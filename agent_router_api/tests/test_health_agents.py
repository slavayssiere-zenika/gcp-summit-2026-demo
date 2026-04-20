"""
Tests for ADR12-5 — GET /health/agents aggregated endpoint.

Scenarios covered:
  1. All 3 sub-agents UP        → status=healthy, HTTP 200
  2. 1 sub-agent DOWN           → status=degraded, HTTP 200
  3. All sub-agents DOWN        → status=unhealthy, HTTP 503
  4. Version is fetched         → version field populated
  5. latency_ms is present      → always measured
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

import sys
import os

# Ensure the router module can be imported (PYTHONPATH trick for local test runs)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(status_code: int, body: dict):
    """Build a minimal httpx.Response mock."""
    m = MagicMock()
    m.status_code = status_code
    m.json.return_value = body
    return m


def _health_ok():
    return _mock_response(200, {"status": "healthy"})


def _health_err():
    return ConnectionError("Connection refused")


def _version_ok(v="1.2.3"):
    return _mock_response(200, {"version": v})


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def app_client(monkeypatch):
    """Create a TestClient with all heavy env/imports neutralised."""
    # Prevent SemanticCache and JWT from crashing during import
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("SEMANTIC_CACHE_ENABLED", "false")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    # Stub the semantic cache so it doesn't try to connect to Redis
    with patch("semantic_cache.SemanticCache", MagicMock()):
        with patch("agent.run_agent_query", AsyncMock(return_value={})):
            with patch("agent.get_session_service", MagicMock()):
                from main import app
                yield TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHealthAgents:
    """ADR12-5 — /health/agents aggregated health check."""

    def _patch_probes(self, monkeypatch, hr_ok=True, ops_ok=True, missions_ok=True):
        """Patch httpx.AsyncClient.get to return controlled per-agent responses."""
        call_order = []

        async def _fake_get(self, url, **kwargs):  # noqa: D401
            call_order.append(url)
            if "/health" in url:
                agent = None
                if "agent_hr" in url:
                    agent = "hr"
                elif "agent_ops" in url:
                    agent = "ops"
                elif "agent_missions" in url:
                    agent = "missions"

                ok_map = {"hr": hr_ok, "ops": ops_ok, "missions": missions_ok}
                if agent and not ok_map.get(agent, True):
                    raise ConnectionError("Connection refused")
                return _health_ok()
            elif "/version" in url:
                return _version_ok()
            raise ValueError(f"Unexpected URL: {url}")

        monkeypatch.setattr("httpx.AsyncClient.get", _fake_get)
        return call_order

    def test_all_up_returns_healthy_200(self, app_client, monkeypatch):
        self._patch_probes(monkeypatch, hr_ok=True, ops_ok=True, missions_ok=True)
        resp = app_client.get("/health/agents")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "healthy"
        assert set(body["agents"].keys()) == {"hr", "ops", "missions"}
        for agent_data in body["agents"].values():
            assert agent_data["status"] == "up"
            assert "latency_ms" in agent_data
            assert "version" in agent_data

    def test_one_down_returns_degraded_200(self, app_client, monkeypatch):
        self._patch_probes(monkeypatch, hr_ok=True, ops_ok=True, missions_ok=False)
        resp = app_client.get("/health/agents")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "degraded"
        assert body["agents"]["hr"]["status"] == "up"
        assert body["agents"]["ops"]["status"] == "up"
        assert body["agents"]["missions"]["status"] == "down"

    def test_all_down_returns_unhealthy_503(self, app_client, monkeypatch):
        self._patch_probes(monkeypatch, hr_ok=False, ops_ok=False, missions_ok=False)
        resp = app_client.get("/health/agents")
        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "unhealthy"
        for agent_data in body["agents"].values():
            assert agent_data["status"] == "down"

    def test_version_is_populated_when_available(self, app_client, monkeypatch):
        self._patch_probes(monkeypatch, hr_ok=True, ops_ok=True, missions_ok=True)
        resp = app_client.get("/health/agents")
        assert resp.status_code == 200
        for agent_data in resp.json()["agents"].values():
            assert agent_data["version"] == "1.2.3"

    def test_latency_ms_is_non_negative_integer(self, app_client, monkeypatch):
        self._patch_probes(monkeypatch)
        resp = app_client.get("/health/agents")
        for agent_data in resp.json()["agents"].values():
            assert isinstance(agent_data["latency_ms"], int)
            assert agent_data["latency_ms"] >= 0

    def test_endpoint_is_public_no_jwt_required(self, app_client, monkeypatch):
        """GET /health/agents must not require Authorization header."""
        self._patch_probes(monkeypatch)
        # Call with no Authorization header
        resp = app_client.get("/health/agents")
        # Should not return 401 or 403
        assert resp.status_code in (200, 503)
        assert resp.status_code != 401
        assert resp.status_code != 403
