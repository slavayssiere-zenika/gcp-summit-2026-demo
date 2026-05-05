"""
Fixtures Testcontainers pour les tests d'intégration de cv_api.

cv_api utilise pgvector (Vector(3072) + HNSW index) et jsonb — des types
PostgreSQL-only totalement invisibles en SQLite. Ces fixtures démarrent un
vrai conteneur pgvector pour détecter les bugs silencieux liés à ces types.

L'extension pgvector est activée manuellement après démarrage du conteneur.

Prérequis : Docker doit être disponible (vérifié par deploy.sh et run_tests.sh).
"""
import os

import pytest
from sqlalchemy import create_engine, text
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="session")
def pgvector_container():
    """
    Démarre un conteneur pgvector/pgvector:pg16 pour toute la session.

    Différence vs items_api (postgres:16-alpine) : on utilise l'image pgvector
    car cv_api.src.cvs.models importe Vector(3072) de pgvector.sqlalchemy.
    Sans cette image, le CREATE TABLE échoue avec "type vector does not exist".
    """
    with PostgresContainer("pgvector/pgvector:pg16") as pg:
        # Activer l'extension pgvector sur la DB de test
        sync_url = pg.get_connection_url()
        engine = create_engine(sync_url)
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
        engine.dispose()
        yield pg


@pytest.fixture(scope="session")
def integration_env_cv(pgvector_container):
    """
    Injecte l'URL PostgreSQL pgvector dans les variables d'environnement.

    cv_api n'a pas de cache.py module-level (Redis est instancié via des
    classes TaskState/BulkTaskState) — pas besoin de reset_client().
    """
    pg_sync_url = pgvector_container.get_connection_url()
    pg_async_url = pg_sync_url.replace("postgresql+psycopg2", "postgresql+asyncpg")
    os.environ["DATABASE_URL"] = pg_async_url
    yield


@pytest.fixture
def wipe_cv_db(pgvector_container, integration_env_cv):
    """
    Recrée le schéma avant chaque test d'intégration.

    Important : le `drop_all` doit respecter l'ordre des dépendances FK.
    SQLAlchemy le gère automatiquement via `metadata.sorted_tables`.
    """
    import sys
    monorepo_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    if monorepo_root not in sys.path:
        sys.path.insert(0, monorepo_root)

    from src.cvs.models import Base

    sync_url = pgvector_container.get_connection_url()
    engine = create_engine(sync_url)
    # Réactive pgvector après drop_all (l'extension est au niveau DB, pas schéma)
    Base.metadata.drop_all(bind=engine)
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.create_all(bind=engine)
    engine.dispose()
    yield
