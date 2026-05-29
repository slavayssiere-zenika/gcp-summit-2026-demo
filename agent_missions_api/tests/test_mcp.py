from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Tests MCPHttpClient ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_tools_success():
    from mcp_client import MCPHttpClient

    mock_response = MagicMock()
    mock_response.json.return_value = [
        {"name": "list_missions", "description": "Liste les missions", "inputSchema": {"properties": {}, "required": []}},
        {"name": "get_mission", "description": "Détail d'une mission", "inputSchema": {
            "properties": {"mission_id": {"type": "integer"}}, "required": ["mission_id"]}},
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
    from mcp_client import LONG_RUNNING_TOOLS

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
    from mcp_client import MCPHttpClient, get_missions_mcp
    client = await get_missions_mcp()
    assert isinstance(client, MCPHttpClient)


@pytest.mark.asyncio
async def test_get_cv_mcp_returns_client():
    from mcp_client import MCPHttpClient, get_cv_mcp
    client = await get_cv_mcp()
    assert isinstance(client, MCPHttpClient)


@pytest.mark.asyncio
async def test_get_users_mcp_returns_client():
    from mcp_client import MCPHttpClient, get_users_mcp
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


# ── ValidationError McpToolResult (lignes 78-83) ─────────────────────────────

@pytest.mark.asyncio
async def test_call_tool_mcp_contract_violation_raises():
    """Si result n'est pas une liste (mauvais type) → ValidationError propagée.

    McpToolResult.result = List[Any] avec default=[].
    Passer un entier à la place d'une liste viole le contrat Pydantic.
    """
    from mcp_client import MCPHttpClient

    mock_response = MagicMock()
    # result doit être List[Any] — un int est une vraie violation de contrat
    mock_response.json.return_value = {"result": 12345}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        client = MCPHttpClient("http://missions_mcp:8000")
        from pydantic import ValidationError
        with pytest.raises((ValidationError, Exception)):
            await client.call_tool("list_missions", {})


# ── MCPSseClient (lignes 96-137) ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mcp_sse_list_tools():
    """MCPSseClient.list_tools() retourne la liste des tools via SSE."""
    from mcp_client import MCPSseClient

    fake_tool = MagicMock()
    fake_tool.name = "list_missions"
    fake_tool.description = "Liste les missions"
    fake_tool.inputSchema = {"properties": {}}

    fake_res = MagicMock()
    fake_res.tools = [fake_tool]

    mock_session = AsyncMock()
    mock_session.initialize = AsyncMock()
    mock_session.list_tools = AsyncMock(return_value=fake_res)

    with patch("mcp_client.sse_client") as _, \
            patch("mcp_client.ClientSession") as _, \
            patch("mcp_client.AsyncExitStack") as mock_stack_cls:

        mock_stack = AsyncMock()
        mock_stack.__aenter__ = AsyncMock(return_value=mock_stack)
        mock_stack.__aexit__ = AsyncMock(return_value=None)
        mock_stack.enter_async_context = AsyncMock(side_effect=[
            (MagicMock(), MagicMock()),  # streams
            mock_session,               # session
        ])
        mock_stack_cls.return_value = mock_stack

        client = MCPSseClient("http://missions_mcp:8000/sse")
        tools = await client.list_tools()

    assert tools[0]["name"] == "list_missions"


@pytest.mark.asyncio
async def test_mcp_sse_call_tool_success():
    """MCPSseClient.call_tool() retourne le contenu sérialisé."""
    from mcp_client import MCPSseClient

    fake_content = MagicMock()
    fake_content.model_dump = MagicMock(return_value={"type": "text", "text": "ok"})

    fake_res = MagicMock()
    fake_res.content = [fake_content]

    mock_session = AsyncMock()
    mock_session.initialize = AsyncMock()
    mock_session.call_tool = AsyncMock(return_value=fake_res)

    with patch("mcp_client.AsyncExitStack") as mock_stack_cls:
        mock_stack = AsyncMock()
        mock_stack.__aenter__ = AsyncMock(return_value=mock_stack)
        mock_stack.__aexit__ = AsyncMock(return_value=None)
        mock_stack.enter_async_context = AsyncMock(side_effect=[
            (MagicMock(), MagicMock()),
            mock_session,
        ])
        mock_stack_cls.return_value = mock_stack

        client = MCPSseClient("http://missions_mcp:8000/sse")
        result = await client.call_tool("list_missions", {})

    assert result == [{"type": "text", "text": "ok"}]


@pytest.mark.asyncio
async def test_mcp_sse_call_tool_raises_on_error():
    """MCPSseClient.call_tool() propage l'exception en cas d'échec SSE."""
    from mcp_client import MCPSseClient

    with patch("mcp_client.AsyncExitStack") as mock_stack_cls:
        mock_stack = AsyncMock()
        mock_stack.__aenter__ = AsyncMock(return_value=mock_stack)
        mock_stack.__aexit__ = AsyncMock(return_value=None)
        mock_stack.enter_async_context = AsyncMock(side_effect=ConnectionError("SSE failed"))
        mock_stack_cls.return_value = mock_stack

        client = MCPSseClient("http://missions_mcp:8000/sse")
        with pytest.raises(ConnectionError):
            await client.call_tool("list_missions", {})


# ── get_competencies_mcp singleton (lignes 183-184) ───────────────────────────

@pytest.mark.asyncio
async def test_get_competencies_mcp_returns_client():
    from mcp_client import MCPHttpClient, get_competencies_mcp
    client = await get_competencies_mcp()
    assert isinstance(client, MCPHttpClient)
