"""mcp_server_utils.py — Bootstrap OTel pour les serveurs MCP (sidecar stdio + HTTP).

Résolution du nom de service (source de vérité : SERVICE_NAME) :
  - SERVICE_NAME=users_api → OTel service.name = "users-api"  (underscores → tirets)
  - SERVICE_NAME=analytics_mcp → OTel service.name = "analytics-mcp"
  - Le paramètre `service_name` de setup_mcp_tracer_provider() peut toujours
    être passé explicitement pour un override complet.
"""
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


def _resolve_mcp_service_name(service_name: str | None) -> str:
    """Détermine le nom de service OTel pour un serveur MCP.

    Priorité :
    1. Paramètre `service_name` passé explicitement.
    2. Variable OTEL_SERVICE_NAME si définie (backward compat).
    3. Variable SERVICE_NAME avec remplacement underscores → tirets.
    4. Fallback "unknown-mcp".

    Args:
        service_name: Valeur explicite passée par l'appelant (peut être None).

    Returns:
        Nom de service OTel canonique (tirets, ex: "users-api", "analytics-mcp").
    """
    if service_name:
        return service_name

    explicit_otel = os.getenv("OTEL_SERVICE_NAME")
    if explicit_otel:
        return explicit_otel

    raw = os.getenv("SERVICE_NAME", "unknown-mcp")
    return raw.replace("_", "-")


def setup_mcp_tracer_provider(service_name: str | None = None) -> trace.Tracer:
    """Initialise le TracerProvider OTel pour un serveur MCP et retourne le tracer.

    Configure également la propagation globale du context OTel.

    Args:
        service_name: Nom du service OTel. Si None, dérivé de SERVICE_NAME env var
                      (underscores remplacés par tirets). Peut aussi être lu depuis
                      OTEL_SERVICE_NAME pour la compatibilité.

    Returns:
        Tracer OTel initialisé avec le bon service.name.
    """
    resolved_name = _resolve_mcp_service_name(service_name)
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
            ResourceAttributes.SERVICE_NAME: resolved_name,
            ResourceAttributes.SERVICE_VERSION: os.getenv("APP_VERSION", "dev"),
        }),
        sampler=sampler
    )

    if os.getenv("TRACE_EXPORTER", "grpc") == "gcp":
        provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))
    else:
        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter() if os.getenv("TRACE_EXPORTER", "grpc") == "http"
                else OTLPSpanExporter(insecure=True)
            )
        )
    trace.set_tracer_provider(provider)
    return trace.get_tracer(resolved_name)


def get_mcp_trace_headers() -> dict:
    """Récupère les headers OTel (traceparent) et l'Authorization du context."""
    headers = {}
    inject(headers)
    auth = auth_header_var.get(None)
    if auth:
        headers["Authorization"] = auth
    return headers
