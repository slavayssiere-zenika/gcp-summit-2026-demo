"""
Tests additionnels — Nouveaux endpoints et MCP tools (Sprint Bulk Reanalyse)
Ce fichier étend la suite de tests de competencies_api avec :
  - POST /user/{id}/assign/bulk  (idempotent bulk assignment)
  - DELETE /user/{id}/evaluations (purge scores)
  - MCP tools : assign_competencies_bulk / clear_user_evaluations
"""
import os
os.environ.setdefault("SECRET_KEY", "testsecret")
os.environ.setdefault("COMPETENCIES_API_URL", "http://test-comp")

import pytest
import json
from unittest.mock import MagicMock, AsyncMock
import httpx
from mcp_server import call_tool

# ── Fixture partagée ──────────────────────────────────────────────────────────

@pytest.fixture
def mock_httpx_client(mocker):
    mock = mocker.patch("mcp_server.httpx.AsyncClient")
    ci = AsyncMock()
    mock.return_value.__aenter__.return_value = ci
    return ci


# ══════════════════════════════════════════════════════════════════════════════
# MCP Tool — assign_competencies_bulk
# ══════════════════════════════════════════════════════════════════════════════

class TestAssignCompetenciesBulkMcp:

    @pytest.mark.asyncio
    async def test_success(self, mock_httpx_client):
        """Vérifie que le tool appelle POST /user/{id}/assign/bulk avec le bon payload."""
        resp = MagicMock(status_code=200)
        resp.json.return_value = {
            "success": True,
            "user_id": 42,
            "assigned": 5,
            "skipped": 1,
            "details": []
        }
        resp.raise_for_status = MagicMock()
        mock_httpx_client.post.return_value = resp

        result = await call_tool(
            name="assign_competencies_bulk",
            arguments={
                "user_id": 42,
                "competencies": [
                    {"name": "Python", "parent": "Langages", "practiced": True},
                    {"name": "GCP", "parent": "Cloud", "practiced": True},
                ]
            }
        )
        assert result[0].text
        # Le handler retourne json.dumps(response.json()) — parse-able
        payload = json.loads(result[0].text)
        assert payload.get("success") is True
        assert payload.get("assigned") == 5

        # Vérifier que l'endpoint correct a été appelé
        call_url = str(mock_httpx_client.post.call_args)
        assert "/user/42/assign/bulk" in call_url

    @pytest.mark.asyncio
    async def test_missing_user_id_returns_error(self):
        """user_id manquant → KeyError → exception capturée → {"success": false}."""
        result = await call_tool(
            name="assign_competencies_bulk",
            arguments={"competencies": [{"name": "Python"}]}
        )
        # L'implémentation lève une KeyError → except → {"success": False, "error": ...}
        payload = json.loads(result[0].text)
        assert payload.get("success") is False

    @pytest.mark.asyncio
    async def test_missing_competencies_returns_error(self):
        """competencies manquant → KeyError → exception → {"success": false}."""
        result = await call_tool(
            name="assign_competencies_bulk",
            arguments={"user_id": 1}
        )
        payload = json.loads(result[0].text)
        assert payload.get("success") is False

    @pytest.mark.asyncio
    async def test_api_error_returns_text(self, mock_httpx_client):
        """Erreur HTTP API → retour texte 'API Error {status}: {body}'."""
        err_resp = MagicMock(status_code=500, text="DB error")
        mock_httpx_client.post.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=err_resp
        )
        result = await call_tool(
            name="assign_competencies_bulk",
            arguments={"user_id": 1, "competencies": [{"name": "Java"}]}
        )
        # Le handler global retourne f"API Error {status}: {text}" pour les non-409
        assert "API Error" in result[0].text or "500" in result[0].text

    @pytest.mark.asyncio
    async def test_network_error_returns_structured(self, mock_httpx_client):
        """Erreur réseau (Exception) → retour {"success": false}."""
        mock_httpx_client.post.side_effect = Exception("Connection refused")
        result = await call_tool(
            name="assign_competencies_bulk",
            arguments={"user_id": 1, "competencies": [{"name": "Go"}]}
        )
        payload = json.loads(result[0].text)
        assert payload.get("success") is False


# ══════════════════════════════════════════════════════════════════════════════
# MCP Tool — clear_user_evaluations
# ══════════════════════════════════════════════════════════════════════════════

class TestClearUserEvaluationsMcp:

    @pytest.mark.asyncio
    async def test_success(self, mock_httpx_client):
        """Vérifie que le tool appelle DELETE /user/{id}/evaluations et retourne confirmation."""
        resp = MagicMock(status_code=200)
        resp.raise_for_status = MagicMock()
        mock_httpx_client.delete.return_value = resp

        result = await call_tool(
            name="clear_user_evaluations",
            arguments={"user_id": 7}
        )
        # L'implémentation retourne une string plain text (non-JSON)
        assert "7" in result[0].text or "cleared" in result[0].text.lower()

        call_url = str(mock_httpx_client.delete.call_args)
        assert "/user/7/evaluations" in call_url

    @pytest.mark.asyncio
    async def test_missing_user_id_returns_error(self):
        """user_id manquant → KeyError → {"success": false}."""
        result = await call_tool(name="clear_user_evaluations", arguments={})
        payload = json.loads(result[0].text)
        assert payload.get("success") is False

    @pytest.mark.asyncio
    async def test_api_error_returns_text(self, mock_httpx_client):
        """Erreur 404 → retour texte 'API Error 404: ...' ou CONFLIT 409."""
        err_resp = MagicMock(status_code=404, text="User not found")
        mock_httpx_client.delete.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=err_resp
        )
        result = await call_tool(name="clear_user_evaluations", arguments={"user_id": 9999})
        # Le handler global retourne le message d'erreur
        assert "API Error" in result[0].text or "404" in result[0].text or "not found" in result[0].text.lower()

    @pytest.mark.asyncio
    async def test_network_error_returns_structured(self, mock_httpx_client):
        """Erreur réseau → {"success": false}."""
        mock_httpx_client.delete.side_effect = Exception("Timeout")
        result = await call_tool(name="clear_user_evaluations", arguments={"user_id": 5})
        payload = json.loads(result[0].text)
        assert payload.get("success") is False


# ══════════════════════════════════════════════════════════════════════════════
# MCP Tool List — vérification présence des tools
# ══════════════════════════════════════════════════════════════════════════════

class TestMcpToolsRegistration:

    @pytest.mark.asyncio
    async def test_new_tools_in_list(self):
        """Vérifie que assign_competencies_bulk et clear_user_evaluations sont déclarés."""
        from mcp_server import list_tools
        tools = await list_tools()
        names = {t.name for t in tools}
        assert "assign_competencies_bulk" in names, \
            "Tool 'assign_competencies_bulk' manquant dans list_tools()"
        assert "clear_user_evaluations" in names, \
            "Tool 'clear_user_evaluations' manquant dans list_tools()"
