import os
from contextlib import asynccontextmanager

import httpx
import uvicorn
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from prometheus_fastapi_instrumentator import Instrumentator

from telemetry import setup_telemetry
from logger import setup_logging, LoggingMiddleware
from agent_commons.exception_handler import make_global_exception_handler
from router import router as api_router
from tools_registry import router as mcp_router

tracer = setup_telemetry()
setup_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting ADK Web Agent with Gemini...")
    yield

app = FastAPI(
    title="ADK Router Agent (A2A)",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
    root_path=os.getenv("ROOT_PATH", ""),
    lifespan=lifespan
)

app.add_middleware(LoggingMiddleware)
Instrumentator().instrument(app).expose(app)
FastAPIInstrumentor.instrument_app(app, excluded_urls="health,health/agents,metrics")
RedisInstrumentor().instrument()
HTTPXClientInstrumentor().instrument()

@app.get("/")
async def root():
    return {"message": "Router Agent API - Use /query for interactions"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/version")
async def get_version():
    return {"version": os.getenv("APP_VERSION", "unknown")}

@app.get("/health/agents")
async def health_agents():
    """ADR12-5 — Agrège la santé des 3 sous-agents (HR, Ops, Missions)."""
    from metrics import AGENT_HEALTH_PROBE_TOTAL
    import time
    import asyncio

    _AGENTS = {
        "hr":       os.getenv("AGENT_HR_API_URL",       "http://agent_hr_api:8080"),
        "ops":      os.getenv("AGENT_OPS_API_URL",      "http://agent_ops_api:8080"),
        "missions": os.getenv("AGENT_MISSIONS_API_URL", "http://agent_missions_api:8080"),
    }

    async def _probe(agent_name: str, base_url: str) -> dict:
        start = time.monotonic()
        ok = False
        version = "unknown"
        try:
            async with httpx.AsyncClient(timeout=3.0) as c:
                h_res, v_res = await asyncio.gather(
                    c.get(f"{base_url.rstrip('/')}/health"),
                    c.get(f"{base_url.rstrip('/')}/version"),
                    return_exceptions=True,
                )
            if not isinstance(h_res, Exception) and h_res.status_code == 200:
                ok = True
            if not isinstance(v_res, Exception) and v_res.status_code == 200:
                version = v_res.json().get("version", "unknown")
        except Exception as e:
            logger.warning("[health-probe] Agent '%s' health check failed: %s", agent_name, e)
            ok = False
        finally:
            latency_ms = round((time.monotonic() - start) * 1000)
            status = "up" if ok else "down"
            AGENT_HEALTH_PROBE_TOTAL.labels(agent=agent_name, status=status).inc()
        return {
            "name": agent_name,
            "status": status,
            "version": version,
            "latency_ms": latency_ms,
        }

    results = await asyncio.gather(*[_probe(n, u) for n, u in _AGENTS.items()])
    agents_detail = {r["name"]: {k: v for k, v in r.items() if k != "name"} for r in results}

    up_count = sum(1 for r in results if r["status"] == "up")
    if up_count == len(_AGENTS):
        agg_status = "healthy"
    elif up_count > 0:
        agg_status = "degraded"
    else:
        agg_status = "unhealthy"

    http_code = 200 if up_count > 0 else 503
    return JSONResponse(
        content={"status": agg_status, "agents": agents_detail},
        status_code=http_code,
    )

from opentelemetry.propagate import inject

USERS_API_URL = os.getenv("USERS_API_URL", "http://users_api:8000")

@app.post("/login")
async def login(request: Request, response: Response):
    data = await request.json()
    headers = {}
    inject(headers)
    async with httpx.AsyncClient() as client:
        res = await client.post(f"{USERS_API_URL}/login", json=data, headers=headers)
        if res.status_code != 200:
            raise HTTPException(status_code=res.status_code, detail=res.json().get("detail", "Erreur de connexion"))
        
        for name, value in res.cookies.items():
            response.set_cookie(key=name, value=value, httponly=True, samesite="lax")
        
        return res.json()

@app.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token")
    return {"message": "Déconnecté"}

@app.get("/me")
async def get_me(request: Request):
    headers = {}
    inject(headers)
    async with httpx.AsyncClient() as client:
        cookies = request.cookies
        res = await client.get(f"{USERS_API_URL}/me", cookies=cookies, headers=headers)
        if res.status_code != 200:
            raise HTTPException(status_code=res.status_code, detail="Non connecté")
        return res.json()

app.include_router(api_router)
app.include_router(mcp_router)

app.add_exception_handler(Exception, make_global_exception_handler("agent_router_api"))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)
