import asyncio
import logging
import os

from fastapi import FastAPI, Response, Request
from contextlib import asynccontextmanager
import database
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from opentelemetry import trace
if os.getenv("TRACE_EXPORTER", "grpc") == "http":
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
elif os.getenv("TRACE_EXPORTER", "grpc") == "gcp":
    from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
else:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

from database import engine, Base
from src.prompts import router

# 1. Setup DB Schema
# Deferring schema creation to async startup event to speed up uvicorn boot

# 2. Initialize FastAPI
from logger import setup_logging, LoggingMiddleware
setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.init_db_connector()
    SQLAlchemyInstrumentor().instrument(engine=database.engine.sync_engine)
    yield
    await database.close_db_connector()

app = FastAPI(lifespan=lifespan, title="Prompts API", version="1.0.0", root_path=os.getenv("ROOT_PATH", ""))
app.add_middleware(LoggingMiddleware)

# 3. Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



FastAPIInstrumentor.instrument_app(app, excluded_urls="health,metrics")
RedisInstrumentor().instrument()
HTTPXClientInstrumentor().instrument()


# 5. Prometheus Instrumentator
Instrumentator().instrument(app).expose(app)

# 6. Include Router

@app.get("/health")
async def health_check():
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
import httpx
from fastapi import APIRouter, Depends
from src.prompts.router import verify_jwt
from opentelemetry.propagate import inject

protected_router = APIRouter(dependencies=[Depends(verify_jwt)])

@app.get("/spec")
async def get_spec():
    try:
        with open("spec.md", "r", encoding="utf-8") as f:
            return Response(content=f.read(), media_type="text/markdown")
    except Exception:
        return Response(content="# Specification introuvable", media_type="text/markdown")

# Rule §3 (AGENTS.md): Toute logique métier expose un proxy vers son MCP sidecar
@app.api_route("/mcp/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
@app.api_route("//mcp/{path:path}", methods=["GET", "POST", "PUT", "DELETE"], include_in_schema=False)
async def proxy_mcp(path: str, request: Request):
    sidecar_url = os.getenv("MCP_SIDECAR_URL", "http://prompts_mcp:8000")
    url = f"{sidecar_url.rstrip('/')}/mcp/{path}"
    if request.url.query:
        url += f"?{request.url.query}"

    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("content-length", None)
    inject(headers)  # Rule §5 (AGENTS.md): inject OTel trace context

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

app.include_router(protected_router)  # /spec MUST be registered before /{key} wildcard
app.include_router(router.router, prefix="", tags=["prompts"])

import traceback
from fastapi.responses import JSONResponse
import httpx

import traceback
from fastapi.responses import JSONResponse
import httpx
import logging
import asyncio



async def get_service_token_fallback() -> str:
    import httpx, os, logging
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
    except Exception: raise
    return ""

async def report_exception_to_prompts_api(service_name: str, error_msg: str, trace_context: str, token: str):
    prompts_api_url = os.getenv("PROMPTS_API_URL", "http://prompts_api:8000")
    headers = {"Authorization": f"Bearer {token}"}
    try:
        from opentelemetry.propagate import inject
        inject(headers)
    except Exception: raise

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
    
    try:
        if not token:
            token = await get_service_token_fallback()
    
        if token:
            await report_exception_to_prompts_api("prompts_api", error_msg, trace_context, token)
    
    except Exception as fallback_e:
        logging.error(f"Failed to process exception reporting: {fallback_e}")
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})

        
    error_msg = str(exc)
    trace_context = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else ""
    
    if token:
        import asyncio
        await report_exception_to_prompts_api("prompts_api", error_msg, trace_context, token)
    
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})
