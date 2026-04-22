from fastapi import FastAPI, Response, Request
from contextlib import asynccontextmanager
import database
from prometheus_fastapi_instrumentator import Instrumentator
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
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
from src.cvs.router import router, public_router
from logger import setup_logging, LoggingMiddleware

provider = TracerProvider(
    resource=Resource.create({
        ResourceAttributes.SERVICE_NAME: "cv-api",
        ResourceAttributes.SERVICE_VERSION: "1.0.0",
    })
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

app = FastAPI(lifespan=lifespan, title="CV Analysis API", root_path=os.getenv("ROOT_PATH", ""))
app.add_middleware(LoggingMiddleware)
Instrumentator().instrument(app).expose(app)

import asyncio
import os

import logging


FastAPIInstrumentor.instrument_app(app, excluded_urls="health,metrics")
RedisInstrumentor().instrument()
HTTPXClientInstrumentor().instrument()



@app.get("/health")
async def health(response: Response):
    if await database.check_db_connection():
        return {"status": "healthy"}
    response.status_code = 503
    return {"status": "unhealthy"}

@app.get("/version")
async def get_version():
    return {"version": os.getenv("APP_VERSION", "unknown")}

from src.auth import verify_jwt
from fastapi import APIRouter, Depends
protected_router = APIRouter(dependencies=[Depends(verify_jwt)])

@protected_router.get("/spec")
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

app.include_router(protected_router)

import traceback
from fastapi.responses import JSONResponse
import httpx

async def report_exception_to_prompts_api(service_name: str, error_msg: str, trace_context: str, token: str):
    prompts_api_url = os.getenv("PROMPTS_API_URL", "http://prompts_api:8000")
    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                f"{prompts_api_url}/errors/report",
                json={
                    "service_name": service_name,
                    "error_message": error_msg,
                    "context": trace_context[:2000] # truncate to avoid large payloads
                },
                headers={"Authorization": f"Bearer {token}"}
            )
        except Exception:
            pass

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_msg = str(exc)
    trace_context = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else ""
    
    if token:
        import asyncio
        asyncio.create_task(report_exception_to_prompts_api("cv_api", error_msg, trace_context, token))
    
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
