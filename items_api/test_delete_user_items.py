"""
Tests additionnels — Nouveaux endpoints et MCP tools (Sprint Bulk Reanalyse)
Ce fichier étend la suite de tests de items_api avec :
  - DELETE /user/{id}/items  (purge atomique missions)
  - MCP tool : delete_user_items
"""
import os
os.environ.setdefault("SECRET_KEY", "testsecret")
os.environ.setdefault("ITEMS_API_URL", "http://test-items")

import pytest
import json
from unittest.mock import MagicMock, AsyncMock, patch
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
# MCP Tool — delete_user_items
# ══════════════════════════════════════════════════════════════════════════════

class TestDeleteUserItemsMcp:

    @pytest.mark.asyncio
    async def test_success(self, mock_httpx_client):
        """Vérifie que le tool appelle DELETE /user/{id}/items et confirme la suppression."""
        resp = MagicMock(status_code=204)
        resp.raise_for_status = MagicMock()
        mock_httpx_client.delete.return_value = resp

        result = await call_tool(name="delete_user_items", arguments={"user_id": 3})

        assert result[0].text
        # Le handler retourne une string plain text (non-JSON)
        assert "3" in result[0].text or "deleted" in result[0].text.lower()

        # Vérifier que le bon endpoint a été appelé
        call_url = str(mock_httpx_client.delete.call_args)
        assert "/user/3/items" in call_url

    @pytest.mark.asyncio
    async def test_missing_user_id_returns_error(self):
        """user_id manquant → KeyError → {"success": false}."""
        result = await call_tool(name="delete_user_items", arguments={})
        payload = json.loads(result[0].text)
        assert payload.get("success") is False
        assert "error" in payload

    @pytest.mark.asyncio
    async def test_user_not_found_http_error(self, mock_httpx_client):
        """Erreur 404 → retour texte 'HTTP Error: 404 - ...'."""
        err_resp = MagicMock(status_code=404, text="User not found")
        mock_httpx_client.delete.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=err_resp
        )
        result = await call_tool(name="delete_user_items", arguments={"user_id": 9999})
        # Le handler retourne f"HTTP Error: {status} - {text}"
        assert "HTTP Error" in result[0].text or "404" in result[0].text

    @pytest.mark.asyncio
    async def test_network_error_returns_structured(self, mock_httpx_client):
        """Erreur réseau (Exception) → {"success": false}."""
        mock_httpx_client.delete.side_effect = Exception("Connection refused")
        result = await call_tool(name="delete_user_items", arguments={"user_id": 1})
        payload = json.loads(result[0].text)
        assert payload.get("success") is False
        assert "Connection refused" in payload.get("error", "")

    @pytest.mark.asyncio
    async def test_zero_deleted_returns_confirmation(self, mock_httpx_client):
        """Purge réussie (même 0 items) → message de confirmation."""
        resp = MagicMock(status_code=204)
        resp.raise_for_status = MagicMock()
        mock_httpx_client.delete.return_value = resp

        result = await call_tool(name="delete_user_items", arguments={"user_id": 99})
        # La réponse est toujours une confirmation textuelle
        assert "99" in result[0].text or "deleted" in result[0].text.lower()


# ══════════════════════════════════════════════════════════════════════════════
# MCP Tool List — vérification présence du tool
# ══════════════════════════════════════════════════════════════════════════════

class TestMcpToolsRegistration:

    @pytest.mark.asyncio
    async def test_delete_user_items_in_list(self):
        """Vérifie que delete_user_items est déclaré dans list_tools()."""
        from mcp_server import list_tools
        tools = await list_tools()
        names = {t.name for t in tools}
        assert "delete_user_items" in names, \
            "Tool 'delete_user_items' manquant dans list_tools()"


# ══════════════════════════════════════════════════════════════════════════════
# Endpoint HTTP — DELETE /user/{user_id}/items
# ══════════════════════════════════════════════════════════════════════════════

class TestDeleteUserItemsEndpoint:
    """Tests de contrat sur l'endpoint REST directement (sans BDD)."""

    def test_delete_user_items_returns_204(self, mocker):
        """DELETE /user/{id}/items doit retourner 204 No Content."""
        from main import app
        from database import get_db
        try:
            from src.auth import verify_jwt, security
        except ImportError:
            pytest.skip("Impossible de charger l'app items_api")

        from fastapi.testclient import TestClient

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 5
        mock_db.execute = AsyncMock(return_value=mock_result)

        overrides = {
            verify_jwt: lambda: {"sub": "test", "role": "admin"},
            security: lambda: MagicMock(credentials="testtoken"),
            get_db: lambda: mock_db
        }

        with patch.dict(app.dependency_overrides, overrides):
            tc = TestClient(app)
            r = tc.delete("/user/42/items", headers={"Authorization": "Bearer token"})
            assert r.status_code == 204

    def test_delete_user_items_requires_auth(self):
        """DELETE /user/{id}/items doit retourner 401 sans JWT."""
        from main import app
        try:
            from src.auth import verify_jwt, security
        except ImportError:
            pytest.skip("Impossible de charger l'app items_api")
        from fastapi.testclient import TestClient

        new_overrides = app.dependency_overrides.copy()
        new_overrides.pop(verify_jwt, None)
        new_overrides.pop(security, None)

        with patch.dict(app.dependency_overrides, new_overrides, clear=True):
            tc = TestClient(app)
            r = tc.delete("/user/1/items")
            assert r.status_code == 401
