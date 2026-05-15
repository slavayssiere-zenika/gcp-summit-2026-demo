import os
from opentelemetry import propagate, trace
from opentelemetry.propagate import inject
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from shared.auth.context import auth_header_var


def setup_mcp_tracer_provider(service_name: str) -> trace.Tracer:
    """Initialise le TracerProvider OTel pour un serveur MCP et retourne le tracer.
    Configure également la propagation globale du context OTel."""
    propagate.set_global_textmap(TraceContextTextMapPropagator())

    if os.getenv("TRACE_EXPORTER", "grpc") == "http":
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    elif os.getenv("TRACE_EXPORTER", "grpc") == "gcp":
        from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
    else:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

    # Clamp sampling_rate to [0.0, 1.0] — TraceIdRatioBased lève ValueError sinon
    sampling_rate = max(0.0, min(1.0, float(os.getenv("TRACE_SAMPLING_RATE", "1.0"))))
    sampler = ParentBased(root=TraceIdRatioBased(sampling_rate))
    provider = TracerProvider(
        resource=Resource.create({
            ResourceAttributes.SERVICE_NAME: service_name,
            ResourceAttributes.SERVICE_VERSION: os.getenv("APP_VERSION", "dev"),
        }),
        sampler=sampler
    )

    if os.getenv("TRACE_EXPORTER", "grpc") == "gcp":
        provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))
    else:
        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter() if os.getenv("TRACE_EXPORTER", "grpc") == "http" else OTLPSpanExporter(insecure=True)
            )
        )
    trace.set_tracer_provider(provider)
    return trace.get_tracer(service_name)


def get_mcp_trace_headers() -> dict:
    """Récupère les headers OTel (traceparent) et l'Authorization du context."""
    headers = {}
    inject(headers)
    auth = auth_header_var.get(None)
    if auth:
        headers["Authorization"] = auth
    return headers
