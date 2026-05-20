import os
from contextlib import asynccontextmanager

import shared.database as database
import httpx
from fastapi import APIRouter, Depends, FastAPI, Request, Response
from shared.fastapi_utils import instrument_app
from opentelemetry import trace
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.semconv.resource import ResourceAttributes
from shared.auth.jwt import verify_jwt
from src.cvs.router import public_router, router
import uvicorn
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter as OTLPGrpcExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter as OTLPHttpExporter

if os.getenv("TRACE_EXPORTER", "grpc") == "http":
    OTLPSpanExporter = OTLPHttpExporter
elif os.getenv("TRACE_EXPORTER", "grpc") == "gcp":
    OTLPSpanExporter = None  # CloudTraceSpanExporter utilisé directement
else:
    OTLPSpanExporter = OTLPGrpcExporter


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.init_db_connector()
    SQLAlchemyInstrumentor().instrument(engine=database.engine.sync_engine)
    yield
    await database.close_db_connector()


# Leak Mitigation (Anti prompt-injection / introspection)
os.environ.pop("JWT_SECRET", None)
os.environ.pop("SECRET_KEY", None)
os.environ.pop("GEMINI_API_KEY", None)
os.environ.pop("ADMIN_SERVICE_PASSWORD", None)
app = FastAPI(lifespan=lifespan, title="CV Analysis API", root_path=os.getenv("ROOT_PATH", ""))
instrument_app(app, service_name="cv-api")
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


@app.api_route("/mcp/{path:path}", methods=["GET", "POST", "PUT", "DELETE"], dependencies=[Depends(verify_jwt)])
@app.api_route("//mcp/{path:path}", methods=["GET", "POST", "PUT", "DELETE"], dependencies=[Depends(verify_jwt)], include_in_schema=False)
async def proxy_mcp(path: str, request: Request):
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


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8004)
