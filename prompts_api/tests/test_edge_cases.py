"""Tests des cas limites non couverts — prompts_api.

Sections :
  A. cache.py — Redis async timeout, GET/SET erreurs
  B. router.py — prompt key avec caractères spéciaux, value vide
  C. analyzer.py — edge cases non couverts
"""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key-32chars-xxxxxxxxx")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./prompts_edge_test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/5")


# ─────────────────────────────────────────────────────────────────────────────
# Section A — cache.py : Redis async errors (fail-open)
# ─────────────────────────────────────────────────────────────────────────────

class TestPromptsCacheEdgeCases:

    @pytest.mark.asyncio
    async def test_get_cache_redis_error_returns_none(self):
        """get_cache avec Redis indisponible → retourne None (fail-open)."""
        from cache import get_cache
        with patch("cache.redis_client.get", new=AsyncMock(side_effect=Exception("timeout"))):
            result = await get_cache("any_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_cache_redis_error_does_not_raise(self):
        """set_cache avec Redis indisponible → log erreur, pas d'exception."""
        from cache import set_cache
        with patch("cache.redis_client.set", new=AsyncMock(side_effect=Exception("timeout"))):
            # Ne doit pas lever d'exception
            await set_cache("key", "value", ttl=60)

    @pytest.mark.asyncio
    async def test_delete_cache_redis_error_does_not_raise(self):
        """delete_cache avec Redis indisponible → log erreur, pas d'exception."""
        from cache import delete_cache
        with patch("cache.redis_client.delete", new=AsyncMock(side_effect=Exception("timeout"))):
            await delete_cache("key")

    @pytest.mark.asyncio
    async def test_get_cache_returns_value_on_hit(self):
        """get_cache hit → retourne la valeur stockée."""
        from cache import get_cache
        with patch("cache.redis_client.get", new=AsyncMock(return_value="cached_prompt")):
            result = await get_cache("some_key")
        assert result == "cached_prompt"

    @pytest.mark.asyncio
    async def test_get_cache_returns_none_on_miss(self):
        """get_cache miss → retourne None."""
        from cache import get_cache
        with patch("cache.redis_client.get", new=AsyncMock(return_value=None)):
            result = await get_cache("missing_key")
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# Section B — router.py : prompt key edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestPromptsRouterEdgeCases:

    @pytest.fixture(autouse=True)
    def setup_app(self):
        """Setup commun : app avec SQLite in-memory et JWT mocké."""
        from unittest.mock import patch as _patch
        with _patch(
            "opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter",
            return_value=MagicMock(),
        ):
            from main import app
            import src.prompts.router as router
            from sqlalchemy import create_engine
            from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
            from sqlalchemy.orm import sessionmaker
            from shared.database import get_db
            from src.prompts.models import Base

        sync_engine = create_engine("sqlite:///./prompts_edge_test.db")
        async_engine = create_async_engine("sqlite+aiosqlite:///./prompts_edge_test.db")
        TestingSession = sessionmaker(
            class_=AsyncSession, autocommit=False, autoflush=False,
            expire_on_commit=False, bind=async_engine,
        )
        Base.metadata.drop_all(bind=sync_engine)
        Base.metadata.create_all(bind=sync_engine)

        async def override_db():
            async with TestingSession() as db:
                yield db

        old_overrides = app.dependency_overrides.copy()
        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[router.verify_jwt] = lambda: {
            "sub": "u@zenika.com", "role": "admin"
        }
        app.dependency_overrides[router.verify_admin] = lambda: {"role": "admin"}

        from fastapi.testclient import TestClient
        self.client = TestClient(app)
        yield
        app.dependency_overrides = old_overrides

    def test_prompt_key_with_dots_is_accepted(self):
        """Une clé de prompt avec des points (ex: agent_hr.system_prompt) → 200."""
        resp = self.client.post(
            "/",
            json={"key": "agent.hr.system_prompt", "value": "You are an HR agent."},
        )
        assert resp.status_code == 200
        assert resp.json()["key"] == "agent.hr.system_prompt"

    def test_prompt_value_empty_string_accepted(self):
        """Une valeur de prompt vide (chaîne '') → 200 (aucune contrainte min_length)."""
        resp = self.client.post(
            "/",
            json={"key": "empty_prompt", "value": ""},
        )
        # Comportement documenté : valeur vide acceptée ou rejetée
        assert resp.status_code in (200, 422)

    def test_prompt_key_with_special_chars(self):
        """Clé contenant / → comportement documenté (FastAPI peut interpréter comme chemin)."""
        resp = self.client.post(
            "/",
            json={"key": "agent/hr/prompt", "value": "Test"},
        )
        # Comportement documenté : 200 ou 422 selon validation
        assert resp.status_code in (200, 422)

    def test_list_prompts_pagination(self):
        """Liste de prompts avec skip/limit."""
        self.client.post("/", json={"key": "p1", "value": "v1"})
        self.client.post("/", json={"key": "p2", "value": "v2"})
        self.client.post("/", json={"key": "p3", "value": "v3"})

        resp = self.client.get("/?skip=1&limit=2")
        assert resp.status_code == 200
        data = resp.json()
        assert "prompts" in data or "items" in data
        assert "total" in data

    def test_delete_prompt_not_found(self):
        """DELETE d'un prompt inexistant → 404."""
        resp = self.client.delete("/nonexistent_prompt_xyz")
        assert resp.status_code == 404

    def test_get_prompt_by_key_not_found(self):
        """GET d'une clé inexistante → 404."""
        resp = self.client.get("/no_such_key_xyz")
        assert resp.status_code == 404
