import os
from fastapi import FastAPI, Response, Request
from contextlib import asynccontextmanager
import database
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from opentelemetry import trace
import os
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

import asyncio
import os
import logging


FastAPIInstrumentor.instrument_app(app, excluded_urls="health,metrics")
RedisInstrumentor().instrument()
HTTPXClientInstrumentor().instrument()


# 5. Prometheus Instrumentator
Instrumentator().instrument(app).expose(app)

# 6. Include Router

@app.get("/health")
async def health_check(response: Response):
    if await database.check_db_connection():
        return {"status": "healthy"}
    response.status_code = 503
    return {"status": "unhealthy"}

@app.get("/version")
async def get_version():
    return {"version": os.getenv("APP_VERSION", "unknown")}
from src.prompts.router import verify_jwt
from fastapi import APIRouter, Depends
protected_router = APIRouter(dependencies=[Depends(verify_jwt)])

@protected_router.get("/spec")
async def get_spec():
    try:
        with open("spec.md", "r", encoding="utf-8") as f:
            return Response(content=f.read(), media_type="text/markdown")
    except Exception:
        return Response(content="# Specification introuvable", media_type="text/markdown")

app.include_router(router.router, prefix="", tags=["prompts"])
app.include_router(protected_router)
