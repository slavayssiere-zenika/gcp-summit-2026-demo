import os
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.propagate import inject, extract
from opentelemetry.trace import SpanKind
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor

if os.getenv("TRACE_EXPORTER", "grpc") == "http":
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
elif os.getenv("TRACE_EXPORTER", "grpc") == "gcp":
    from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
else:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

def setup_telemetry():
    sampling_rate = float(os.getenv("TRACE_SAMPLING_RATE", "1.0"))
    sampler = ParentBased(root=TraceIdRatioBased(sampling_rate))
    provider = TracerProvider(
        resource=Resource.create({
            ResourceAttributes.SERVICE_NAME: "agent-router-api",
            ResourceAttributes.SERVICE_VERSION: "1.0.0",
        }),
        sampler=sampler
    )
    if os.getenv("TRACE_EXPORTER", "grpc") == "gcp":
        provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))
    else:
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter() if os.getenv("TRACE_EXPORTER", "grpc") == "http" else OTLPSpanExporter(insecure=True)))
    trace.set_tracer_provider(provider)

    return trace.get_tracer("agent_router_api.main")
