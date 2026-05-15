"""Bootstrap FastAPI standardisé pour les APIs data Zenika.

Usage minimal (dans main.py) :
    from shared.fastapi_utils import instrument_app
    instrument_app(app)

Ce que fait `instrument_app` :
1. Prometheus Instrumentator (expose /metrics)
2. FastAPI OTEL Instrumentator (exclut health/metrics/ready/version)
3. Middleware ContentLength sanitizer
4. Middleware LoggingMiddleware JSON structuré
5. Enregistrement de l'exception handler global (via register_global_exception_handler)

Note : Le /health endpoint n'est PAS ajouté automatiquement car certains services
ont des health checks enrichis (BQ ping, DB ping, etc.). Utilisez
`register_health_endpoint(app, service_name)` si vous n'en avez pas de custom.
"""
import os

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_fastapi_instrumentator import Instrumentator

from shared.exception_handler import register_global_exception_handler
from shared.middlewares import ContentLengthSanitizerASGIMiddleware
from shared.observability import LoggingMiddleware

# URLs exclues des instrumentations (health-check / readiness / métriques)
_EXCLUDED_URLS = "health,ready,metrics,version,api/health"


def instrument_app(
    app: FastAPI,
    service_name: str | None = None,
    excluded_urls: str | None = None,
    skip_otel_fastapi: bool = False,
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

    Returns:
        L'instance app modifiée (pour le chaînage).
    """
    _service_name = service_name or os.getenv("SERVICE_NAME", "unknown-service")
    _excluded = excluded_urls or _EXCLUDED_URLS

    # 1. Prometheus — expose /metrics
    Instrumentator().instrument(app).expose(app)

    # 2. OTEL FastAPI — trace les requêtes HTTP entrantes (sauf si tracer_provider custom)
    if not skip_otel_fastapi:
        FastAPIInstrumentor.instrument_app(app, excluded_urls=_excluded)

    # 3. Sanitise les Content-Length vides (curl, proxies)
    app.add_middleware(ContentLengthSanitizerASGIMiddleware)

    # 4. Logging JSON structuré avec trace context OTEL
    app.add_middleware(LoggingMiddleware)

    # 5. Exception handler global (fail-fast + rapport prompts_api)
    # NOTE : les agents ne l'utilisent PAS — ils ont leur propre
    # agent_commons.exception_handler.make_global_exception_handler()
    # Appeler register_global_exception_handler() séparément si nécessaire.

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
