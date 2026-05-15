import os
from unittest.mock import MagicMock, patch

import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# CRITICAL: Set environment variables BEFORE any imports that use them at module level
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./items_test.db"
os.environ["ITEMS_API_URL"] = "http://items-api:8001"
os.environ["USERS_API_URL"] = "http://users-api:8000"
os.environ["SECRET_KEY"] = "testsecret"

# Prépare le serveur FakeRedis partagé (réutilisé par reset_client après import)
_fake_redis_server = fakeredis.FakeServer()
_fake_redis_client = fakeredis.FakeRedis(server=_fake_redis_server, decode_responses=True)

# Mock OTel AVANT l'import de main (nécessaire car OTel s'init au niveau module)
with patch("opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter", return_value=MagicMock()):
    from shared.database import engine, get_db
    from main import app
    from shared.auth.jwt import verify_jwt
    from src.items.models import Base

# Injecte le client fakeredis dans le module cache (lazy init)
import cache as _cache_module  # noqa: E402
_cache_module._client = _fake_redis_client

if engine:
    engine.dispose()

sync_engine = create_engine(
    "sqlite:///./items_test.db",
    connect_args={"check_same_thread": False},
)

async_engine = create_async_engine(
    "sqlite+aiosqlite:///./items_test.db",
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(
    class_=AsyncSession, autocommit=False, autoflush=False,
    expire_on_commit=False, bind=async_engine
)


async def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        await db.close()


def override_verify_jwt():
    return {"sub": "1", "allowed_category_ids": [1]}


app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[verify_jwt] = override_verify_jwt


@pytest.fixture(scope="function", autouse=True)
def wipe_db():
    Base.metadata.drop_all(bind=sync_engine)
    Base.metadata.create_all(bind=sync_engine)
    import cache as _cache_module
    if _cache_module._client:
        _cache_module._client.flushall()
    yield


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c
