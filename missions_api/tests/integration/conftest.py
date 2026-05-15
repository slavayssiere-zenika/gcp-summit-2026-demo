"""
Fixtures Testcontainers pour les tests d'intégration de missions_api.

missions_api utilise des types PostgreSQL avancés :
- JSONB : extracted_competencies, prefiltered_candidates, proposed_team
- ARRAY(String) : competencies_keywords
- Vector(3072) : semantic_embedding

Ces types sont incompatibles avec SQLite — ils nécessitent pgvector (même image que cv_api).
"""
import os

import pytest
from sqlalchemy import create_engine, text
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="session")
def postgres_container():
    """
    Démarre pgvector/pg16 pour missions_api.

    L'image pgvector est obligatoire car la colonne semantic_embedding
    utilise Vector(3072), incompatible avec postgres:16-alpine standard.
    """
    with PostgresContainer("pgvector/pgvector:pg16") as pg:
        # Activer l'extension pgvector
        sync_url = pg.get_connection_url()
        engine = create_engine(sync_url)
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
        engine.dispose()
        yield pg


@pytest.fixture(scope="session")
def integration_env(postgres_container):
    """Injecte les URLs dynamiques — sauvegarde et restaure l'env original."""
    _orig_db_url = os.environ.get("DATABASE_URL")

    pg_sync_url = postgres_container.get_connection_url()
    pg_async_url = pg_sync_url.replace("postgresql+psycopg2", "postgresql+asyncpg")
    os.environ["DATABASE_URL"] = pg_async_url

    yield

    if _orig_db_url is not None:
        os.environ["DATABASE_URL"] = _orig_db_url
    else:
        os.environ.pop("DATABASE_URL", None)


@pytest.fixture
def wipe_missions_db(postgres_container, integration_env):
    """Recrée le schéma avant chaque test."""
    from src.missions.models import Base
    sync_url = postgres_container.get_connection_url()
    engine = create_engine(sync_url)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    engine.dispose()
    yield


@pytest.fixture
def client(postgres_container, integration_env):
    """TestClient FastAPI pointant vers le vrai PostgreSQL pgvector."""
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
        return {"sub": "test", "email": "test@zenika.com", "role": "admin"}

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
