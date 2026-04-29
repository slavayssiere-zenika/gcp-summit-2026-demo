from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, Depends, APIRouter, Response
from pydantic import BaseModel
import asyncio
import os
import json
import uvicorn
import redis
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes

if os.getenv("TRACE_EXPORTER", "grpc") == "http":
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
elif os.getenv("TRACE_EXPORTER", "grpc") == "gcp":
    from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
else:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.propagate import inject
from prometheus_fastapi_instrumentator import Instrumentator

from mcp_server import list_tools, call_tool
from auth import verify_jwt
from logger import setup_logging, LoggingMiddleware

# La vérification Zero-Trust et la purge de SECRET_KEY est déléguée à auth.py, 
# importé ci-dessus, ce qui empêche une disparition prématurée de la variable d'env lors des imports.

sampling_rate = float(os.getenv("TRACE_SAMPLING_RATE", "1.0"))
sampler = ParentBased(root=TraceIdRatioBased(sampling_rate))
provider = TracerProvider(
    resource=Resource.create({
        ResourceAttributes.SERVICE_NAME: "monitoring-mcp",
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

tracer = trace.get_tracer(__name__)

setup_logging()

app = FastAPI(title="Monitoring MCP Sidecar", root_path=os.getenv("ROOT_PATH", ""))
app.add_middleware(LoggingMiddleware)

FastAPIInstrumentor.instrument_app(app, excluded_urls="health,metrics")
RedisInstrumentor().instrument()
HTTPXClientInstrumentor().instrument()
Instrumentator().instrument(app).expose(app)

from fastapi.middleware.cors import CORSMiddleware
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:80,http://localhost:8080,https://dev.zenika.slavayssiere.fr,https://uat.zenika.slavayssiere.fr,https://zenika.slavayssiere.fr").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins, 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
mcp_router = APIRouter(dependencies=[Depends(verify_jwt)])
api_router = APIRouter(dependencies=[Depends(verify_jwt)])

class ToolCallRequest(BaseModel):
    name: str
    arguments: dict = {}

@mcp_router.get("/tools")
async def get_tools():
    tools = await list_tools()
    return [{"name": t.name, "description": t.description, "inputSchema": t.inputSchema} for t in tools]

@api_router.get("/topology")
async def get_topology(background_tasks: BackgroundTasks, hours_lookback: int = 1, force: bool = False):
    """Native REST endpoint to fetch infrastructure topology from GCP Cloud Trace with Caching."""
    from mcp_server import get_infrastructure_topology
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/9")
    try:
        r = redis.from_url(redis_url, socket_timeout=2.0)
        cache_key = f"cache:metrics:topology:{hours_lookback}"
        lock_key = f"lock:metrics:topology:{hours_lookback}"

        async def async_background_refresh():
            acquired = r.set(lock_key, "1", ex=30, nx=True)
            if not acquired: return
            try:
                data = await get_infrastructure_topology(hours_lookback)
                # Hard TTL 1 hour. We'll use 5 minutes for Soft TTL.
                data["generated_at"] = datetime.utcnow().isoformat()
                r.set(cache_key, json.dumps(data), ex=3600)
            except Exception as e:
                import logging
                logging.error(f"Topology refresh failed: {e}")
            finally:
                r.delete(lock_key)

        from datetime import datetime
        if not force:
            try:
                cached_str = r.get(cache_key)
                if cached_str:
                    cached_data = json.loads(cached_str)
                    if "generated_at" in cached_data:
                        gen_time = datetime.fromisoformat(cached_data["generated_at"])
                        age = (datetime.utcnow() - gen_time).total_seconds()
                        if age > 300: # 5 minutes soft TTL
                            background_tasks.add_task(async_background_refresh)
                    return cached_data
            except Exception: raise

        # Execution or Waiting for lock
        acquired = r.set(lock_key, "1", ex=30, nx=True)
        if not acquired and not force:
            for _ in range(50):
                await asyncio.sleep(0.2)
                d = r.get(cache_key)
                if d: return json.loads(d)

        data = await get_infrastructure_topology(hours_lookback)
        data["generated_at"] = datetime.utcnow().isoformat()
        r.set(cache_key, json.dumps(data), ex=3600)
        
        if acquired: r.delete(lock_key)
        return data

    except Exception as e:
        import logging
        logging.exception("Failed to fetch topology in Monitoring MCP REST endpoint")
        raise HTTPException(status_code=500, detail=str(e))



@mcp_router.post("/call")
async def execute_tool(request: ToolCallRequest, http_request: Request):
    auth_header = http_request.headers.get("Authorization")
    if auth_header:
        from mcp_server import mcp_auth_header_var
        mcp_auth_header_var.set(auth_header)
    
    try:
        result = await call_tool(request.name, request.arguments)
        return {"result": [r.model_dump() for r in result]}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))



app.include_router(mcp_router, prefix="/mcp")
app.include_router(api_router, prefix="/api")

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "monitoring-mcp"}

@app.get("/version")
async def get_version():
    return {"version": os.getenv("APP_VERSION", "unknown")}

@app.get("/spec")
async def get_spec():
    try:
        with open("spec.md", "r", encoding="utf-8") as f:
            return Response(content=f.read(), media_type="text/markdown")
    except Exception:
        return Response(content="# Monitoring MCP — Spécification introuvable", media_type="text/markdown")


import traceback
from fastapi.responses import JSONResponse
import httpx
import logging
import asyncio

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
                    "context": trace_context[:2000]
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
    
    if token:
        await report_exception_to_prompts_api("monitoring_mcp", error_msg, trace_context, token)
    
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port, server_header=False)
