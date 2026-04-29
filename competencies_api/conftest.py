import os
import pytest
import fakeredis
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./competencies_test.db"
os.environ["COMPETENCIES_API_URL"] = "http://competencies_api:8003"
os.environ["USERS_API_URL"] = "http://users_api:8000"
os.environ["SECRET_KEY"] = "testsecret"

# Remplace le client Redis par un serveur FakeRedis in-memory AVANT l'import de main.
# cache.py crée `client = redis.from_url(...)` au niveau module → il faut patcher
# redis.from_url avant que ce code s'exécute.
_fake_redis_server = fakeredis.FakeServer()
_fake_redis_client = fakeredis.FakeRedis(server=_fake_redis_server, decode_responses=True)

with patch("redis.from_url", return_value=_fake_redis_client), \
     patch("opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter", return_value=MagicMock()):
    from main import app
    from database import get_db, engine
    from src.competencies.models import Base
    from src.auth import verify_jwt

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

if engine: engine.dispose()

sync_engine = create_engine(
    "sqlite:///./competencies_test.db",
    connect_args={"check_same_thread": False},
)

async_engine = create_async_engine(
    "sqlite+aiosqlite:///./competencies_test.db",
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(class_=AsyncSession, autocommit=False, autoflush=False, expire_on_commit=False, bind=async_engine)

async def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        await db.close()

def override_verify_jwt():
    return {"sub": "1", "role": "admin", "allowed_category_ids": [1]}

app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[verify_jwt] = override_verify_jwt

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

@pytest.fixture(scope="function", autouse=True)
def wipe_db():
    Base.metadata.drop_all(bind=sync_engine)
    Base.metadata.create_all(bind=sync_engine)
    _fake_redis_client.flushall()
    yield
