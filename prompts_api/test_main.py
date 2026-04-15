import os
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient

# CRITICAL: Set environment variables BEFORE imports
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./prompts_test.db"
os.environ["SECRET_KEY"] = "testsecret"

with patch("opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter", return_value=MagicMock()):
    from main import app
    from database import get_db
    import src.prompts.router as prompts_router

def override_verify_jwt():
    return {"sub": "test", "email": "test@zenika.com", "role": "admin"}

# N'écrase PAS get_db globalement — les tests CRUD sont couverts par tests/test_prompts.py
# avec une vraie DB SQLite. Ce fichier ne teste que les endpoints sans DB.
app.dependency_overrides[prompts_router.verify_jwt] = override_verify_jwt

client = TestClient(app)


def test_health(mocker):
    mocker.patch("database.check_db_connection", new=AsyncMock(return_value=True))
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


def test_version():
    resp = client.get("/version")
    assert resp.status_code == 200
    assert "version" in resp.json()


def test_metrics_accessible():
    resp = client.get("/metrics")
    assert resp.status_code == 200
