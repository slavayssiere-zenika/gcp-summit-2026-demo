import asyncio
import json
import logging
import os
import traceback
from datetime import datetime, timezone

import redis
import uvicorn
from auth import verify_jwt
from fastapi import (APIRouter, BackgroundTasks, Depends, FastAPI,
                     HTTPException, Request, Response)
from fastapi.middleware.cors import CORSMiddleware
from shared.fastapi_utils import instrument_app
from mcp_server import call_tool, list_tools
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from pydantic import BaseModel
from shared.mcp_server_utils import setup_mcp_tracer_provider


# La vérification Zero-Trust et la purge de SECRET_KEY est déléguée à auth.py.

tracer = setup_mcp_tracer_provider("monitoring-mcp")

# Leak Mitigation (Anti prompt-injection / introspection)
os.environ.pop("JWT_SECRET", None)
os.environ.pop("SECRET_KEY", None)
os.environ.pop("GEMINI_API_KEY", None)
os.environ.pop("ADMIN_SERVICE_PASSWORD", None)
app = FastAPI(title="Monitoring MCP Sidecar", root_path=os.getenv("ROOT_PATH", ""))
instrument_app(app, service_name="monitoring-mcp")
HTTPXClientInstrumentor().instrument()

cors_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://localhost:80,http://localhost:8080,"
    "https://dev.zenika.slavayssiere.fr,https://uat.zenika.slavayssiere.fr,"
    "https://zenika.slavayssiere.fr",
).split(",")
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
    # Note: import kept here to avoid circular import between mcp_app and mcp_server at module level.
    from mcp_server import get_infrastructure_topology

    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/9")
    try:
        r = redis.from_url(redis_url, socket_timeout=2.0)
        cache_key = f"cache:metrics:topology:{hours_lookback}"
        lock_key = f"lock:metrics:topology:{hours_lookback}"

        async def async_background_refresh():
            acquired = r.set(lock_key, "1", ex=30, nx=True)
            if not acquired:
                return
            try:
                data = await get_infrastructure_topology(hours_lookback)
                data["generated_at"] = datetime.now(timezone.utc).isoformat()
                r.set(cache_key, json.dumps(data), ex=3600)
            except Exception as e:
                logging.error(f"Topology refresh failed: {e}")
            finally:
                r.delete(lock_key)

        if not force:
            try:
                cached_str = r.get(cache_key)
                if cached_str:
                    cached_data = json.loads(cached_str)
                    if "generated_at" in cached_data:
                        gen_time = datetime.fromisoformat(cached_data["generated_at"])
                        age = (datetime.now(timezone.utc) - gen_time).total_seconds()
                        if age > 300:  # 5 minutes soft TTL
                            background_tasks.add_task(async_background_refresh)
                    return cached_data
            except Exception:
                raise

        # Execution or waiting for lock
        acquired = r.set(lock_key, "1", ex=30, nx=True)
        if not acquired and not force:
            for _ in range(50):
                await asyncio.sleep(0.2)
                d = r.get(cache_key)
                if d:
                    return json.loads(d)

        data = await get_infrastructure_topology(hours_lookback)
        data["generated_at"] = datetime.now(timezone.utc).isoformat()
        r.set(cache_key, json.dumps(data), ex=3600)

        if acquired:
            r.delete(lock_key)
        return data

    except Exception as e:
        logging.exception("Failed to fetch topology in Monitoring MCP REST endpoint")
        raise HTTPException(status_code=500, detail=str(e))


@mcp_router.post("/call")
async def execute_tool(request: ToolCallRequest, http_request: Request):
    auth_header = http_request.headers.get("Authorization")
    if auth_header:
        from shared.auth.context import auth_header_var
        auth_header_var.set(auth_header)

    try:
        result = await call_tool(request.name, request.arguments)
        return {"result": [r.model_dump() for r in result]}
    except Exception as e:
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


# Exception handler global enregistré par instrument_app() via shared.exception_handler
# (register_global_exception_handler(app, service_name="monitoring-mcp"))


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port, server_header=False)
