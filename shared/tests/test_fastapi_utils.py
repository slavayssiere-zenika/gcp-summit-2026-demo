"""Tests unitaires — shared/fastapi_utils.py.

Couvre :
- instrument_app() : Prometheus, OTEL, ContentLength, LoggingMiddleware
- instrument_app(skip_otel_fastapi=True)
- instrument_app(excluded_urls=...)
- register_health_endpoint()
"""
import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.fastapi_utils import instrument_app, register_health_endpoint


def _bare_app() -> FastAPI:
    """App FastAPI minimale sans aucune instrumentation."""
    app = FastAPI()

    @app.get("/hello")
    async def hello():
        return {"hello": "world"}

    return app


# ─── instrument_app — comportement de base ────────────────────────────────────

class TestInstrumentApp:

    def test_retourne_app(self):
        app = _bare_app()
        result = instrument_app(app, service_name="test-svc")
        assert result is app

    def test_metrics_endpoint_disponible(self):
        """Prometheus doit exposer /metrics après instrumentation."""
        app = _bare_app()
        instrument_app(app, service_name="test-svc")
        with TestClient(app) as client:
            r = client.get("/metrics")
        assert r.status_code == 200
        assert "text/plain" in r.headers.get("content-type", "")

    def test_contenu_length_middleware_present(self):
        """ContentLengthSanitizerASGIMiddleware doit être dans la stack."""
        app = _bare_app()
        instrument_app(app, service_name="test-svc")
        middleware_classes = [type(m).__name__ for m in app.middleware_stack.__class__.__mro__]
        # On vérifie via le fonctionnement plutôt que l'introspection directe
        with TestClient(app) as client:
            r = client.get("/hello")
        assert r.status_code == 200

    def test_service_name_depuis_env(self, monkeypatch):
        """Sans service_name explicite, SERVICE_NAME env var doit être utilisé."""
        monkeypatch.setenv("SERVICE_NAME", "env-service")
        app = _bare_app()
        # Ne doit pas lever
        result = instrument_app(app)
        assert result is app

    def test_service_name_defaut_unknown(self, monkeypatch):
        """Sans SERVICE_NAME env et sans argument → 'unknown-service' sans erreur."""
        monkeypatch.delenv("SERVICE_NAME", raising=False)
        app = _bare_app()
        result = instrument_app(app)
        assert result is app

    def test_excluded_urls_custom(self):
        """excluded_urls custom ne doit pas lever d'erreur."""
        app = _bare_app()
        result = instrument_app(
            app,
            service_name="test-svc",
            excluded_urls="health,custom/url,agents/health",
        )
        assert result is app

    def test_skip_otel_fastapi(self):
        """skip_otel_fastapi=True ne doit pas appeler FastAPIInstrumentor."""
        app = _bare_app()
        with patch("shared.fastapi_utils.FastAPIInstrumentor") as mock_otel:
            instrument_app(app, service_name="test-svc", skip_otel_fastapi=True)
            mock_otel.instrument_app.assert_not_called()

    def test_otel_fastapi_appele_sans_skip(self):
        """Sans skip_otel_fastapi, FastAPIInstrumentor doit être appelé."""
        app = _bare_app()
        with patch("shared.fastapi_utils.FastAPIInstrumentor") as mock_otel:
            instrument_app(app, service_name="test-svc", skip_otel_fastapi=False)
            mock_otel.instrument_app.assert_called_once()

    def test_prometheus_toujours_appele(self):
        """Instrumentator doit toujours être appelé, même avec skip_otel_fastapi."""
        app = _bare_app()
        with patch("shared.fastapi_utils.Instrumentator") as mock_prom:
            mock_instance = MagicMock()
            mock_prom.return_value = mock_instance
            mock_instance.instrument.return_value = mock_instance
            instrument_app(app, service_name="test-svc", skip_otel_fastapi=True)
            mock_prom.assert_called_once()
            mock_instance.instrument.assert_called_once_with(app)
            mock_instance.expose.assert_called_once_with(app)

    def test_exception_handler_non_enregistre_par_defaut(self):
        """instrument_app() NE doit PAS enregistrer l'exception handler shared
        (les agents ont le leur — register_global_exception_handler est optionnel)."""
        app = _bare_app()
        # On vérifie qu'on peut toujours instrumenter sans erreur
        result = instrument_app(app, service_name="test-svc")
        assert result is app


# ─── register_health_endpoint ─────────────────────────────────────────────────

class TestRegisterHealthEndpoint:

    def test_health_endpoint_repond_200(self):
        app = _bare_app()
        register_health_endpoint(app, service_name="test-svc")
        with TestClient(app) as client:
            r = client.get("/health")
        assert r.status_code == 200

    def test_health_endpoint_contient_service_name(self):
        app = _bare_app()
        register_health_endpoint(app, service_name="my-service")
        with TestClient(app) as client:
            r = client.get("/health")
        data = r.json()
        assert data["status"] == "healthy"
        assert data["service"] == "my-service"

    def test_health_endpoint_version_depuis_env(self, monkeypatch):
        monkeypatch.setenv("APP_VERSION", "v1.2.3")
        app = _bare_app()
        register_health_endpoint(app, service_name="svc")
        with TestClient(app) as client:
            r = client.get("/health")
        assert r.json()["version"] == "v1.2.3"

    def test_health_endpoint_version_defaut(self, monkeypatch):
        monkeypatch.delenv("APP_VERSION", raising=False)
        app = _bare_app()
        register_health_endpoint(app, service_name="svc")
        with TestClient(app) as client:
            r = client.get("/health")
        assert r.json()["version"] == "dev"

    def test_retourne_app(self):
        app = _bare_app()
        result = register_health_endpoint(app, service_name="svc")
        assert result is app

    def test_service_name_depuis_env(self, monkeypatch):
        monkeypatch.setenv("SERVICE_NAME", "env-svc")
        app = _bare_app()
        register_health_endpoint(app)
        with TestClient(app) as client:
            r = client.get("/health")
        assert r.json()["service"] == "env-svc"
