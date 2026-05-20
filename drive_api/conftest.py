import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio

# CRITICAL: Set environment variables BEFORE any import that consumes them
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./drive_test.db"
os.environ["SECRET_KEY"] = "testsecret"
os.environ["USERS_API_URL"] = "http://users-api:8000"

with patch("opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter", return_value=MagicMock()):
    from fastapi.testclient import TestClient
    from httpx import ASGITransport
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker
    from shared.database import get_db, Base
    from main import app
    from shared.auth.jwt import verify_jwt


def override_verify_jwt():
    return {"sub": "test", "email": "test@zenika.com", "role": "admin"}


test_engine = create_async_engine("sqlite+aiosqlite:///./drive_test.db", pool_pre_ping=True)
TestSessionLocal = sessionmaker(
    bind=test_engine, class_=AsyncSession, expire_on_commit=False,
    autocommit=False, autoflush=False
)


@pytest_asyncio.fixture(autouse=True)
async def create_test_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session():
    async with TestSessionLocal() as db:
        yield db


async def override_get_db():
    db = AsyncMock()
    yield db


app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[verify_jwt] = override_verify_jwt


@pytest.fixture(autouse=True)
def mock_google_auth(monkeypatch):
    creds = MagicMock()
    creds.universe_domain = "googleapis.com"
    monkeypatch.setattr("google.auth.default", lambda *args, **kwargs: (creds, "test-project"))


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest_asyncio.fixture
async def async_client():
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
