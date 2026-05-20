"""Tests des cas limites non couverts — items_api.

Sections :
  A. crud_router.py — bulk semaphore, get_user_from_api 503, enrich_item
  B. cache.py — Redis error patterns + delete_cache_pattern vide
  C. categories_router.py — pagination + edge cases
"""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key-32chars-xxxxxxxxx")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./items_edge_test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("USERS_API_URL", "http://users-api:8000")


# ─────────────────────────────────────────────────────────────────────────────
# Section A — crud_router.py : get_user_from_api edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestCrudRouterEdgeCases:

    def test_get_user_from_api_404_raises_400(self):
        """get_user_from_api avec réponse 404 → HTTPException 400 (user not found)."""
        import asyncio
        from src.items.crud_router import get_user_from_api

        mock_request = MagicMock()
        mock_request.user = None
        mock_request.headers.get.return_value = "Bearer fake"

        mock_response = MagicMock()
        mock_response.user = None
        mock_response.status_code = 404

        async def run():
            with patch("src.items.crud_router.httpx.AsyncClient") as mock_cls:
                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_cls.return_value = mock_client
                from fastapi import HTTPException
                with pytest.raises(HTTPException) as exc_info:
                    await get_user_from_api(999, mock_request)
                assert exc_info.value.status_code == 400

        asyncio.run(run())

    def test_get_user_from_api_network_error_raises_503(self):
        """get_user_from_api avec erreur réseau → HTTPException 503."""
        import asyncio
        import httpx
        from src.items.crud_router import get_user_from_api

        mock_request = MagicMock()
        mock_request.user = None
        mock_request.headers.get.return_value = "Bearer fake"

        async def run():
            with patch("src.items.crud_router.httpx.AsyncClient") as mock_cls:
                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client.get = AsyncMock(
                    side_effect=httpx.ConnectError("Connection refused")
                )
                mock_cls.return_value = mock_client
                from fastapi import HTTPException
                with pytest.raises(HTTPException) as exc_info:
                    await get_user_from_api(1, mock_request)
                assert exc_info.value.status_code == 503

        asyncio.run(run())

    def test_get_trace_context_headers_returns_dict(self):
        """get_trace_context_headers retourne toujours un dict (même sans OTel span actif)."""
        from src.items.crud_router import get_trace_context_headers
        headers = get_trace_context_headers()
        assert isinstance(headers, dict)

    def test_bulk_semaphore_lazy_init(self):
        """_get_bulk_sem() crée le sémaphore une seule fois (lazy init)."""
        from src.items.crud_router import _get_bulk_sem
        import src.items.crud_router as mod
        original = mod._BULK_SEM
        mod._BULK_SEM = None
        try:
            s1 = _get_bulk_sem()
            s2 = _get_bulk_sem()
            assert s1 is s2
        finally:
            mod._BULK_SEM = original

    def test_bulk_semaphore_value_from_env(self):
        """_get_bulk_sem() lit BULK_ENDPOINT_SEMAPHORE depuis l'environnement."""
        import src.items.crud_router as mod
        original = mod._BULK_SEM
        mod._BULK_SEM = None
        try:
            with patch.dict(os.environ, {"BULK_ENDPOINT_SEMAPHORE": "3"}):
                sem = mod._get_bulk_sem()
                assert sem._value == 3
        finally:
            mod._BULK_SEM = original


# Section B — cache.py : Supprimée car migrée vers shared.cache (testée globalement)


# ─────────────────────────────────────────────────────────────────────────────
# Section C — mcp_server.py : error handling dans les tools
# ─────────────────────────────────────────────────────────────────────────────

class TestMcpToolsEdgeCases:

    @pytest.mark.asyncio
    async def test_call_tool_unknown_tool_name(self):
        """call_tool avec un nom d'outil inconnu → retourne une erreur structurée."""
        from mcp_server import call_tool
        result = await call_tool("nonexistent_tool", {})
        # Doit retourner un TextContent avec un message d'erreur (pas lever d'exception)
        assert len(result) >= 1
        text = result[0].text
        assert "unknown" in text.lower() or "error" in text.lower() or "outil" in text.lower()

    @pytest.mark.asyncio
    async def test_list_tools_returns_non_empty(self):
        """list_tools retourne une liste non vide d'outils enregistrés."""
        from mcp_server import list_tools
        tools = await list_tools()
        assert len(tools) > 0
        # Vérifier que les tools attendus sont présents
        tool_names = {t.name for t in tools}
        assert "list_items" in tool_names
        assert "get_item" in tool_names
