import os
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient

# CRITICAL: Set environment variables BEFORE imports
os.environ["SECRET_KEY"] = "testsecret"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["GCP_PROJECT_ID"] = "test-project"

with patch("opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter", return_value=MagicMock()):
    from mcp_app import app
    from auth import verify_jwt

def override_verify_jwt():
    return {"sub": "test", "email": "test@zenika.com", "role": "admin"}

app.dependency_overrides[verify_jwt] = override_verify_jwt

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c
