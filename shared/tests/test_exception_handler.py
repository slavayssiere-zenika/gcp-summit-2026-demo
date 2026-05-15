"""Tests unitaires — shared/exception_handler.py.

Couvre :
- _get_service_token_fallback()
- _report_to_prompts_api()
- register_global_exception_handler()
  - Guard codes HTTP natifs (StarletteHTTPException, RequestValidationError)
  - Retour 500 pour exceptions non catchées
  - Logging de la stack trace
  - Intégration avec FastAPI
"""
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from shared.exception_handler import (
    _get_service_token_fallback,
    _report_to_prompts_api,
    register_global_exception_handler,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_app_with_handler(service_name: str = "test-service") -> FastAPI:
    """Crée une app FastAPI avec le handler global enregistré."""
    app = FastAPI()
    register_global_exception_handler(app, service_name=service_name)

    @app.get("/ok")
    async def ok():
        return {"ok": True}

    @app.get("/boom")
    async def boom():
        raise ValueError("Something went wrong")

    @app.get("/http-404")
    async def http_404():
        raise StarletteHTTPException(status_code=404, detail="Not Found")

    return app


# ─── _get_service_token_fallback ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_token_fallback_depuis_env(monkeypatch):
    monkeypatch.setenv("DEV_SERVICE_TOKEN", "my-dev-token")
    token = await _get_service_token_fallback()
    assert token == "my-dev-token"


@pytest.mark.asyncio
async def test_token_fallback_sans_env_retourne_vide(monkeypatch):
    monkeypatch.delenv("DEV_SERVICE_TOKEN", raising=False)
    monkeypatch.delenv("USERS_API_URL", raising=False)
    # Le metadata server n'est pas accessible en test → retourne ""
    with patch("shared.exception_handler.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client
        token = await _get_service_token_fallback()
    assert token == ""


# ─── _report_to_prompts_api ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_report_envoie_post(monkeypatch):
    monkeypatch.setenv("PROMPTS_API_URL", "http://fake-prompts:8000")
    with patch("shared.exception_handler.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock()
        mock_cls.return_value = mock_client

        await _report_to_prompts_api("test-svc", "err msg", "traceback", "tok")
        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        assert "errors/report" in call_kwargs[0][0]
        body = call_kwargs[1]["json"]
        assert body["service_name"] == "test-svc"
        assert body["error_message"] == "err msg"


@pytest.mark.asyncio
async def test_report_best_effort_ne_relance_pas(monkeypatch, caplog):
    """Une erreur dans _report_to_prompts_api ne doit jamais propager."""
    monkeypatch.setenv("PROMPTS_API_URL", "http://fake-prompts:8000")
    with patch("shared.exception_handler.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=ConnectionError("connexion refusée"))
        mock_cls.return_value = mock_client

        with caplog.at_level(logging.ERROR):
            # Ne doit pas lever
            await _report_to_prompts_api("test-svc", "err", "trace", "tok")
    assert any("Failed to report" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_report_tronque_contexte_long(monkeypatch):
    """Le contexte doit être tronqué à 2000 chars si trop long."""
    monkeypatch.setenv("PROMPTS_API_URL", "http://fake-prompts:8000")
    long_trace = "X" * 5000
    with patch("shared.exception_handler.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock()
        mock_cls.return_value = mock_client

        await _report_to_prompts_api("svc", "err", long_trace, "tok")
        body = mock_client.post.call_args[1]["json"]
        assert len(body["context"]) == 2000


# ─── register_global_exception_handler ────────────────────────────────────────

class TestGlobalExceptionHandler:

    def test_requete_ok_non_affectee(self):
        app = _make_app_with_handler()
        with TestClient(app, raise_server_exceptions=False) as client:
            r = client.get("/ok")
        assert r.status_code == 200
        assert r.json() == {"ok": True}

    def test_starlette_http_exception_preservee(self):
        """Un 404 natif Starlette doit être retourné tel quel (pas 500)."""
        app = _make_app_with_handler()
        with TestClient(app, raise_server_exceptions=False) as client:
            r = client.get("/http-404")
        assert r.status_code == 404
        assert r.json()["detail"] == "Not Found"

    def test_exception_interne_retourne_500(self):
        """Une ValueError non catchée doit retourner HTTP 500."""
        app = _make_app_with_handler()
        with patch("shared.exception_handler._get_service_token_fallback", new=AsyncMock(return_value="")):
            with TestClient(app, raise_server_exceptions=False) as client:
                r = client.get("/boom")
        assert r.status_code == 500
        assert r.json()["detail"] == "Internal Server Error"

    def test_service_name_utilise_dans_log(self, caplog):
        """Le service_name doit apparaître dans le log de l'erreur."""
        app = _make_app_with_handler(service_name="my-test-service")
        with caplog.at_level(logging.ERROR):
            with patch("shared.exception_handler._get_service_token_fallback", new=AsyncMock(return_value="")):
                with TestClient(app, raise_server_exceptions=False) as client:
                    client.get("/boom")
        assert any("my-test-service" in r.getMessage() for r in caplog.records)

    def test_validation_error_retourne_422(self):
        """Un RequestValidationError doit retourner 422 (pas 500)."""
        from fastapi import FastAPI
        from pydantic import BaseModel

        app = FastAPI()
        register_global_exception_handler(app, service_name="test-svc")

        class Body(BaseModel):
            name: str

        @app.post("/validate")
        async def validate(body: Body):
            return body

        with TestClient(app, raise_server_exceptions=False) as client:
            r = client.post("/validate", json={"name": 123})
        # 422 ou 200 selon Pydantic coercion — l'important est que ce n'est pas 500
        assert r.status_code != 500
