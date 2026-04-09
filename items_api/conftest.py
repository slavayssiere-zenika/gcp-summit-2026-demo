import os
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# CRITICAL: Set environment variables BEFORE any imports
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./items_test.db"
os.environ["ITEMS_API_URL"] = "http://items-api:8001"
os.environ["USERS_API_URL"] = "http://users-api:8000"
os.environ["SECRET_KEY"] = "testsecret"

# Mock OpenTelemetry before imports
with patch("opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter", return_value=MagicMock()):
    from main import app
    from database import get_db, engine
    from src.items.models import Base
    from src.auth import verify_jwt

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

if engine: engine.dispose()

sync_engine = create_engine(
    "sqlite:///./items_test.db",
    connect_args={"check_same_thread": False},
)

async_engine = create_async_engine(
    "sqlite+aiosqlite:///./items_test.db",
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
    return {"sub": "1", "allowed_category_ids": [1]}

app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[verify_jwt] = override_verify_jwt

@pytest.fixture(scope="function", autouse=True)
def wipe_db():
    Base.metadata.drop_all(bind=sync_engine)
    Base.metadata.create_all(bind=sync_engine)
    import cache
    cache.client.flushdb()
    yield

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c
