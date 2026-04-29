import os
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient

# CRITICAL: Set environment variables BEFORE imports
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./cv_test.db"
os.environ["SECRET_KEY"] = "testsecret"
os.environ["REDIS_URL"] = "redis://localhost:6379/7"
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test-project")

with patch("opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter", return_value=MagicMock()):
    mock_redis = AsyncMock()
    # It needs to return a valid JSON string or None for get()
    mock_redis.get.return_value = None
    with patch("redis.asyncio.from_url", return_value=mock_redis):
        from main import app
        from database import get_db
    from src.auth import verify_jwt

def override_verify_jwt():
    return {"sub": "test", "email": "test@zenika.com", "role": "admin"}

async def override_get_db():
    db = AsyncMock()
    yield db

app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[verify_jwt] = override_verify_jwt

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c
