"""
Fixtures Testcontainers pour les tests d'intégration de competencies_api.

competencies_api utilise :
- PostgreSQL : ON CONFLICT DO NOTHING dans assignments_router.py:38
- Redis : cache compétences (module-level → refactorisé en lazy init)
"""
import os

import pytest
from sqlalchemy import create_engine
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer


@pytest.fixture(scope="session")
def postgres_container():
    """Démarre un conteneur PostgreSQL 16 pour toute la session."""
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture(scope="session")
def redis_container():
    """Démarre un conteneur Redis 7 pour toute la session."""
    with RedisContainer("redis:7-alpine") as r:
        yield r


@pytest.fixture(scope="session")
def integration_env(postgres_container, redis_container):
    """Injecte les URLs dynamiques — sauvegarde et restaure l'env original après la session."""
    _orig_db_url = os.environ.get("DATABASE_URL")
    _orig_redis_url = os.environ.get("REDIS_URL")

    pg_sync_url = postgres_container.get_connection_url()
    pg_async_url = pg_sync_url.replace("postgresql+psycopg2", "postgresql+asyncpg")
    os.environ["DATABASE_URL"] = pg_async_url

    redis_host = redis_container.get_container_host_ip()
    redis_port = redis_container.get_exposed_port(6379)
    os.environ["REDIS_URL"] = f"redis://{redis_host}:{redis_port}/3"

    import cache as _cache_module
    _cache_module.reset_client()

    yield

    # Restauration
    if _orig_db_url is not None:
        os.environ["DATABASE_URL"] = _orig_db_url
    else:
        os.environ.pop("DATABASE_URL", None)
    if _orig_redis_url is not None:
        os.environ["REDIS_URL"] = _orig_redis_url
    else:
        os.environ.pop("REDIS_URL", None)
    _cache_module.reset_client()


@pytest.fixture(autouse=True)
def mock_gemini_aliases():
    """Mock la génération d'alias Gemini pour tous les tests d'intégration."""
    from unittest.mock import AsyncMock, patch
    with patch("src.competencies.helpers._generate_aliases_for_competency", new_callable=AsyncMock) as mock:
        mock.return_value = "mock_alias1, mock_alias2"
        yield mock


@pytest.fixture
def wipe_competencies_db(postgres_container, integration_env):
    """Recrée le schéma avant chaque test."""
    import sys
    monorepo_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    if monorepo_root not in sys.path:
        sys.path.insert(0, monorepo_root)

    from src.competencies.models import Base
    sync_url = postgres_container.get_connection_url()
    engine = create_engine(sync_url)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    engine.dispose()
    yield


@pytest.fixture
def wipe_redis(redis_container, integration_env):
    """Vide Redis avant chaque test."""
    import cache as _cache_module
    _cache_module.get_client().flushdb()
    yield


@pytest.fixture
def client(postgres_container, integration_env):
    """
    TestClient FastAPI pointant vers le vrai PostgreSQL Testcontainers.
    """
    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    pg_async_url = postgres_container.get_connection_url().replace(
        "postgresql+psycopg2", "postgresql+asyncpg"
    )
    engine = create_async_engine(pg_async_url)
    async_session = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with async_session() as session:
            yield session

    from shared.database import get_db
    from main import app
    from shared.auth.jwt import verify_jwt

    # Sauvegarder les overrides existants pour les restaurer après
    _prev_get_db = app.dependency_overrides.get(get_db)
    _prev_verify_jwt = app.dependency_overrides.get(verify_jwt)

    def override_jwt():
        return {"sub": "1", "role": "admin", "allowed_category_ids": [1]}

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[verify_jwt] = override_jwt

    with TestClient(app, follow_redirects=True) as c:
        yield c

    # Restaurer les overrides précédents au lieu de tout effacer
    if _prev_get_db is not None:
        app.dependency_overrides[get_db] = _prev_get_db
    else:
        app.dependency_overrides.pop(get_db, None)

    if _prev_verify_jwt is not None:
        app.dependency_overrides[verify_jwt] = _prev_verify_jwt
    else:
        app.dependency_overrides.pop(verify_jwt, None)
