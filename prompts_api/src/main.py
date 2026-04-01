import os
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

from src.database import engine, Base
from src.prompts import router

# 1. Setup DB Schema
Base.metadata.create_all(bind=engine)

# 2. Initialize FastAPI
app = FastAPI(title="Prompts API", version="1.0.0")

# 3. Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 4. OpenTelemetry Configuration
OTEL_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "prompts-api")
OTEL_EXPORTER_OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://tempo:4317")

resource = Resource.create({
    ResourceAttributes.SERVICE_NAME: OTEL_SERVICE_NAME
})

provider = TracerProvider(resource=resource)
trace.set_tracer_provider(provider)

otlp_exporter = OTLPSpanExporter(
    endpoint=OTEL_EXPORTER_OTLP_ENDPOINT,
    insecure=True
)

span_processor = BatchSpanProcessor(otlp_exporter)
provider.add_span_processor(span_processor)

FastAPIInstrumentor.instrument_app(app)
SQLAlchemyInstrumentor().instrument(engine=engine)

# 5. Prometheus Instrumentator
Instrumentator().instrument(app).expose(app)

# 6. Include Router
app.include_router(router.router, prefix="/prompts", tags=["prompts"])

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/spec")
async def get_spec():
    try:
        with open("spec.md", "r", encoding="utf-8") as f:
            return Response(content=f.read(), media_type="text/markdown")
    except Exception:
        return Response(content="# Specification introuvable", media_type="text/markdown")
