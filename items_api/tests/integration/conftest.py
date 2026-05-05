"""
Fixtures Testcontainers pour les tests d'intégration de items_api.

Ces fixtures démarrent de vrais conteneurs Docker (PostgreSQL + Redis) pour la
durée de la session pytest. Elles ne sont PAS autouse — elles sont demandées
explicitement par les tests marqués @pytest.mark.integration pour ne pas
ralentir les tests unitaires SQLite.

Prérequis : Docker doit être disponible (vérifié par deploy.sh et run_tests.sh).
"""
import os

import pytest
from sqlalchemy import create_engine
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer


@pytest.fixture(scope="session")
def postgres_container():
    """Démarre un conteneur PostgreSQL 16 pour toute la session de tests."""
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture(scope="session")
def redis_container():
    """Démarre un conteneur Redis 7 pour toute la session de tests."""
    with RedisContainer("redis:7-alpine") as r:
        yield r


@pytest.fixture(scope="session")
def integration_env(postgres_container, redis_container):
    """
    Injecte les URLs dynamiques (ports assignés par Docker) dans les variables
    d'environnement. Appelé explicitement par les tests d'intégration.

    Le reset_client() de cache.py force la reconstruction du client Redis avec
    la nouvelle URL au prochain appel à get_client().
    """
    # URL PostgreSQL async (asyncpg)
    pg_sync_url = postgres_container.get_connection_url()
    pg_async_url = pg_sync_url.replace("postgresql+psycopg2", "postgresql+asyncpg")
    os.environ["DATABASE_URL"] = pg_async_url

    # URL Redis dynamique
    redis_host = redis_container.get_container_host_ip()
    redis_port = redis_container.get_exposed_port(6379)
    os.environ["REDIS_URL"] = f"redis://{redis_host}:{redis_port}/1"

    # Réinitialise le client Redis lazy pour qu'il reconstruise avec la nouvelle URL
    import cache as _cache_module
    _cache_module.reset_client()

    yield


@pytest.fixture
def wipe_pg_db(postgres_container, integration_env):
    """
    Recrée le schéma avant chaque test pour garantir l'isolation.

    Utilise le sync engine pour le DDL (drop/create).
    """
    from src.items.models import Base

    sync_url = postgres_container.get_connection_url()
    engine = create_engine(sync_url)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    engine.dispose()
    yield


@pytest.fixture
def wipe_redis_integration(redis_container, integration_env):
    """Vide Redis avant chaque test d'intégration."""
    import cache as _cache_module
    _cache_module.get_client().flushdb()
    yield
