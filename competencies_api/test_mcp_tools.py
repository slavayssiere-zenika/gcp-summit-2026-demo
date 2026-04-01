import pytest
import json
from unittest.mock import MagicMock, patch, AsyncMock
from mcp_server import call_tool, list_tools, main
from mcp_app import app as mcp_app
from fastapi.testclient import TestClient
from mcp.types import TextContent
import httpx

client = TestClient(mcp_app)

@pytest.fixture
def mock_httpx_mcp(mocker):
    mock = mocker.patch("mcp_server.httpx.AsyncClient")
    client_instance = AsyncMock()
    mock.return_value.__aenter__.return_value = client_instance
    return client_instance

@pytest.mark.asyncio
async def test_mcp_tools_list_competencies(mock_httpx_mcp):
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"items": [], "total": 0}
    mock_httpx_mcp.get.return_value = mock_resp
    
    result = await call_tool("list_competencies", {"skip": 0, "limit": 10})
    assert "total" in result[0].text

@pytest.mark.asyncio
async def test_mcp_tools_get_competency(mock_httpx_mcp):
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"id": 1, "name": "Python"}
    mock_httpx_mcp.get.return_value = mock_resp
    
    result = await call_tool("get_competency", {"competency_id": 1})
    assert "Python" in result[0].text

@pytest.mark.asyncio
async def test_mcp_tools_create_competency(mock_httpx_mcp):
    mock_resp = MagicMock(status_code=201)
    mock_resp.json.return_value = {"id": 1, "name": "Python"}
    mock_httpx_mcp.post.return_value = mock_resp
    
    result = await call_tool("create_competency", {"name": "Python"})
    assert "Python" in result[0].text

@pytest.mark.asyncio
async def test_mcp_tools_delete_competency(mock_httpx_mcp):
    mock_resp = MagicMock(status_code=204)
    mock_httpx_mcp.delete.return_value = mock_resp
    
    result = await call_tool("delete_competency", {"competency_id": 1})
    assert "deleted" in result[0].text

@pytest.mark.asyncio
async def test_mcp_tools_assign_to_user(mock_httpx_mcp):
    mock_resp = MagicMock(status_code=201)
    mock_resp.json.return_value = {"status": "assigned"}
    mock_httpx_mcp.post.return_value = mock_resp
    
    result = await call_tool("assign_competency_to_user", {"user_id": 1, "competency_id": 1})
    assert "assigned" in result[0].text

@pytest.mark.asyncio
async def test_mcp_tools_remove_from_user(mock_httpx_mcp):
    mock_resp = MagicMock(status_code=204)
    mock_httpx_mcp.delete.return_value = mock_resp
    
    result = await call_tool("remove_competency_from_user", {"user_id": 1, "competency_id": 1})
    assert "removed" in result[0].text

@pytest.mark.asyncio
async def test_mcp_tools_list_user_competencies(mock_httpx_mcp):
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = [{"id": 1, "name": "Python"}]
    mock_httpx_mcp.get.return_value = mock_resp
    
    result = await call_tool("list_user_competencies", {"user_id": 1})
    assert "Python" in result[0].text

@pytest.mark.asyncio
async def test_mcp_tools_unknown(mock_httpx_mcp):
    result = await call_tool("unknown_foo", {})
    assert "Unknown tool" in result[0].text

@pytest.mark.asyncio
async def test_mcp_tools_generic_error(mock_httpx_mcp):
    mock_httpx_mcp.get.side_effect = ValueError("Boom")
    result = await call_tool("get_competency", {"competency_id": 1})
    assert "Error: Boom" in result[0].text


# MCP App Tests
def test_mcp_app_tools_list():
    resp = client.get("/mcp/tools")
    assert resp.status_code == 200
    tools = resp.json()
    assert len(tools) > 5

def test_mcp_app_call_success(mocker):
    # Mock the underlying call_tool function directly
    mock_call_tool = mocker.patch("mcp_app.call_tool", new_callable=AsyncMock)
    mock_call_tool.return_value = [TextContent(type="text", text='{"status": "ok"}')]
    
    resp = client.post("/mcp/call", json={"name": "list_competencies", "arguments": {}}, headers={"Authorization": "Bearer x"})
    assert resp.status_code == 200
    assert "status" in resp.json()["result"][0]["text"]

def test_mcp_app_call_error(mocker):
    mock_call_tool = mocker.patch("mcp_app.call_tool", new_callable=AsyncMock)
    mock_call_tool.side_effect = Exception("General Failure")
    
    resp = client.post("/mcp/call", json={"name": "list_competencies", "arguments": {}})
    assert resp.status_code == 500
    assert "General Failure" in resp.json()["detail"]

def test_mcp_app_health():
    resp = client.get("/health")
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_mcp_server_main(mocker):
    mock_context = MagicMock()
    mock_context.__aenter__ = AsyncMock(return_value=("r", "w"))
    mock_context.__aexit__ = AsyncMock(return_value=None)
    mocker.patch("mcp.server.stdio.stdio_server", return_value=mock_context)
    
    mock_run = mocker.patch("mcp_server.server.run", new_callable=AsyncMock)
    await main()
    mock_run.assert_called_once()
