import json
from unittest.mock import AsyncMock, MagicMock
import pytest
from mcp_server import call_tool
import httpx

@pytest.fixture
def mock_httpx_mcp(mocker):
    mock = mocker.patch("mcp_server.httpx.AsyncClient")
    client_instance = AsyncMock()
    mock.return_value.__aenter__.return_value = client_instance
    return client_instance

@pytest.mark.asyncio
async def test_mcp_tools_get_user_availability(mock_httpx_mcp):
    # Mock /users/1
    user_resp = MagicMock(status_code=200)
    user_resp.json.return_value = {"unavailability_periods": []}
    
    # Mock /missions/user/1/active
    missions_resp = MagicMock(status_code=200)
    missions_resp.json.return_value = {"active_missions": []}
    
    mock_httpx_mcp.get.side_effect = [user_resp, missions_resp]

    result = await call_tool("get_user_availability", {"user_id": 1})
    data = json.loads(result[0].text)
    
    assert data["is_available"] is True
    assert data["conflict_detected"] is False

@pytest.mark.asyncio
async def test_mcp_tools_get_users_availability_bulk(mock_httpx_mcp):
    user_resp = MagicMock(status_code=200)
    user_resp.json.return_value = {"unavailability_periods": []}
    
    missions_resp = MagicMock(status_code=200)
    missions_resp.json.return_value = {"active_missions": [{"mission_title": "Test"}]}
    
    mock_httpx_mcp.get.side_effect = [user_resp, missions_resp, user_resp, missions_resp]

    result = await call_tool("get_users_availability_bulk", {"user_ids": [1, 2]})
    data = json.loads(result[0].text)
    
    assert len(data) == 2
    assert data[0]["is_available"] is False
    assert data[0]["conflict_detected"] is True

@pytest.mark.asyncio
async def test_mcp_tools_get_user_duplicates(mock_httpx_mcp):
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = [{"users": []}]
    mock_httpx_mcp.get.return_value = mock_resp

    result = await call_tool("get_user_duplicates", {})
    data = json.loads(result[0].text)
    assert len(data) == 1

@pytest.mark.asyncio
async def test_mcp_tools_merge_users(mock_httpx_mcp):
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"message": "Success"}
    mock_httpx_mcp.post.return_value = mock_resp

    result = await call_tool("merge_users", {"source_id": 1, "target_id": 2})
    data = json.loads(result[0].text)
    assert data["message"] == "Success"

@pytest.mark.asyncio
async def test_mcp_tools_search_anonymous_users(mock_httpx_mcp):
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"items": [], "total": 0}
    mock_httpx_mcp.get.return_value = mock_resp

    result = await call_tool("search_anonymous_users", {"limit": 10})
    data = json.loads(result[0].text)
    assert "items" in data

@pytest.mark.asyncio
async def test_mcp_tools_get_users_bulk(mock_httpx_mcp):
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = [{"id": 1}]
    mock_httpx_mcp.post.return_value = mock_resp

    result = await call_tool("get_users_bulk", {"user_ids": [1]})
    data = json.loads(result[0].text)
    assert len(data) == 1

@pytest.mark.asyncio
async def test_mcp_tools_http_409(mock_httpx_mcp):
    mock_resp = MagicMock(status_code=409, text="Conflict")
    e = httpx.HTTPStatusError("409 Conflict", request=MagicMock(), response=mock_resp)
    mock_httpx_mcp.post.side_effect = e

    result = await call_tool("create_user", {"username": "test", "email": "e@e.com"})
    data = json.loads(result[0].text)
    assert data["success"] is False
    assert "CONFLIT (409)" in data["error"]
