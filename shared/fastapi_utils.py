"""Bootstrap FastAPI standardisé pour les APIs data Zenika.

Usage minimal (dans main.py) :
    from shared.fastapi_utils import instrument_app, setup_tracing
    setup_tracing(service_name="my-api")
    instrument_app(app)

Ce que fait `instrument_app` :
1. Prometheus Instrumentator (expose /metrics)
2. FastAPI OTEL Instrumentator (exclut health/metrics/ready/version)
3. Middleware ContentLength sanitizer
4. Middleware LoggingMiddleware JSON structuré
5. Enregistrement de l'exception handler global (via register_global_exception_handler)

Ce que fait `setup_tracing` :
1. Résout l'exportateur OTEL selon TRACE_EXPORTER (grpc|http|gcp)
2. Configure le TracerProvider avec sampler TRACE_SAMPLING_RATE
3. Enregistre le provider global (trace.set_tracer_provider)

Résolution du nom de service (source de vérité : SERVICE_NAME) :
  - SERVICE_NAME=users_api    → OTEL service.name = "users-api"
  - SERVICE_NAME=agent_hr_api → OTEL service.name = "agent-hr-api"
  - OTEL_SERVICE_NAME peut toujours être défini explicitement pour un override complet.

Note : Le /health endpoint n'est PAS ajouté automatiquement car certains services
ont des health checks enrichis (BQ ping, DB ping, etc.). Utilisez
`register_health_endpoint(app, service_name)` si vous n'en avez pas de custom.
"""
import os

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response as StarletteResponse

from shared.exception_handler import register_global_exception_handler
from shared.middlewares import ContentLengthSanitizerASGIMiddleware
from shared.observability import LoggingMiddleware

