import pytest
from unittest.mock import MagicMock, AsyncMock
import httpx

from agent_api.mcp_client import (
    MCPHttpClient, MCPSseClient, auth_header_var,
    get_users_mcp, get_items_mcp, get_competencies_mcp, get_cv_mcp, get_loki_mcp,
    users_mcp_client
)

@pytest.fixture
def mock_httpx(mocker):
    mock = mocker.patch("agent_api.mcp_client.httpx.AsyncClient")
    client_instance = AsyncMock()
    mock.return_value.__aenter__.return_value = client_instance
    return client_instance

@pytest.mark.asyncio
async def test_mcp_http_client_list_tools(mock_httpx):
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = [{"name": "toolxyz"}]
    mock_httpx.get.return_value = mock_resp
    
    auth_header_var.set("Bearer token")
    client = MCPHttpClient("http://fake.url")
    await client.connect() # coverage
    result = await client.list_tools()
    
    assert result[0]["name"] == "toolxyz"
    mock_httpx.get.assert_called_with("http://fake.url/mcp/tools")

@pytest.mark.asyncio
async def test_mcp_http_client_call_tool_success(mock_httpx):
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"result": [{"text": "OK"}]}
    mock_httpx.post.return_value = mock_resp
    
    auth_header_var.set("Bearer token")
    client = MCPHttpClient("http://fake.url")
    result = await client.call_tool("my_tool", {"arg": "val"})
    
    assert result[0]["text"] == "OK"
    mock_httpx.post.assert_called_with(
        "http://fake.url/mcp/call",
        json={"name": "my_tool", "arguments": {"arg": "val"}},
        timeout=30.0
    )

@pytest.mark.asyncio
async def test_mcp_http_client_call_tool_error(mock_httpx):
    mock_httpx.post.side_effect = httpx.HTTPStatusError("Err", request=MagicMock(), response=MagicMock())
    
    client = MCPHttpClient("http://fake.url")
    with pytest.raises(httpx.HTTPStatusError):
        await client.call_tool("bad_tool", {})

@pytest.mark.asyncio
async def test_mcp_client_helpers():
    import agent_api.mcp_client as mc
    # reset globals for test
    mc.users_mcp_client = None
    mc.items_mcp_client = None
    mc.competencies_mcp_client = None
    mc.cv_mcp_client = None
    mc.loki_mcp_client = None
    
    users = await get_users_mcp()
    assert isinstance(users, MCPHttpClient)
    assert await get_items_mcp() is not None
    assert await get_competencies_mcp() is not None
    assert await get_cv_mcp() is not None
    assert await get_loki_mcp() is not None

@pytest.mark.asyncio
async def test_mcp_sse_client_list_tools(mocker):
    # Mocking mcp.client.sse module
    mock_sse = mocker.patch("mcp.client.sse.sse_client", new_callable=AsyncMock)
    mock_session = mocker.patch("mcp.client.session.ClientSession", new_callable=AsyncMock)
    
    mock_session_inst = AsyncMock()
    mock_session.return_value = mock_session_inst
    
    mock_tool = MagicMock()
    mock_tool.name = "loki_query"
    mock_tool.description = "Q"
    mock_tool.inputSchema = {}
    mock_res = MagicMock(tools=[mock_tool])
    mock_session_inst.list_tools.return_value = mock_res
    
    mock_stack_enter = mocker.patch("contextlib.AsyncExitStack.enter_async_context", new_callable=AsyncMock)
    mock_stack_enter.side_effect = ["streams", mock_session_inst] # returns streams then session
    
    client = MCPSseClient("http://sse")
    res = await client.list_tools()
    assert res[0]["name"] == "loki_query"

@pytest.mark.asyncio
async def test_mcp_sse_client_call_tool(mocker):
    # Mock contextlib AsyncExitStack which entering mock_sse
    mock_session_inst = AsyncMock()
    
    mock_content = MagicMock()
    mock_content.model_dump.return_value = {"text": "loki result"}
    mock_call_res = MagicMock(content=[mock_content])
    mock_session_inst.call_tool.return_value = mock_call_res
    
    mock_stack_enter = mocker.patch("contextlib.AsyncExitStack.enter_async_context", new_callable=AsyncMock)
    mock_stack_enter.side_effect = ["streams", mock_session_inst]
    
    client = MCPSseClient("http://sse")
    res = await client.call_tool("cmd", {})
    assert res[0]["text"] == "loki result"
