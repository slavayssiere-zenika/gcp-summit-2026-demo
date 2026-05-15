import asyncio
import logging
import os
import traceback
from contextlib import asynccontextmanager

import database
import httpx
from fastapi import APIRouter, Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from logger import LoggingMiddleware, setup_logging
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.propagate import inject
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.semconv.resource import ResourceAttributes
from prometheus_fastapi_instrumentator import Instrumentator
from shared.middlewares import ContentLengthSanitizerASGIMiddleware
from src.auth import verify_jwt
from src.cvs.router import public_router, router

if os.getenv("TRACE_EXPORTER", "grpc") == "http":
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import \
        OTLPSpanExporter
elif os.getenv("TRACE_EXPORTER", "grpc") == "gcp":
    from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
else:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import \
        OTLPSpanExporter


sampling_rate = float(os.getenv("TRACE_SAMPLING_RATE", "1.0"))
sampler = ParentBased(root=TraceIdRatioBased(sampling_rate))
provider = TracerProvider(
    resource=Resource.create({
        ResourceAttributes.SERVICE_NAME: "cv-api",
        ResourceAttributes.SERVICE_VERSION: os.getenv("APP_VERSION", "dev"),
    }),
    sampler=sampler
)
if os.getenv("TRACE_EXPORTER", "grpc") == "gcp":
    provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))
else:
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter() if os.getenv(
        "TRACE_EXPORTER", "grpc") == "http" else OTLPSpanExporter(insecure=True)))
trace.set_tracer_provider(provider)

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.init_db_connector()
    SQLAlchemyInstrumentor().instrument(engine=database.engine.sync_engine)
    yield
    await database.close_db_connector()

app = FastAPI(lifespan=lifespan, title="CV Analysis API", root_path=os.getenv("ROOT_PATH", ""))
app.add_middleware(LoggingMiddleware)
Instrumentator().instrument(app).expose(app)
app.add_middleware(ContentLengthSanitizerASGIMiddleware)


FastAPIInstrumentor.instrument_app(app, excluded_urls="health,ready,metrics,version")
RedisInstrumentor().instrument()
HTTPXClientInstrumentor().instrument()


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


protected_router = APIRouter(dependencies=[Depends(verify_jwt)])


@app.get("/spec")
async def get_spec():
    try:
        with open("spec.md", "r", encoding="utf-8") as f:
            return Response(content=f.read(), media_type="text/markdown")
    except Exception:
        return Response(content="# Specification introuvable", media_type="text/markdown")

app.include_router(public_router)
app.include_router(router)


@app.api_route("/mcp/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
@app.api_route("//mcp/{path:path}", methods=["GET", "POST", "PUT", "DELETE"], include_in_schema=False)
async def proxy_mcp(path: str, request: Request):
    import httpx
    sidecar_url = os.getenv("MCP_SIDECAR_URL", "http://cv_mcp:8000")
    url = f"{sidecar_url.rstrip('/')}/mcp/{path}"
    if request.url.query:
        url += f"?{request.url.query}"

    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("content-length", None)

    body = await request.body()

    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0)) as client:
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

app.include_router(protected_router)


async def get_service_token_fallback() -> str:
    import logging
    import os

    import httpx
    logging.getLogger(__name__)
    dev_token = os.getenv("DEV_SERVICE_TOKEN")
    if dev_token:
        return dev_token

    try:
        users_api_url = os.getenv("USERS_API_URL", "http://users_api:8000")
        async with httpx.AsyncClient(timeout=httpx.Timeout(2.0, connect=1.0)) as client:
            res_meta = await client.get(
                "http://metadata.google.internal/computeMetadata/v1/instance/"
                "service-accounts/default/identity?audience=users_api",
                headers={"Metadata-Flavor": "Google"},
                timeout=2.0
            )
            if res_meta.status_code == 200:
                id_token = res_meta.text
                res = await client.post(f"{users_api_url}/auth/service-account/login", json={"id_token": id_token})
                if res.status_code == 200:
                    from shared.schemas.auth import TokenResponse
                    data = TokenResponse.model_validate(res.json())
                    return data.access_token
    except Exception:
        raise
    return ""


async def report_exception_to_prompts_api(service_name: str, error_msg: str, trace_context: str, token: str):
    prompts_api_url = os.getenv("PROMPTS_API_URL", "http://prompts_api:8000")
    headers = {"Authorization": f"Bearer {token}"}
    inject(headers)

    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=3.0)) as client:
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
            # Ne pas re-raise : cette fonction est best-effort.
            # Un échec du reporting ne doit JAMAIS crasher une background task.


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, StarletteHTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    if isinstance(exc, RequestValidationError):
        return JSONResponse(status_code=422, content={"detail": exc.errors()})

    error_msg = str(exc)
    trace_context = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))

    # Tenter d'obtenir un token : d'abord depuis le header (si JWT applicatif HS256),
    # sinon via le fallback service-account GCP.
    # Note : le token OIDC Pub/Sub (RS256 Google) n'est PAS utilisable pour prompts_api.
    auth_header = request.headers.get("Authorization", "")
    token = ""
    if auth_header.startswith("Bearer "):
        candidate = auth_header.replace("Bearer ", "")
        # Heuristique : les JWT HS256 applicatifs ont 3 segments séparés par '.'
        # Les tokens OIDC Google aussi, mais on essaie quand même — prompts_api
        # rejetera avec 401 si invalide, ce qui est géré silencieusement.
        token = candidate

    try:
        if not token:
            token = await get_service_token_fallback()

        # On reporte TOUJOURS, même sans token :
        # prompts_api peut accepter des rapports non authentifiés sur /errors/report
        # ou rejeter avec 401 — dans les deux cas on ne bloque pas le handler.
        asyncio.create_task(
            report_exception_to_prompts_api("cv_api", error_msg, trace_context, token)
        )

    except Exception as fallback_e:
        logging.error(f"Failed to process exception reporting: {fallback_e}")

    logging.error(f"[cv_api] Unhandled exception on {request.method} {request.url.path}: {error_msg}\n{trace_context}")
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
