import os
import pytest
import pytest_asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient
import httpx
from httpx import ASGITransport

# CRITICAL: Set environment variables BEFORE imports
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./drive_test.db"
os.environ["SECRET_KEY"] = "testsecret"
os.environ["USERS_API_URL"] = "http://users-api:8000"

with patch("opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter", return_value=MagicMock()):
    from main import app
    from database import get_db
    from src.auth import verify_jwt

def override_verify_jwt():
    return {"sub": "test", "email": "test@zenika.com", "role": "admin"}

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

test_engine = create_async_engine("sqlite+aiosqlite:///./drive_test.db", pool_pre_ping=True)
TestSessionLocal = sessionmaker(
    bind=test_engine, class_=AsyncSession, expire_on_commit=False,
    autocommit=False, autoflush=False
)

@pytest_asyncio.fixture(autouse=True)
async def create_test_db():
    from database import Base
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
    from unittest.mock import MagicMock
    import google.auth
    monkeypatch.setattr("google.auth.default", lambda: (MagicMock(), "test-project"))

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

@pytest_asyncio.fixture
async def async_client():
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
