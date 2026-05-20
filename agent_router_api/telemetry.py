import os

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.semconv.resource import ResourceAttributes

try:
    from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
    _CLOUD_TRACE_AVAILABLE = True
except ImportError:
    _CLOUD_TRACE_AVAILABLE = False

if os.getenv("TRACE_EXPORTER", "grpc") == "http":
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
else:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter


def setup_telemetry():
    sampling_rate = float(os.getenv("TRACE_SAMPLING_RATE", "1.0"))
    sampler = ParentBased(root=TraceIdRatioBased(sampling_rate))
    provider = TracerProvider(
        resource=Resource.create({
            ResourceAttributes.SERVICE_NAME: "agent-router-api",
            ResourceAttributes.SERVICE_VERSION: os.getenv("APP_VERSION", "dev"),
        }),
        sampler=sampler
    )
    trace_exporter_type = os.getenv("TRACE_EXPORTER", "grpc")
    if trace_exporter_type == "gcp" and _CLOUD_TRACE_AVAILABLE:
        provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))
    elif trace_exporter_type == "http":
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    else:
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(insecure=True)))
    trace.set_tracer_provider(provider)

    return trace.get_tracer("agent_router_api.main")
