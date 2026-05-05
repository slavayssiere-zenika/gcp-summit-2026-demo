from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy import create_engine
from fastapi.testclient import TestClient
import pytest
import fakeredis
from unittest.mock import MagicMock, patch
import os
import sys

# Assure que la racine du monorepo est dans sys.path pour résoudre `shared/`
_MONOREPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _MONOREPO_ROOT not in sys.path:
    sys.path.insert(0, _MONOREPO_ROOT)


os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./competencies_test.db"
os.environ["COMPETENCIES_API_URL"] = "http://competencies_api:8003"
os.environ["USERS_API_URL"] = "http://users_api:8000"
os.environ["SECRET_KEY"] = "testsecret"

# Remplace le client Redis par un serveur FakeRedis in-memory.
_fake_redis_server = fakeredis.FakeServer()
_fake_redis_client = fakeredis.FakeRedis(server=_fake_redis_server, decode_responses=True)

# Mock OTel AVANT l'import de main
with patch("opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter", return_value=MagicMock()):
    from database import engine, get_db
    from main import app
    from src.auth import verify_jwt
    from src.competencies.models import Base

# Injecte le client fakeredis dans le module cache (lazy init)
import cache as _cache_module  # noqa: E402
_cache_module._client = _fake_redis_client


if engine:
    engine.dispose()

sync_engine = create_engine(
    "sqlite:///./competencies_test.db",
    connect_args={"check_same_thread": False},
)

async_engine = create_async_engine(
    "sqlite+aiosqlite:///./competencies_test.db",
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(class_=AsyncSession, autocommit=False,
                                   autoflush=False, expire_on_commit=False, bind=async_engine)


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
