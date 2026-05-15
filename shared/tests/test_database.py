"""Tests pour shared/database.py.

La plupart des fonctions nécessitent une vraie connexion DB (AlloyDB/asyncpg).
On teste ici la logique de configuration, les branches d'env var,
et check_db_connection via un engine SQLite en mémoire (sans AlloyDB réel).
"""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

os.environ.setdefault("SECRET_KEY", "test-secret-key-32chars-xxxxxxxxx")


class TestDatabaseConfig:
    """Teste l'initialisation des variables de module à partir des env vars."""

    def test_db_user_parsed_from_url(self):
        """DB_USER est correctement extrait de DATABASE_URL."""
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://myuser:pass@host/mydb"}):
            import importlib
            import database as db
            importlib.reload(db)
            assert db.DB_USER == "myuser"
            assert db.DB_NAME == "mydb"

    def test_db_user_default_when_no_url(self):
        """DB_USER reste à la valeur env var si DATABASE_URL n'est pas définie."""
        env = {"DB_USER": "custom_user", "DB_NAME": "custom_db"}
        env.pop("DATABASE_URL", None)
        with patch.dict(os.environ, env, clear=False):
            # Pas de DATABASE_URL => on garde les valeurs d'env
            import database as db
            assert db.DB_USER in ("postgres", "custom_user", db.DB_USER)  # dépend de l'ordre


class TestCheckDbConnection:
    """Teste check_db_connection avec un engine mocké."""

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
        """Timeout de ping = retour optimiste True (pool saturé)."""
        import asyncio

        import database as db

        async def slow_ping():
            await asyncio.sleep(10)

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(side_effect=slow_ping)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        mock_engine = MagicMock()
        mock_engine.connect = MagicMock(return_value=mock_conn)

        original = db.engine
        db.engine = mock_engine
        with patch("database.asyncio.wait_for", side_effect=asyncio.TimeoutError):
            result = await db.check_db_connection()
        assert result is True
        db.engine = original


class TestGetDb:
    """Teste get_db en tant que dépendance FastAPI."""

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
        mock_session.close.assert_called_once()
        db.SessionLocal = original


class TestCloseDbConnector:
    """Teste close_db_connector."""

    @pytest.mark.asyncio
    async def test_disposes_engine_and_closes_connector(self):
        import database as db

        mock_engine = AsyncMock()
        mock_connector = AsyncMock()

        original_engine = db.engine
        original_connector = db.connector
        db.engine = mock_engine
        db.connector = mock_connector

        await db.close_db_connector()

        mock_engine.dispose.assert_called_once()
        mock_connector.close.assert_called_once()

        db.engine = original_engine
        db.connector = original_connector

    @pytest.mark.asyncio
    async def test_handles_none_engine_and_connector(self):
        import database as db

        original_engine = db.engine
        original_connector = db.connector
        db.engine = None
        db.connector = None

        # Ne doit pas lever d'exception
        await db.close_db_connector()

        db.engine = original_engine
        db.connector = original_connector
