import os
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient

# CRITICAL: Set environment variables BEFORE imports
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./drive_test.db"
os.environ["SECRET_KEY"] = "testsecret"
os.environ["USERS_API_URL"] = "http://users-api:8000"

with patch("opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter", return_value=MagicMock()):
    from main import app
    from database import get_db
    from src.auth import verify_jwt

client = TestClient(app)

def override_verify_jwt():
    return {"sub": "test", "email": "test@zenika.com", "role": "admin"}

async def override_get_db():
    db = AsyncMock()
    yield db

app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[verify_jwt] = override_verify_jwt


def test_health(mocker):
    mocker.patch("database.check_db_connection", new=AsyncMock(return_value=True))
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


def test_version():
    resp = client.get("/version")
    assert resp.status_code == 200
    assert "version" in resp.json()


def test_spec_success(mocker):
    mocker.patch("builtins.open", mocker.mock_open(read_data="# Drive Spec"))
    resp = client.get("/spec")
    assert resp.status_code == 200
    assert "Drive Spec" in resp.text


def test_spec_fallback(mocker):
    mocker.patch("builtins.open", side_effect=Exception("Not found"))
    resp = client.get("/spec")
    assert resp.status_code == 200
    assert "introuvable" in resp.text
