import os
from contextlib import asynccontextmanager

import shared.database as database
from fastapi import APIRouter, Depends, FastAPI, Request, Response
from shared.fastapi_utils import instrument_app
from opentelemetry import trace
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.semconv.resource import ResourceAttributes
from shared.auth.jwt import verify_jwt
from src.items.router import public_router, router
import httpx
import uvicorn

if os.getenv("TRACE_EXPORTER", "grpc") == "http":
    pass
elif os.getenv("TRACE_EXPORTER", "grpc") == "gcp":
    pass
else:
    pass


sampling_rate = float(os.getenv("TRACE_SAMPLING_RATE", "1.0"))
sampler = ParentBased(root=TraceIdRatioBased(sampling_rate))
provider = TracerProvider(
    resource=Resource.create({
        ResourceAttributes.SERVICE_NAME: "items-api",
        ResourceAttributes.SERVICE_VERSION: os.getenv("APP_VERSION", "dev"),
    }),
    sampler=sampler
)
# ... (rest of provider setup)
trace.set_tracer_provider(provider)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.init_db_connector()
    SQLAlchemyInstrumentor().instrument(engine=database.engine.sync_engine)
    yield
    await database.close_db_connector()

app = FastAPI(lifespan=lifespan, title="Items API", root_path=os.getenv("ROOT_PATH", ""))
instrument_app(app, service_name="items-api")
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


os.environ.pop("SECRET_KEY", None)  # Purge post-démarrage (anti prompt-injection)

protected_router = APIRouter(dependencies=[Depends(verify_jwt)])


@app.get("/spec")
async def get_spec():
    try:
        with open("spec.md", "r", encoding="utf-8") as f:
            return Response(content=f.read(), media_type="text/markdown")
    except Exception:
        return Response(content="# Specification introuvable", media_type="text/markdown")

app.include_router(public_router)
app.include_router(protected_router)  # /spec MUST be registered before /{item_id} wildcard
app.include_router(router)


@app.api_route("/mcp/{path:path}", methods=["GET", "POST", "PUT", "DELETE"], dependencies=[Depends(verify_jwt)], include_in_schema=False)
@app.api_route("//mcp/{path:path}", methods=["GET", "POST", "PUT", "DELETE"], dependencies=[Depends(verify_jwt)], include_in_schema=False)
async def proxy_mcp(path: str, request: Request):
    sidecar_url = os.getenv("MCP_SIDECAR_URL", "http://items_mcp:8000")
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

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
