from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, Depends
from pydantic import BaseModel
import asyncio
import os
import json
import uvicorn
import redis
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from prometheus_fastapi_instrumentator import Instrumentator

from mcp_server import list_tools, call_tool, get_aiops_dashboard_data_internal
from auth import verify_jwt
from fastapi import Depends

app = FastAPI(title="Market & FinOps MCP Sidecar")
FastAPIInstrumentor.instrument_app(app, excluded_urls="health,metrics")
RedisInstrumentor().instrument()
HTTPXClientInstrumentor().instrument()
Instrumentator().instrument(app).expose(app)

class ToolCallRequest(BaseModel):
    name: str
    arguments: dict = {}

@app.get("/mcp/tools", dependencies=[Depends(verify_jwt)])
async def get_tools():
    tools = await list_tools()
    return [{"name": t.name, "description": t.description, "inputSchema": t.inputSchema} for t in tools]

@app.get("/topology", dependencies=[Depends(verify_jwt)])
async def get_topology(background_tasks: BackgroundTasks, hours_lookback: int = 1, force: bool = False):
    """Native REST endpoint to fetch infrastructure topology from GCP Cloud Trace with Caching."""
    from mcp_server import get_infrastructure_topology
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/1")
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
            except Exception:
                pass

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
        logging.exception("Failed to fetch topology in Market MCP REST endpoint")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/metrics/aiops", dependencies=[Depends(verify_jwt)])
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
                        except Exception:
                            pass
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

@app.post("/mcp/call")
async def execute_tool(request: ToolCallRequest, http_request: Request, user: dict = Depends(verify_jwt)):
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

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "market-mcp"}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
