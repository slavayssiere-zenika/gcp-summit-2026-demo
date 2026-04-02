from fastapi import FastAPI, Response, Request
from prometheus_fastapi_instrumentator import Instrumentator
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.propagate import extract
from opentelemetry.trace import set_span_in_context
from fastapi.middleware.cors import CORSMiddleware
from database import engine
from src.users.router import router, auth_router
import time
from logger import setup_logging, LoggingMiddleware


provider = TracerProvider(
    resource=Resource.create({
        ResourceAttributes.SERVICE_NAME: "users-api",
        ResourceAttributes.SERVICE_VERSION: "1.0.0",
    })
)
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(insecure=True)))
trace.set_tracer_provider(provider)

tracer = trace.get_tracer(__name__)

setup_logging()
app = FastAPI(title="Users API")
app.add_middleware(LoggingMiddleware)
Instrumentator().instrument(app).expose(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Since it's behind a proxy or accessed directly
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


import asyncio
import logging
import os


FastAPIInstrumentor.instrument_app(app, excluded_urls="metrics,health")
SQLAlchemyInstrumentor().instrument(engine=engine)

app.include_router(auth_router)
app.include_router(router)




@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/spec")
async def get_spec():
    try:
        with open("spec.md", "r", encoding="utf-8") as f:
            return Response(content=f.read(), media_type="text/markdown")
    except Exception:
        return Response(content="# Specification introuvable", media_type="text/markdown")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
