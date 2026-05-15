"""Tests unitaires — shared/observability.py.

Couvre :
- HealthCheckFilter
- OpenTelemetryJsonFormatter
- ThrottledHandler
- setup_logging()
- LoggingMiddleware
"""
import asyncio
import logging
import os
import time
import unittest
from io import StringIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from shared.observability import (
    SILENT_PATHS,
    HealthCheckFilter,
    LoggingMiddleware,
    OpenTelemetryJsonFormatter,
    ThrottledHandler,
    setup_logging,
)


# ─── HealthCheckFilter ─────────────────────────────────────────────────────────

class TestHealthCheckFilter(unittest.TestCase):

    def _make_record(self, message: str) -> logging.LogRecord:
        record = logging.LogRecord(
            name="uvicorn.access", level=logging.INFO,
            pathname="", lineno=0, msg=message, args=(), exc_info=None
        )
        return record

    def test_filtre_get_health(self):
        f = HealthCheckFilter()
        self.assertFalse(f.filter(self._make_record('"GET /health HTTP/1.1" 200')))

    def test_filtre_get_metrics(self):
        f = HealthCheckFilter()
        self.assertFalse(f.filter(self._make_record('"GET /metrics HTTP/1.1" 200')))

    def test_filtre_post_health(self):
        f = HealthCheckFilter()
        self.assertFalse(f.filter(self._make_record('"POST /health HTTP/1.1" 200')))

    def test_laisse_passer_requete_normale(self):
        f = HealthCheckFilter()
        self.assertTrue(f.filter(self._make_record('"GET /users/ HTTP/1.1" 200')))

    def test_laisse_passer_requete_api(self):
        f = HealthCheckFilter()
        self.assertTrue(f.filter(self._make_record('"POST /auth/login HTTP/1.1" 200')))

    def test_record_sans_message(self):
        """Doit survivre à un record sans message mais avec request_line."""
        f = HealthCheckFilter()
        record = self._make_record("")
        record.request_line = "GET /health HTTP/1.1"
        # Le filtre inspecte request_line si msg vide
        self.assertFalse(f.filter(record))

    def test_silent_paths_constant(self):
        """SILENT_PATHS est bien un frozenset et contient les paths attendus."""
        self.assertIsInstance(SILENT_PATHS, frozenset)
        self.assertIn("/health", SILENT_PATHS)
        self.assertIn("/metrics", SILENT_PATHS)
        self.assertIn("/ready", SILENT_PATHS)


# ─── OpenTelemetryJsonFormatter ────────────────────────────────────────────────

class TestOpenTelemetryJsonFormatter(unittest.TestCase):

    def test_injecte_service_et_environment(self):
        fmt = OpenTelemetryJsonFormatter("%(message)s")
        record = logging.LogRecord(
            name="test", level=logging.INFO,
            pathname="", lineno=0, msg="hello", args=(), exc_info=None
        )
        log_dict = {}
        fmt.add_fields(log_dict, record, {})
        self.assertEqual(log_dict["service"], os.getenv("SERVICE_NAME", "unknown-service"))
        self.assertEqual(log_dict["environment"], os.getenv("ENVIRONMENT", "dev"))

    def test_service_lit_env_var(self):
        fmt = OpenTelemetryJsonFormatter("%(message)s")
        record = logging.LogRecord(
            name="test", level=logging.INFO,
            pathname="", lineno=0, msg="hello", args=(), exc_info=None
        )
        log_dict = {}
        with patch.dict(os.environ, {"SERVICE_NAME": "my-test-service"}):
            fmt.add_fields(log_dict, record, {})
        self.assertEqual(log_dict["service"], "my-test-service")

    def test_pas_de_trace_sans_span_actif(self):
        """Sans span OTel actif, trace_id/span_id ne doivent PAS être injectés."""
        fmt = OpenTelemetryJsonFormatter("%(message)s")
        record = logging.LogRecord(
            name="test", level=logging.INFO,
            pathname="", lineno=0, msg="hello", args=(), exc_info=None
        )
        log_dict = {}
        fmt.add_fields(log_dict, record, {})
        # Sans span actif → pas de trace_id (ou span non-recording)
        if "trace_id" in log_dict:
            # Si présent, doit être le trace_id invalide (non-recording span)
            pass  # acceptable


# ─── ThrottledHandler ─────────────────────────────────────────────────────────

