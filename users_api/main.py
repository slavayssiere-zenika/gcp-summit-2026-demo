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
from opentelemetry.propagate import extract
from opentelemetry.trace import set_span_in_context
from fastapi.middleware.cors import CORSMiddleware
from src.users.router import router, auth_router
import time
from logger import setup_logging, LoggingMiddleware


provider = TracerProvider(
    resource=Resource.create({
        ResourceAttributes.SERVICE_NAME: "users-api",
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

@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.init_db_connector()
    SQLAlchemyInstrumentor().instrument(engine=database.engine.sync_engine)
    asyncio.create_task(seed_admin())
    yield
    await database.close_db_connector()
app = FastAPI(title="Users API", lifespan=lifespan, root_path=os.getenv("ROOT_PATH", ""))
app.add_middleware(LoggingMiddleware)
Instrumentator().instrument(app).expose(app)

cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:80,http://localhost:8080").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins, 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


import asyncio
import logging
import os
from sqlalchemy import text
from src.users.models import User
from src.auth import get_password_hash

logger = logging.getLogger(__name__)

async def seed_admin():
    admin_password = os.getenv("DEFAULT_ADMIN_PASSWORD")
    if not admin_password:
        return

    for _ in range(60):
        try:
            if not await database.check_db_connection():
                await asyncio.sleep(5)
                continue
                
            async with database.SessionLocal() as db:
                # Check if users table exists and admin doesn't
                res = await db.execute(text("SELECT id FROM users WHERE email = 'admin@zenika.com'"))
                row = res.fetchone()
                hashed_password = get_password_hash(admin_password)

                if not row:
                    logger.info("Seeding admin user into database...")
                    admin_user = User(
                        username="admin",
                        email="admin@zenika.com",
                        first_name="Zenika",
                        last_name="Admin",
                        full_name="Zenika Admin",
                        role="admin",
                        is_active=True,
                        hashed_password=hashed_password,
                        allowed_category_ids="1,2,3,4,5"
                    )
                    db.add(admin_user)
                    await db.commit()
                    logger.info("Admin user seeded successfully!")
                else:
                    logger.info("Syncing existing admin password with current environment variable...")
                    await db.execute(
                        text("UPDATE users SET hashed_password = :hp WHERE email = 'admin@zenika.com'"),
                        {"hp": hashed_password}
                    )
                    await db.commit()
                return
        except Exception as e:
            # users table might not exist yet if Liquibase hasn't finished
            await asyncio.sleep(5)


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

app.include_router(auth_router)
app.include_router(router)

@protected_router.api_route("/mcp/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
@protected_router.api_route("//mcp/{path:path}", methods=["GET", "POST", "PUT", "DELETE"], include_in_schema=False)
async def proxy_mcp(path: str, request: Request):
    import httpx
    url = f"http://localhost:8081/mcp/{path}"
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
