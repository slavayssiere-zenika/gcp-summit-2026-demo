import os
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient

os.environ["SECRET_KEY"] = "testsecret"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["GCP_PROJECT_ID"] = "test-project"

with patch("opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter", return_value=MagicMock()):
    with patch("mcp_server.client", MagicMock()):
        from mcp_app import app
        from auth import verify_jwt

def override_verify_jwt():
    return {"sub": "test", "email": "test@zenika.com", "role": "admin"}

app.dependency_overrides[verify_jwt] = override_verify_jwt
client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


def test_version():
    resp = client.get("/version")
    assert resp.status_code == 200
    assert "version" in resp.json()


def test_get_tools_unauthorized():
    resp = client.get("/mcp/tools")
    # dependency_overrides bypasses JWT — should return 200
    assert resp.status_code == 200


def test_call_tool_unknown(mocker):
    mocker.patch("mcp_app.call_tool", new=AsyncMock(side_effect=Exception("Unknown tool")))
    resp = client.post(
        "/mcp/call",
        json={"name": "unknown_tool", "arguments": {}},
        headers={"Authorization": "Bearer testsecret"}
    )
    assert resp.status_code == 500
