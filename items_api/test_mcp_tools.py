import pytest
import json
from unittest.mock import MagicMock, patch
from mcp_server import call_tool
from mcp.types import TextContent

import anyio

def test_call_tool_list_items():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"items": [], "total": 0}
    mock_response.raise_for_status = MagicMock()
    
    with patch("httpx.AsyncClient.get", return_value=mock_response) as mock_get:
        async def run_test():
            return await call_tool("list_items", {"skip": 0, "limit": 10})
        
        result = anyio.run(run_test)
        
        assert isinstance(result[0], TextContent)
        data = json.loads(result[0].text)
        assert data["total"] == 0
        mock_get.assert_called_once()

def test_call_tool_get_items_by_user():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"items": [{"id": 1, "name": "Item 1", "user_id": 1}], "total": 1}
    mock_response.raise_for_status = MagicMock()
    
    with patch("httpx.AsyncClient.get", return_value=mock_response) as mock_get:
        async def run_test():
            return await call_tool("get_items_by_user", {"user_id": 1})
            
        result = anyio.run(run_test)
        assert "Item 1" in result[0].text
        mock_get.assert_called_once_with("http://items-api:8001/items/user/1", params={"skip": 0, "limit": 100})

def test_call_tool_get_items_by_user_invalid_id():
    async def run_test():
        return await call_tool("get_items_by_user", {"user_id": "abc"})
        
    result = anyio.run(run_test)
    assert "must be an integer" in result[0].text
