from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, Depends, APIRouter, Response
from pydantic import BaseModel
import asyncio
import os
import json
import uvicorn
import redis
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
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

from mcp_server import list_tools, call_tool, get_aiops_dashboard_data_internal
from auth import verify_jwt
from logger import setup_logging, LoggingMiddleware

# La vérification Zero-Trust et la purge de SECRET_KEY est déléguée à auth.py, 
# importé ci-dessus, ce qui empêche une disparition prématurée de la variable d'env lors des imports.

provider = TracerProvider(
    resource=Resource.create({
        ResourceAttributes.SERVICE_NAME: "market-mcp",
        ResourceAttributes.SERVICE_VERSION: "1.0.0",
    })
)
if os.getenv("TRACE_EXPORTER", "grpc") == "gcp":
    provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))
else:
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter() if os.getenv("TRACE_EXPORTER", "grpc") == "http" else OTLPSpanExporter(insecure=True)))
trace.set_tracer_provider(provider)

tracer = trace.get_tracer(__name__)

setup_logging()

app = FastAPI(title="Market & FinOps MCP Sidecar", root_path=os.getenv("ROOT_PATH", ""))
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


@api_router.get("/metrics/aiops")
async def get_aiops_metrics(background_tasks: BackgroundTasks, force: bool = False):
    """
    Récupère les indicateurs AIOps et FinOps (Optimisé).
    - Exécution parallèle BigQuery
    - Stale-While-Revalidate (SWR) : hard TTL 24h, soft TTL 1h.
    - Mutex Redis (SETNX) pour éviter le Cache Stampede.
    """
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/1")
    try:
        r = redis.from_url(redis_url, socket_timeout=2.0)
        cache_key = "cache:metrics:aiops"
        lock_key = "lock:metrics:aiops"

        async def async_background_refresh():
            acquired = r.set(lock_key, "1", ex=30, nx=True)
            if not acquired:
                return
            try:
                data = await get_aiops_dashboard_data_internal()
                r.set(cache_key, json.dumps(data), ex=3600*24)
            except Exception as e:
                import logging
                logging.error(f"Background refresh failed: {e}")
            finally:
                r.delete(lock_key)

        # 1. Tentative depuis le cache (si pas de force)
        if not force:
            try:
                cached_data_str = r.get(cache_key)
                if cached_data_str:
                    cached_data = json.loads(cached_data_str)
                    # Check age for Soft TTL
                    from datetime import datetime
                    if "generated_at" in cached_data:
                        gen_str = cached_data["generated_at"]
                        try:
                            # Parse standard ISO format
                            gen_time = datetime.fromisoformat(gen_str)
                            age = (datetime.utcnow() - gen_time).total_seconds()
                            if age > 3600:
                                # Stale! Schedule background refresh and return old data
                                background_tasks.add_task(async_background_refresh)
                        except Exception: raise
                    return cached_data
            except Exception as re:
                import logging
                logging.warning(f"Redis cache access failed: {re}")

        # 2. Cache Miss ou Force -> Calcul direct
        acquired = False
        try:
            acquired = r.set(lock_key, "1", ex=30, nx=True)
            if not acquired and not force:
                # Concurrent request is currently computing it. Wait up to 10s.
                for _ in range(50):
                    await asyncio.sleep(0.2)
                    d = r.get(cache_key)
                    if d: return json.loads(d)

            # Execution (Parallelisée en backend)
            data = await get_aiops_dashboard_data_internal()
            r.set(cache_key, json.dumps(data), ex=3600*24)
            return data
        finally:
            if acquired:
                r.delete(lock_key)

    except Exception as e:
        import logging
        logging.exception("Failed to fetch AIOps metrics in Market MCP REST endpoint")
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

@api_router.post("/admin/finops/detect")
async def detect_finops_anomalies(http_request: Request):
    """
    Exécute la Requête BigQuery pour détecter les anomalies de consommation,
    et déclenche le Kill-Switch si le seuil est dépassé.
    """
    from mcp_server import client as bq_client, FINOPS_TABLE_REF
    import httpx
    
    threshold = int(os.getenv("FINOPS_ANOMALY_THRESHOLD", 500000))
    users_api_url = os.getenv("USERS_API_URL", "http://users_api:8000/")
    
    query = f"""
        SELECT user_email, SUM(input_tokens + output_tokens) as total_tokens
        FROM `{FINOPS_TABLE_REF}`
        WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 15 MINUTE)
        GROUP BY user_email
        HAVING total_tokens > @threshold
    """
    
    from google.cloud import bigquery
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("threshold", "INT64", threshold)
        ]
    )
    
    query_job = bq_client.query(query, job_config=job_config)
    results = query_job.result()
    
    auth_header = http_request.headers.get("Authorization")
    headers = {"Authorization": auth_header} if auth_header else {}
    inject(headers)  # Propagate OTel trace context
    
    suspended_users = []
    
    async with httpx.AsyncClient() as http:
        for row in results:
            user_email = row.user_email
            total_tokens = row.total_tokens
            
            # Déclenchement du Kill Switch
            try:
                res = await http.post(f"{users_api_url.rstrip('/')}/suspend/{user_email}", headers=headers)
                if res.status_code == 200:
                    suspended_users.append({"email": user_email, "tokens": total_tokens, "status": "suspended"})
                else:
                    import logging
                    logging.error(f"Echec suspension {user_email}: {res.text}")
                    suspended_users.append({"email": user_email, "tokens": total_tokens, "status": "failed"})
            except Exception as e:
                import logging
                logging.exception(f"Exception suspension {user_email}")
                suspended_users.append({"email": user_email, "tokens": total_tokens, "status": "error", "message": str(e)})

    return {"threshold": threshold, "anomalies_detected": len(suspended_users), "details": suspended_users}

app.include_router(mcp_router, prefix="/mcp")
app.include_router(api_router, prefix="/api")

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "market-mcp"}

@app.get("/version")
async def get_version():
    return {"version": os.getenv("APP_VERSION", "unknown")}

@app.get("/spec")
async def get_spec():
    try:
        with open("spec.md", "r", encoding="utf-8") as f:
            return Response(content=f.read(), media_type="text/markdown")
    except Exception:
        return Response(content="# Market MCP — Spécification introuvable", media_type="text/markdown")


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
        asyncio.create_task(report_exception_to_prompts_api("market_mcp", error_msg, trace_context, token))
    
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port, server_header=False)
