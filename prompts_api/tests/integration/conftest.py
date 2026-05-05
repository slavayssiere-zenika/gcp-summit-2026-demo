"""
Fixtures Testcontainers pour les tests d'intégration de prompts_api.

prompts_api est simple : String/Text uniquement, pas de JSONB ni pgvector.
Valeur principale : tester le cache Redis async (redis.asyncio) et la
persistence réelle des prompts système.
"""
import os

import pytest
from sqlalchemy import create_engine
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer


@pytest.fixture(scope="session")
def postgres_container():
    """Démarre PostgreSQL 16 pour prompts_api."""
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture(scope="session")
def redis_container():
    """Démarre Redis 7 pour tester le cache async prompts_api."""
    with RedisContainer("redis:7-alpine") as r:
        yield r


@pytest.fixture(scope="session")
def integration_env(postgres_container, redis_container):
    """Injecte les URLs dynamiques — sauvegarde et restaure l'env original."""
    _orig_db_url = os.environ.get("DATABASE_URL")
    _orig_redis_url = os.environ.get("REDIS_URL")

    pg_sync_url = postgres_container.get_connection_url()
    pg_async_url = pg_sync_url.replace("postgresql+psycopg2", "postgresql+asyncpg")
    os.environ["DATABASE_URL"] = pg_async_url

    redis_host = redis_container.get_container_host_ip()
    redis_port = redis_container.get_exposed_port(6379)
    os.environ["REDIS_URL"] = f"redis://{redis_host}:{redis_port}/5"

    yield

    if _orig_db_url is not None:
        os.environ["DATABASE_URL"] = _orig_db_url
    else:
        os.environ.pop("DATABASE_URL", None)
    if _orig_redis_url is not None:
        os.environ["REDIS_URL"] = _orig_redis_url
    else:
        os.environ.pop("REDIS_URL", None)


@pytest.fixture
def wipe_prompts_db(postgres_container, integration_env):
    """Recrée le schéma avant chaque test."""
    from src.prompts.models import Base
    sync_url = postgres_container.get_connection_url()
    engine = create_engine(sync_url)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    engine.dispose()
    yield


@pytest.fixture
def client(postgres_container, integration_env):
    """TestClient FastAPI pointant vers le vrai PostgreSQL."""
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

    from database import get_db
    from main import app
    from src.prompts.router import verify_jwt

    def override_jwt():
        return {"sub": "test", "email": "test@zenika.com", "role": "admin"}

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[verify_jwt] = override_jwt

    with TestClient(app, follow_redirects=True) as c:
        yield c

    app.dependency_overrides.clear()