# URLs exclues des instrumentations (health-check / readiness / métriques)
_EXCLUDED_URLS = "health,ready,metrics,version,api/health"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware défensif — injecte des headers de sécurité HTTP sur chaque réponse.

    Protège contre :
    - Clickjacking          : X-Frame-Options: DENY
    - MIME sniffing         : X-Content-Type-Options: nosniff
    - XSS (navigateurs old) : X-XSS-Protection: 1; mode=block
    - Referrer leakage      : Referrer-Policy: strict-origin-when-cross-origin

    Appliqué automatiquement par instrument_app() — ne pas ajouter manuellement.
    """

    async def dispatch(
        self, request: StarletteRequest, call_next
    ) -> StarletteResponse:
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


def _resolve_otel_service_name() -> str:
    """Détermine le nom de service pour OpenTelemetry.

    Priorité :
    1. Variable OTEL_SERVICE_NAME si définie explicitement (backward compat / override).
    2. Variable SERVICE_NAME avec remplacement underscores → tirets
       (ex: agent_router_api → agent-router-api — convention OTel standard).
    3. Fallback "unknown-service".

    Le SDK OTel Python lit OTEL_SERVICE_NAME automatiquement à l'init du provider.
    Cette fonction garantit qu'il est toujours défini AVANT l'instrumentation,
    permettant de supprimer OTEL_SERVICE_NAME des fichiers de configuration
    (docker-compose, Terraform) en faveur de SERVICE_NAME.

    Returns:
        Nom de service OTel avec tirets (convention OTel).
    """
    explicit = os.getenv("OTEL_SERVICE_NAME")
    if explicit:
        return explicit

    service_name = os.getenv("SERVICE_NAME", "unknown-service")
    otel_name = service_name.replace("_", "-")

    # Injecte dans l'environnement pour que le SDK OTel le lise automatiquement.
    os.environ["OTEL_SERVICE_NAME"] = otel_name
    return otel_name


def instrument_app(
    app: FastAPI,
    service_name: str | None = None,
    excluded_urls: str | None = None,
    skip_otel_fastapi: bool = False,
    register_exception_handler: bool = True,
) -> FastAPI:
    """Configure les instruments communs obligatoires (AGENTS.md checklist §global).

    Doit être appelé APRÈS la création de l'app FastAPI et de son lifespan,
    mais AVANT l'enregistrement des routers (pour que les middlewares soient
    correctement ordonnés).

    Args:
        app: L'instance FastAPI à instrumenter.
        service_name: Nom du service pour les logs et rapports d'erreur.
                      Défaut : variable d'env SERVICE_NAME, ou "unknown-service".
        excluded_urls: URLs exclues de l'instrumentation OTEL (défaut: health,ready,metrics,version,api/health).
                       Permet aux agents d'ajouter leurs URLs spécifiques (ex: "health,health/agents,...").
        skip_otel_fastapi: Si True, n'applique PAS FastAPIInstrumentor — utile quand l'agent
                           configure lui-même l'instrumentation avec un tracer_provider custom
                           (ex: agent_missions_api.setup_tracing()).
        register_exception_handler: Si True (défaut), enregistre le global exception handler
                                    (fail-fast + rapport prompts_api). Passer False uniquement
                                    pour les agents qui ont leur propre handler (agent_commons).

    Returns:
        L'instance app modifiée (pour le chaînage).
    """
    # Résolution du nom de service — garantit que OTEL_SERVICE_NAME est injecté avant
    # l'instrumentation, même si la variable n'est pas définie dans l'environnement.
    _resolve_otel_service_name()

    _service_name = service_name or os.getenv("SERVICE_NAME", "unknown-service")
    _excluded = excluded_urls or _EXCLUDED_URLS

    # 1. Prometheus — expose /metrics
    Instrumentator().instrument(app).expose(app)

    # 2. OTEL FastAPI — trace les requêtes HTTP entrantes (sauf si tracer_provider custom)
    if not skip_otel_fastapi:
        FastAPIInstrumentor.instrument_app(app, excluded_urls=_excluded)

    # 3. Headers de sécurité HTTP (clickjacking, MIME sniffing, XSS, referrer leakage)
    app.add_middleware(SecurityHeadersMiddleware)

    # 4. Sanitise les Content-Length vides (curl, proxies)
    app.add_middleware(ContentLengthSanitizerASGIMiddleware)

    # 5. Logging JSON structuré avec trace context OTEL
    app.add_middleware(LoggingMiddleware)

    # 6. Exception handler global (fail-fast + rapport prompts_api)
    # Les agents passent register_exception_handler=False — ils ont agent_commons.
    if register_exception_handler:
        register_global_exception_handler(app, _service_name)

    return app


def register_health_endpoint(app: FastAPI, service_name: str | None = None) -> FastAPI:
    """Ajoute un endpoint /health minimal si le service n'en a pas de custom.

    Pour les services avec un health enrichi (ping BQ, ping DB, etc.),
    NE PAS utiliser cette fonction — définissez votre propre @app.get("/health").

    Args:
        app: L'instance FastAPI cible.
        service_name: Nom du service retourné dans la réponse JSON.
    """
    _svc = service_name or os.getenv("SERVICE_NAME", "unknown-service")
    _version = os.getenv("APP_VERSION", "dev")

    @app.get("/health", tags=["ops"], include_in_schema=False)
    async def _health():
        return {"status": "healthy", "service": _svc, "version": _version}

    return app


def setup_tracing(service_name: str, app_version: str | None = None) -> None:
    """Configure le TracerProvider OTel pour le service courant.

    Factorise le bloc TracerProvider commun à drive_api, users_api et competencies_api.
    Doit être appelé au niveau module dans main.py, AVANT la création de l'app FastAPI.

    Variables d'environnement :
        TRACE_EXPORTER     : "grpc" (défaut) | "http" | "gcp"
        TRACE_SAMPLING_RATE: float entre 0.0 et 1.0 (défaut 1.0 — tout tracer)
        APP_VERSION        : Version de l'application (défaut "dev")

    Args:
        service_name: Nom du service (ex: "drive-api") pour les attributs de ressource.
        app_version:  Version applicative. Si None, lit APP_VERSION ou utilise "dev".

    Example (dans main.py) :
        from shared.fastapi_utils import setup_tracing, instrument_app
        setup_tracing(service_name="drive-api")
        app = FastAPI(...)
        instrument_app(app)
    """
    from opentelemetry import trace as _trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
    from opentelemetry.semconv.resource import ResourceAttributes

    _version = app_version or os.getenv("APP_VERSION", "dev")
    _exporter_type = os.getenv("TRACE_EXPORTER", "grpc")

    # Résolution de l'exportateur selon TRACE_EXPORTER
    if _exporter_type == "http":
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        exporter = OTLPSpanExporter()
    elif _exporter_type == "gcp":
        from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
        exporter = None  # CloudTrace gère son propre processor
        cloud_exporter = CloudTraceSpanExporter()
    else:
        # grpc (défaut)
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        exporter = OTLPSpanExporter(insecure=True)

    sampling_rate = float(os.getenv("TRACE_SAMPLING_RATE", "1.0"))
    sampler = ParentBased(root=TraceIdRatioBased(sampling_rate))

    provider = TracerProvider(
        resource=Resource.create({
            ResourceAttributes.SERVICE_NAME: service_name,
            ResourceAttributes.SERVICE_VERSION: _version,
        }),
        sampler=sampler,
    )

    if _exporter_type == "gcp":
        provider.add_span_processor(BatchSpanProcessor(cloud_exporter))
    else:
        provider.add_span_processor(BatchSpanProcessor(exporter))

    _trace.set_tracer_provider(provider)
