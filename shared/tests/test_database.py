"""Tests pour shared/database.py — injection des valeurs configurables.

Couvre :
- Parsing DATABASE_URL → DB_USER, DB_NAME
- Rewrite postgresql:// → postgresql+asyncpg://
- Injection de DB_POOL_SIZE, DB_MAX_OVERFLOW dans SQLAlchemy
- Valeurs fixées : pool_pre_ping=True, pool_recycle=1800
- check_db_connection / get_db / close_db_connector (mocks)
"""
import importlib
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key-32chars-xxxxxxxxx")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def reload_db(**env_overrides):
    """Recharge le module database avec les env vars spécifiées."""
    with patch.dict(os.environ, env_overrides):
        import database as db
        importlib.reload(db)
        return db


# ─── DB_USER / DB_NAME : parsing depuis DATABASE_URL ─────────────────────────

class TestDatabaseUrlParsing:
    """Vérifie que DB_USER et DB_NAME sont extraits de DATABASE_URL."""

    def test_extracts_user_and_name_from_standard_postgresql_url(self):
        db = reload_db(DATABASE_URL="postgresql://alice:s3cr3t@db-host:5432/myapp_db")
        assert db.DB_USER == "alice"
        assert db.DB_NAME == "myapp_db"

    def test_extracts_user_from_asyncpg_url(self):
        db = reload_db(DATABASE_URL="postgresql+asyncpg://bob:pass@host/analytics")
        assert db.DB_USER == "bob"
        assert db.DB_NAME == "analytics"

    def test_url_without_password_parsed_correctly(self):
        db = reload_db(DATABASE_URL="postgresql://nopassuser@localhost/testdb")
        assert db.DB_USER == "nopassuser"
        assert db.DB_NAME == "testdb"

    def test_url_query_params_not_included_in_db_name(self):
        db = reload_db(DATABASE_URL="postgresql://user:pass@host/mydb?sslmode=require")
        assert db.DB_NAME == "mydb"

    def test_db_user_defaults_to_postgres_when_url_missing(self):
        env = dict(os.environ)
        env.pop("DATABASE_URL", None)
        env.pop("DB_USER", None)
        with patch.dict(os.environ, env, clear=True):
            import database as db
            importlib.reload(db)
            assert db.DB_USER == "postgres"

    def test_db_name_defaults_to_mydb_when_url_missing(self):
        env = dict(os.environ)
        env.pop("DATABASE_URL", None)
        env.pop("DB_NAME", None)
        with patch.dict(os.environ, env, clear=True):
            import database as db
            importlib.reload(db)
            assert db.DB_NAME == "mydb"

    def test_db_user_overridable_via_env_var(self):
        env = dict(os.environ)
        env.pop("DATABASE_URL", None)
        env["DB_USER"] = "custom_pg_user"
        with patch.dict(os.environ, env, clear=True):
            import database as db
            importlib.reload(db)
            assert db.DB_USER == "custom_pg_user"


# ─── DATABASE_URL : rewrite postgresql → asyncpg ─────────────────────────────

class TestDatabaseUrlRewrite:
    """Vérifie que postgresql:// est réécrit en postgresql+asyncpg://."""

    @pytest.mark.asyncio
    async def test_plain_postgresql_rewritten_to_asyncpg(self):
        captured = {}

        def mock_create_engine(url, **kwargs):
            captured["url"] = str(url)
            return MagicMock()

        db = reload_db(DATABASE_URL="postgresql://user:pass@host/db", USE_IAM_AUTH="false")
        with patch("database.create_async_engine", side_effect=mock_create_engine), \
             patch("database.sessionmaker"):
            await db.init_db_connector()

        assert captured["url"].startswith("postgresql+asyncpg://")

    @pytest.mark.asyncio
    async def test_asyncpg_url_not_double_rewritten(self):
        captured = {}

        def mock_create_engine(url, **kwargs):
            captured["url"] = str(url)
            return MagicMock()

        db = reload_db(
            DATABASE_URL="postgresql+asyncpg://user:pass@host/db",
            USE_IAM_AUTH="false",
        )
        with patch("database.create_async_engine", side_effect=mock_create_engine), \
             patch("database.sessionmaker"):
            await db.init_db_connector()

        assert captured["url"] == "postgresql+asyncpg://user:pass@host/db"


# ─── DB_POOL_SIZE / DB_MAX_OVERFLOW ──────────────────────────────────────────