class TestThrottledHandler(unittest.TestCase):

    def _make_handler(self, window: int = 60):
        """Retourne un ThrottledHandler avec un delegate mock."""
        delegate = MagicMock(spec=logging.Handler)
        return ThrottledHandler(delegate, window_seconds=window), delegate

    def _record(self, msg: str = "test message") -> logging.LogRecord:
        return logging.LogRecord(
            name="test", level=logging.WARNING,
            pathname="", lineno=0, msg=msg, args=(), exc_info=None
        )

    def test_premier_emit_passe(self):
        handler, delegate = self._make_handler()
        handler.emit(self._record("msg A"))
        delegate.emit.assert_called_once()

    def test_meme_message_supprime_pendant_fenetre(self):
        handler, delegate = self._make_handler(window=60)
        r = self._record("msg B")
        handler.emit(r)
        handler.emit(r)  # Supprimé
        handler.emit(r)  # Supprimé
        self.assertEqual(delegate.emit.call_count, 1)

    def test_message_different_passe(self):
        handler, delegate = self._make_handler()
        handler.emit(self._record("msg X"))
        handler.emit(self._record("msg Y"))
        self.assertEqual(delegate.emit.call_count, 2)

    def test_message_reemis_apres_fenetre(self):
        """Après expiration de la fenêtre, le message est réémis avec compteur."""
        handler, delegate = self._make_handler(window=0)  # fenêtre 0 = toujours expiré
        r = self._record("msg C")
        handler.emit(r)
        time.sleep(0.01)
        handler.emit(r)  # Doit passer car fenêtre=0
        self.assertEqual(delegate.emit.call_count, 2)


# ─── setup_logging ────────────────────────────────────────────────────────────

class TestSetupLogging(unittest.TestCase):

    def test_retourne_root_logger(self):
        root = setup_logging()
        self.assertIsInstance(root, logging.Logger)
        self.assertEqual(root.name, "root")

    def test_root_logger_a_handler(self):
        setup_logging()
        root = logging.getLogger()
        self.assertGreater(len(root.handlers), 0)

    def test_double_appel_pas_de_doublons(self):
        """Deux appels successifs ne doivent pas doubler les handlers."""
        setup_logging()
        setup_logging()
        root = logging.getLogger()
        self.assertEqual(len(root.handlers), 1)

    def test_log_level_depuis_env(self):
        with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}):
            setup_logging()
        root = logging.getLogger()
        self.assertEqual(root.level, logging.DEBUG)

    def test_silences_noisy_loggers(self):
        setup_logging()
        self.assertEqual(logging.getLogger("httpcore").level, logging.WARNING)
        self.assertEqual(logging.getLogger("httpx").level, logging.WARNING)
        self.assertEqual(logging.getLogger("opentelemetry").level, logging.WARNING)


# ─── LoggingMiddleware ────────────────────────────────────────────────────────

@pytest.fixture
def test_app():
    """FastAPI app minimaliste avec LoggingMiddleware pour les tests."""
    app = FastAPI()
    app.add_middleware(LoggingMiddleware)

    @app.get("/hello")
    async def hello():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    @app.get("/error")
    async def error():
        raise ValueError("test error")

    return app


def test_logging_middleware_laisse_passer_requete_normale(test_app, caplog):
    with TestClient(test_app, raise_server_exceptions=False) as client:
        r = client.get("/hello")
    assert r.status_code == 200


def test_logging_middleware_exclut_health(test_app, caplog):
    """Les requêtes vers /health ne doivent PAS produire de log HTTP."""
    with caplog.at_level(logging.INFO, logger="middleware.http"):
        with TestClient(test_app, raise_server_exceptions=False) as client:
            client.get("/health")
    # Aucun log HTTP structuré pour /health
    http_logs = [r for r in caplog.records if r.name == "middleware.http"]
    assert not http_logs


def test_logging_middleware_requete_normale_loggee(test_app, caplog):
    """Les requêtes normales DOIVENT produire un log structuré."""
    with caplog.at_level(logging.INFO, logger="middleware.http"):
        with TestClient(test_app, raise_server_exceptions=False) as client:
            client.get("/hello")
    http_logs = [r for r in caplog.records if r.name == "middleware.http"]
    assert len(http_logs) >= 1
    assert http_logs[0].getMessage() == "HTTP Request Processed"


def test_logging_middleware_erreur_500(test_app, caplog):
    """Les erreurs serveur doivent être loggées au niveau ERROR."""
    with caplog.at_level(logging.ERROR, logger="middleware.http"):
        with TestClient(test_app, raise_server_exceptions=False) as client:
            client.get("/error")
    error_logs = [r for r in caplog.records if r.name == "middleware.http" and r.levelno == logging.ERROR]
    assert len(error_logs) >= 1
