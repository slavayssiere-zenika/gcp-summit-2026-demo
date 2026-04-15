import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── Tests MCPHttpClient ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_tools_success():
    from mcp_client import MCPHttpClient

    mock_response = MagicMock()
    mock_response.json.return_value = [
        {"name": "list_missions", "description": "Liste les missions", "inputSchema": {"properties": {}, "required": []}},
        {"name": "get_mission", "description": "Détail d'une mission", "inputSchema": {"properties": {"mission_id": {"type": "integer"}}, "required": ["mission_id"]}},
    ]
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        client = MCPHttpClient("http://missions_mcp:8000")
        tools = await client.list_tools()

    assert len(tools) == 2
    assert tools[0]["name"] == "list_missions"


@pytest.mark.asyncio
async def test_call_tool_list_missions():
    from mcp_client import MCPHttpClient

    mock_response = MagicMock()
    mock_response.json.return_value = {"result": [{"type": "text", "text": '{"missions": [{"id": 1}]}'}]}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        client = MCPHttpClient("http://missions_mcp:8000")
        result = await client.call_tool("list_missions", {})

    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_call_tool_search_best_candidates_uses_long_timeout():
    """search_best_candidates est dans LONG_RUNNING_TOOLS → timeout 120s."""
    from mcp_client import MCPHttpClient, LONG_RUNNING_TOOLS

    assert "search_best_candidates" in LONG_RUNNING_TOOLS
    assert "reanalyze_mission" in LONG_RUNNING_TOOLS
    assert "get_candidate_rag_context" in LONG_RUNNING_TOOLS


@pytest.mark.asyncio
async def test_call_tool_raises_on_http_error():
    """Un 500 du MCP doit propager une exception."""
    import httpx
    from mcp_client import MCPHttpClient

    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500 Server Error", request=MagicMock(), response=MagicMock()
    )

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        client = MCPHttpClient("http://missions_mcp:8000")
        with pytest.raises(Exception):
            await client.call_tool("list_missions", {})


# ── Tests singletons ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_missions_mcp_returns_client():
    from mcp_client import get_missions_mcp, MCPHttpClient
    client = await get_missions_mcp()
    assert isinstance(client, MCPHttpClient)


@pytest.mark.asyncio
async def test_get_cv_mcp_returns_client():
    from mcp_client import get_cv_mcp, MCPHttpClient
    client = await get_cv_mcp()
    assert isinstance(client, MCPHttpClient)


@pytest.mark.asyncio
async def test_get_users_mcp_returns_client():
    from mcp_client import get_users_mcp, MCPHttpClient
    client = await get_users_mcp()
    assert isinstance(client, MCPHttpClient)


@pytest.mark.asyncio
async def test_auth_header_propagated():
    """auth_header_var est propagé dans les headers MCP sortants."""
    from mcp_client import MCPHttpClient, auth_header_var

    captured_headers = {}

    mock_response = MagicMock()
    mock_response.json.return_value = []
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)

        async def capture_get(url, **kwargs):
            captured_headers.update(mock_cls.call_args.kwargs.get("headers", {}))
            return mock_response

        mock_http.get = capture_get
        mock_cls.return_value = mock_http

        token = auth_header_var.set("Bearer test-token-xyz")
        try:
            client = MCPHttpClient("http://missions_mcp:8000")
            await client.list_tools()
        finally:
            auth_header_var.reset(token)
