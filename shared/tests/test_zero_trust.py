"""Tests pour shared/tests/zero_trust.py (assert_zero_trust helper)."""
import os

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.routing import APIRoute

os.environ.setdefault("SECRET_KEY", "test-secret-key-32chars-xxxxxxxxx")

from tests.zero_trust import assert_zero_trust  # noqa: E402


def make_verify_jwt():
    def verify_jwt():
        return {"sub": "test"}
    return verify_jwt


class TestAssertZeroTrust:
    """Tests de la fonction assert_zero_trust."""

    def test_passes_when_all_routes_protected(self):
        """Toutes les routes protégées par verify_jwt → pas d'AssertionError."""
        verify_jwt = make_verify_jwt()
        app = FastAPI()
        router = APIRouter(dependencies=[Depends(verify_jwt)])

        @router.get("/items")
        def list_items():
            return []

        app.include_router(router)

        PUBLIC = {"/health", "/docs", "/openapi.json"}
        # Ne doit pas lever d'exception
        assert_zero_trust(app, PUBLIC)

    def test_fails_when_route_unprotected(self):
        """Route sans verify_jwt hors whitelist → AssertionError."""
        app = FastAPI()

        @app.get("/secret")
        def secret():
            return {"secret": True}

        PUBLIC = {"/health"}
        with pytest.raises(AssertionError) as exc_info:
            assert_zero_trust(app, PUBLIC)

        assert "/secret" in str(exc_info.value)

    def test_whitelisted_routes_are_skipped(self):
        """Routes dans la whitelist ne déclenchent pas d'alerte."""
        app = FastAPI()

        @app.get("/health")
        def health():
            return {"ok": True}

        @app.get("/metrics")
        def metrics():
            return ""

        PUBLIC = {"/health", "/metrics", "/docs", "/openapi.json", "/redoc"}
        assert_zero_trust(app, PUBLIC)

    def test_mcp_routes_are_always_skipped(self):
        """Routes /mcp/* sont toujours ignorées (sidecar interne)."""
        app = FastAPI()

        @app.get("/mcp/tools")
        def mcp_tools():
            return []

        @app.post("/mcp/call")
        def mcp_call():
            return {}

        PUBLIC = {"/health"}
        # Ne doit pas lever d'exception malgré l'absence de JWT
        assert_zero_trust(app, PUBLIC)

    def test_protected_via_inline_depends(self):
        """Route avec Depends inline (non via APIRouter) est bien détectée."""
        verify_jwt = make_verify_jwt()
        app = FastAPI()

        @app.get("/profile")
        def profile(_ = Depends(verify_jwt)):
            return {}

        PUBLIC = {"/health"}
        assert_zero_trust(app, PUBLIC)

    def test_empty_app_passes(self):
        """App vide (juste les routes FastAPI auto) ne lève pas d'erreur."""
        app = FastAPI()
        PUBLIC = {"/health", "/docs", "/openapi.json", "/redoc"}
        assert_zero_trust(app, PUBLIC)

    def test_error_message_lists_all_unprotected(self):
        """Le message d'erreur mentionne tous les endpoints non protégés."""
        app = FastAPI()

        @app.get("/a")
        def route_a():
            return {}

        @app.post("/b")
        def route_b():
            return {}

        with pytest.raises(AssertionError) as exc_info:
            assert_zero_trust(app, {"/health"})

        error = str(exc_info.value)
        assert "/a" in error
        assert "/b" in error
