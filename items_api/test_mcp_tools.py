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
async def test_mcp_tools_list_items(mock_httpx_mcp):
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"items": [], "total": 0}
    mock_httpx_mcp.get.return_value = mock_resp
    
    result = await call_tool("list_items", {"skip": 0, "limit": 10})
    assert "total" in result[0].text

@pytest.mark.asyncio
async def test_mcp_tools_get_item(mock_httpx_mcp):
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"id": 1, "name": "test"}
    mock_httpx_mcp.get.return_value = mock_resp
    
    result = await call_tool("get_item", {"item_id": 1})
    assert "test" in result[0].text

@pytest.mark.asyncio
async def test_mcp_tools_create_item(mock_httpx_mcp):
    mock_resp = MagicMock(status_code=201)
    mock_resp.json.return_value = {"id": 1, "name": "new"}
    mock_httpx_mcp.post.return_value = mock_resp
    
    result = await call_tool("create_item", {"name": "new", "user_id": 1})
    assert "new" in result[0].text

@pytest.mark.asyncio
async def test_mcp_tools_get_item_with_user(mock_httpx_mcp):
    item_resp = MagicMock(status_code=200)
    item_resp.json.return_value = {"id": 1, "name": "item", "user_id": 1}
    
    user_resp = MagicMock(status_code=200)
    user_resp.json.return_value = {"username": "foo"}
    
    mock_httpx_mcp.get.side_effect = [item_resp, user_resp]
    
    result = await call_tool("get_item_with_user", {"item_id": 1})
    assert "foo" in result[0].text

@pytest.mark.asyncio
async def test_mcp_tools_get_item_with_user_failed_user(mock_httpx_mcp):
    item_resp = MagicMock(status_code=200)
    item_resp.json.return_value = {"id": 1, "name": "item", "user_id": 999}
    
    user_resp = MagicMock(status_code=404)
    user_resp.json.return_value = {"detail": "Not found"}
    
    mock_httpx_mcp.get.side_effect = [item_resp, user_resp]
    
    result = await call_tool("get_item_with_user", {"item_id": 1})
    assert "item" in result[0].text
    assert "username" not in result[0].text

@pytest.mark.asyncio
async def test_mcp_tools_update_item(mock_httpx_mcp):
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"id": 1, "name": "upd"}
    mock_httpx_mcp.put.return_value = mock_resp
    
    result = await call_tool("update_item", {"item_id": 1, "name": "upd"})
    assert "upd" in result[0].text

@pytest.mark.asyncio
async def test_mcp_tools_delete_item(mock_httpx_mcp):
    mock_resp = MagicMock(status_code=204)
    mock_httpx_mcp.delete.return_value = mock_resp
    
    result = await call_tool("delete_item", {"item_id": 1})
    assert "Item deleted successfully" in result[0].text

@pytest.mark.asyncio
async def test_mcp_tools_health_check(mock_httpx_mcp):
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"status": "ok"}
    mock_httpx_mcp.get.return_value = mock_resp
    
    result = await call_tool("health_check", {})
    assert "ok" in result[0].text

@pytest.mark.asyncio
async def test_mcp_tools_search(mock_httpx_mcp):
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"items": [{"name": "test item"}]}
    mock_httpx_mcp.get.return_value = mock_resp
    
    result = await call_tool("search_items", {"query": "test"})
    assert "test item" in result[0].text

@pytest.mark.asyncio
async def test_mcp_tools_get_items_by_user(mock_httpx_mcp):
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"items": []}
    mock_httpx_mcp.get.return_value = mock_resp
    
    result = await call_tool("get_items_by_user", {"user_id": "1"})
    assert "items" in result[0].text

@pytest.mark.asyncio
async def test_mcp_tools_get_items_by_user_bad_id(mock_httpx_mcp):
    result = await call_tool("get_items_by_user", {"user_id": "bad"})
    assert "must be an integer" in result[0].text

@pytest.mark.asyncio
async def test_mcp_tools_stats(mock_httpx_mcp):
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"total": 5}
    mock_httpx_mcp.get.return_value = mock_resp
    
    result = await call_tool("get_item_stats", {})
    assert "total" in result[0].text

@pytest.mark.asyncio
async def test_mcp_tools_unknown(mock_httpx_mcp):
    result = await call_tool("unknown_foo", {})
    assert "Unknown tool" in result[0].text

@pytest.mark.asyncio
async def test_mcp_tools_http_error(mock_httpx_mcp):
    mock_resp = MagicMock(status_code=404, text="Not Found")
    e = httpx.HTTPStatusError("404", request=MagicMock(), response=mock_resp)
    mock_httpx_mcp.get.side_effect = e
    
    result = await call_tool("get_item", {"item_id": 999})
    assert "HTTP Error: 404" in result[0].text

@pytest.mark.asyncio
async def test_mcp_tools_generic_error(mock_httpx_mcp):
    mock_httpx_mcp.get.side_effect = ValueError("Boom")
    result = await call_tool("get_item", {"item_id": 1})
    data = json.loads(result[0].text)
    assert data["success"] is False
    assert "Boom" in data["error"]


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
    
    resp = client.post("/mcp/call", json={"name": "health_check", "arguments": {}}, headers={"Authorization": "Bearer x"})
    assert resp.status_code == 200
    assert "status" in resp.json()["result"][0]["text"]

def test_mcp_app_call_error(mocker):
    mock_call_tool = mocker.patch("mcp_app.call_tool", new_callable=AsyncMock)
    mock_call_tool.side_effect = Exception("General Failure")
    
    resp = client.post("/mcp/call", json={"name": "health_check", "arguments": {}})
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
