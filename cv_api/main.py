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
from database import engine, init_db
from src.cvs.router import router

provider = TracerProvider(
    resource=Resource.create({
        ResourceAttributes.SERVICE_NAME: "cv-api",
        ResourceAttributes.SERVICE_VERSION: "1.0.0",
    })
)
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(insecure=True)))
trace.set_tracer_provider(provider)

app = FastAPI(title="CV Analysis API")
Instrumentator().instrument(app).expose(app)

@app.on_event("startup")
async def startup_event():
    init_db()

FastAPIInstrumentor.instrument_app(app, excluded_urls="metrics")
SQLAlchemyInstrumentor().instrument(engine=engine)

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
    uvicorn.run(app, host="0.0.0.0", port=8004)
