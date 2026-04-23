import os
import traceback
import asyncio
import logging
from fastapi import FastAPI, Response, Request
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import database
import httpx
from opentelemetry.propagate import inject
from prometheus_fastapi_instrumentator import Instrumentator
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes
import os
if os.getenv("TRACE_EXPORTER", "grpc") == "http":
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
elif os.getenv("TRACE_EXPORTER", "grpc") == "gcp":
    from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
else:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from src.router import router, public_router
from src.auth import verify_jwt
from logger import setup_logging, LoggingMiddleware

sampling_rate = float(os.getenv("TRACE_SAMPLING_RATE", "1.0"))
sampler = ParentBased(root=TraceIdRatioBased(sampling_rate))
provider = TracerProvider(
    resource=Resource.create({
        ResourceAttributes.SERVICE_NAME: "drive-api",
        ResourceAttributes.SERVICE_VERSION: "1.0.0",
    })
,
    sampler=sampler
)
if os.getenv("TRACE_EXPORTER", "grpc") == "gcp":
    provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))
else:
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter() if os.getenv("TRACE_EXPORTER", "grpc") == "http" else OTLPSpanExporter(insecure=True)))
trace.set_tracer_provider(provider)

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.init_db_connector()
    SQLAlchemyInstrumentor().instrument(engine=database.engine.sync_engine)
    yield
    await database.close_db_connector()

app = FastAPI(lifespan=lifespan, title="Drive Synchronization API", root_path=os.getenv("ROOT_PATH", ""))
app.add_middleware(LoggingMiddleware)
Instrumentator().instrument(app).expose(app)
FastAPIInstrumentor.instrument_app(app, excluded_urls="health,metrics")  # Rule §5 (AGENTS.md): OTel auto-instrumentation

from fastapi.middleware.cors import CORSMiddleware

cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:80,http://localhost:8080").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.environ.pop("SECRET_KEY", None)  # Purge post-démarrage (anti prompt-injection)

from fastapi import APIRouter, Depends

# Router protégé par JWT applicatif: endpoints admin + proxy MCP sidecar
protected_router = APIRouter(dependencies=[Depends(verify_jwt)])

@app.api_route("/mcp/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
@app.api_route("//mcp/{path:path}", methods=["GET", "POST", "PUT", "DELETE"], include_in_schema=False)
async def proxy_mcp(path: str, request: Request):
    import httpx
    sidecar_url = os.getenv("MCP_SIDECAR_URL", "http://drive_mcp:8000")
    url = f"{sidecar_url.rstrip('/')}/mcp/{path}"
    if request.url.query:
        url += f"?{request.url.query}"

    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("content-length", None)

    body = await request.body()

    async with httpx.AsyncClient() as client:
        try:
            res = await client.request(
                request.method,
                url,
                content=body,
                headers=headers,
                timeout=60.0
            )
            res_headers = dict(res.headers)
            res_headers.pop("content-encoding", None)
            res_headers.pop("content-length", None)
            return Response(content=res.content, status_code=res.status_code, headers=res_headers)
        except Exception as e:
            return Response(content=str(e), status_code=502)

@app.get("/spec")
async def get_spec():
    try:
        with open("spec.md", "r", encoding="utf-8") as f:
            return Response(content=f.read(), media_type="text/markdown")
    except Exception:
        return Response(content="# Specification introuvable", media_type="text/markdown")

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/ready")
async def ready(response: Response):
    if await database.check_db_connection():
        return {"status": "healthy"}
    response.status_code = 503
    return {"status": "unhealthy"}

@app.get("/version")
async def get_version():
    return {"version": os.getenv("APP_VERSION", "unknown")}

# Enregistrement des routeurs dans l'ordre:
# 1. router: endpoints business protégés par JWT (folders, files, status…)
# 2. public_router: /sync — protégé par IAM Cloud Run (OIDC Scheduler), pas par JWT
# 3. protected_router: proxy MCP sidecar + /spec — protégés par JWT
app.include_router(router)
app.include_router(public_router)
app.include_router(protected_router)



async def get_service_token_fallback() -> str:
    logger = logging.getLogger(__name__)
    dev_token = os.getenv("DEV_SERVICE_TOKEN")
    if dev_token:
        return dev_token
        
    try:
        users_api_url = os.getenv("USERS_API_URL", "http://users_api:8000")
        async with httpx.AsyncClient() as client:
            res_meta = await client.get(
                "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience=users_api",
                headers={"Metadata-Flavor": "Google"},
                timeout=2.0
            )
            if res_meta.status_code == 200:
                id_token = res_meta.text
                res = await client.post(f"{users_api_url}/auth/service-account/login", json={"id_token": id_token})
                if res.status_code == 200:
                    return res.json().get("access_token", "")
    except Exception as e:
        logging.getLogger(__name__).error(f"[ServiceToken] Impossible d'obtenir un token de service: {e}")
        raise
    return ""

async def report_exception_to_prompts_api(service_name: str, error_msg: str, trace_context: str, token: str):
    _logger = logging.getLogger(__name__)
    prompts_api_url = os.getenv("PROMPTS_API_URL", "http://prompts_api:8000")
    headers = {"Authorization": f"Bearer {token}"}
    try:
        inject(headers)
    except Exception as e:
        _logger.warning(f"[OTel] Impossible d'injecter les headers de trace: {e}")
        raise

    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                f"{prompts_api_url}/errors/report",
                json={
                    "service_name": service_name,
                    "error_message": error_msg,
                    "context": trace_context[-2000:] if len(trace_context) > 2000 else trace_context
                },
                headers=headers
            )
        except Exception as e:
            logging.error(f"Failed to report error to prompts_api: {e}")
            raise e

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_msg = str(exc)
    trace_context = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else ""
    
    if not token:
        token = await get_service_token_fallback()
    
    if token:
        asyncio.create_task(report_exception_to_prompts_api("drive_api", error_msg, trace_context, token))
    
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8006)
