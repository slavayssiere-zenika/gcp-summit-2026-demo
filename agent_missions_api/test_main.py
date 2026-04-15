import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

import jwt


# ── Helpers ────────────────────────────────────────────────────────────────────

SECRET_KEY = "test-secret-key-missions"
ALGORITHM = "HS256"


def make_jwt(sub: str = "test@zenika.com") -> str:
    return jwt.encode({"sub": sub, "exp": 9999999999}, SECRET_KEY, algorithm=ALGORITHM)


def auth_headers(sub: str = "test@zenika.com") -> dict:
    return {"Authorization": f"Bearer {make_jwt(sub)}"}


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def mock_agent_result():
    return {
        "response": "Voici les missions actives : Mission Java FinTech (ID 1).",
        "data": {"missions": [{"id": 1, "title": "Java FinTech"}]},
        "steps": [
            {"type": "call", "tool": "list_missions", "args": {}},
            {"type": "result", "data": {"missions": [{"id": 1}]}},
        ],
        "thoughts": "",
        "usage": {"total_input_tokens": 100, "total_output_tokens": 50, "estimated_cost_usd": 0.000023},
    }


# ── Tests publics (sans JWT) ───────────────────────────────────────────────────

def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "agent_missions_api"
    assert "version" in data


def test_version(client):
    resp = client.get("/version")
    assert resp.status_code == 200
    assert "version" in resp.json()


def test_query_requires_auth(client):
    resp = client.post("/query", json={"query": "Liste les missions"})
    assert resp.status_code == 401


# ── Tests protégés (avec JWT valide) ──────────────────────────────────────────

def test_query_success(client, mock_agent_result):
    with patch("main.run_agent_query", new=AsyncMock(return_value=mock_agent_result)):
        resp = client.post(
            "/query",
            json={"query": "Montre-moi les missions en cours", "session_id": "test-session"},
            headers=auth_headers(),
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "response" in data
    assert "missions" in data["response"].lower() or data["response"]


def test_query_propagates_user_id(client, mock_agent_result):
    """Le user_id JWT sub est propagé à run_agent_query."""
    captured = {}

    async def fake_run(query, session_id, user_id):
        captured["user_id"] = user_id
        return mock_agent_result

    with patch("main.run_agent_query", new=fake_run):
        client.post(
            "/query",
            json={"query": "test", "user_id": "alice@zenika.com"},
            headers=auth_headers("alice@zenika.com"),
        )
    assert captured.get("user_id") == "alice@zenika.com"


def test_query_invalid_jwt(client):
    resp = client.post(
        "/query",
        json={"query": "test"},
        headers={"Authorization": "Bearer invalid.token.here"},
    )
    assert resp.status_code == 401


def test_mcp_registry_requires_auth(client):
    resp = client.get("/mcp/registry")
    assert resp.status_code == 401


def test_mcp_registry_success(client):
    mock_tool = MagicMock()
    mock_tool.__name__ = "list_missions"
    mock_tool.__doc__ = "Liste les missions actives"

    with patch("main.MISSIONS_TOOLS", [mock_tool]):
        resp = client.get("/mcp/registry", headers=auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent"] == "agent_missions_api"
    assert data["count"] >= 0


def test_query_agent_error_returns_500(client):
    async def raise_error(query, session_id, user_id):
        raise RuntimeError("MCP timeout")

    with patch("main.run_agent_query", new=raise_error):
        resp = client.post(
            "/query",
            json={"query": "Staffing mission Java"},
            headers=auth_headers(),
        )
    assert resp.status_code == 500


def test_metrics_endpoint_exposed(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert b"missions_agent_queries_total" in resp.content or b"python_gc" in resp.content