class TestPoolParams:
    """Vérifie que les params de pool sont correctement injectés dans SQLAlchemy."""

    def _capture_engine(self):
        captured = {}

        def mock_create_engine(url, **kwargs):
            captured["kwargs"] = kwargs
            return MagicMock()

        return captured, mock_create_engine

    @pytest.mark.asyncio
    async def test_default_pool_size_is_10(self):
        captured, mock_create_engine = self._capture_engine()
        env = {"DATABASE_URL": "postgresql+asyncpg://u:p@h/db", "USE_IAM_AUTH": "false"}
        env.pop("DB_POOL_SIZE", None)
        db = reload_db(**env)
        with patch("database.create_async_engine", side_effect=mock_create_engine), \
             patch("database.sessionmaker"):
            await db.init_db_connector()
        assert captured["kwargs"].get("pool_size") == 10

    @pytest.mark.asyncio
    async def test_default_max_overflow_is_20(self):
        captured, mock_create_engine = self._capture_engine()
        env = {"DATABASE_URL": "postgresql+asyncpg://u:p@h/db", "USE_IAM_AUTH": "false"}
        db = reload_db(**env)
        with patch("database.create_async_engine", side_effect=mock_create_engine), \
             patch("database.sessionmaker"):
            await db.init_db_connector()
        assert captured["kwargs"].get("max_overflow") == 20

    @pytest.mark.asyncio
    async def test_custom_pool_size_injected(self):
        captured, mock_create_engine = self._capture_engine()
        db = reload_db(DATABASE_URL="postgresql+asyncpg://u:p@h/db", USE_IAM_AUTH="false")
        # Les getenv DB_POOL_SIZE/DB_MAX_OVERFLOW sont lus AU MOMENT de l'appel
        # → le patch doit entourer l'appel à init_db_connector
        with patch.dict(os.environ, {"DB_POOL_SIZE": "3", "DB_MAX_OVERFLOW": "7"}), \
             patch("database.create_async_engine", side_effect=mock_create_engine), \
             patch("database.sessionmaker"):
            await db.init_db_connector()
        assert captured["kwargs"].get("pool_size") == 3
        assert captured["kwargs"].get("max_overflow") == 7

    @pytest.mark.asyncio
    async def test_pool_pre_ping_always_true(self):
        captured, mock_create_engine = self._capture_engine()
        db = reload_db(DATABASE_URL="postgresql+asyncpg://u:p@h/db", USE_IAM_AUTH="false")
        with patch("database.create_async_engine", side_effect=mock_create_engine), \
             patch("database.sessionmaker"):
            await db.init_db_connector()
        assert captured["kwargs"].get("pool_pre_ping") is True

    @pytest.mark.asyncio
    async def test_pool_recycle_is_1800(self):
        captured, mock_create_engine = self._capture_engine()
        db = reload_db(DATABASE_URL="postgresql+asyncpg://u:p@h/db", USE_IAM_AUTH="false")
        with patch("database.create_async_engine", side_effect=mock_create_engine), \
             patch("database.sessionmaker"):
            await db.init_db_connector()
        assert captured["kwargs"].get("pool_recycle") == 1800


# ─── check_db_connection ─────────────────────────────────────────────────────

class TestCheckDbConnection:
    @pytest.mark.asyncio
    async def test_returns_false_when_engine_is_none(self):
        import database as db
        original = db.engine
        db.engine = None
        result = await db.check_db_connection()
        assert result is False
        db.engine = original

    @pytest.mark.asyncio
    async def test_returns_true_on_successful_ping(self):
        import database as db
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value=None)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)
        mock_engine = MagicMock()
        mock_engine.connect = MagicMock(return_value=mock_conn)
        original = db.engine
        db.engine = mock_engine
        result = await db.check_db_connection()
        assert result is True
        db.engine = original

    @pytest.mark.asyncio
    async def test_returns_false_on_connection_error(self):
        import database as db
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(side_effect=Exception("DB unreachable"))
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)
        mock_engine = MagicMock()
        mock_engine.connect = MagicMock(return_value=mock_conn)
        original = db.engine
        db.engine = mock_engine
        result = await db.check_db_connection()
        assert result is False
        db.engine = original

    @pytest.mark.asyncio
    async def test_returns_true_optimistically_on_timeout(self):
        import asyncio
        import database as db
        mock_engine = MagicMock()
        original = db.engine
        db.engine = mock_engine
        with patch("database.asyncio.wait_for", side_effect=asyncio.TimeoutError):
            result = await db.check_db_connection()
        assert result is True
        db.engine = original


# ─── get_db / close_db_connector ─────────────────────────────────────────────

class TestGetDb:
    @pytest.mark.asyncio
    async def test_get_db_yields_session_and_closes(self):
        import database as db
        mock_session = AsyncMock()
        mock_session.close = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session_factory = MagicMock(return_value=mock_session)
        original = db.SessionLocal
        db.SessionLocal = mock_session_factory
        sessions = []
        async for session in db.get_db():
            sessions.append(session)
        assert len(sessions) == 1
        mock_session.__aexit__.assert_called_once()
        db.SessionLocal = original


class TestCloseDbConnector:
    @pytest.mark.asyncio
    async def test_disposes_engine_and_closes_connector(self):
        import database as db
        mock_engine = AsyncMock()
        mock_connector = AsyncMock()
        original_engine, original_connector = db.engine, db.connector
        db.engine = mock_engine
        db.connector = mock_connector
        await db.close_db_connector()
        mock_engine.dispose.assert_called_once()
        mock_connector.close.assert_called_once()
        db.engine, db.connector = original_engine, original_connector

    @pytest.mark.asyncio
    async def test_handles_none_engine_and_connector(self):
        import database as db
        original_engine, original_connector = db.engine, db.connector
        db.engine = None
        db.connector = None
        await db.close_db_connector()
        db.engine, db.connector = original_engine, original_connector
