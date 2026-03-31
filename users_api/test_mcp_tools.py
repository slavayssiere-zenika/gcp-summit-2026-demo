import pytest
import json
from unittest.mock import MagicMock, patch
from mcp_server import call_tool
from mcp.types import TextContent

import anyio

def test_call_tool_list_users():
    # Mock httpx.AsyncClient.get
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"items": [], "total": 0}
    mock_response.raise_for_status = MagicMock()
    
    with patch("httpx.AsyncClient.get", return_value=mock_response) as mock_get:
        async def run_test():
            return await call_tool("list_users", {"skip": 0, "limit": 10})
        
        result = anyio.run(run_test)
        
        assert isinstance(result[0], TextContent)
        data = json.loads(result[0].text)
        assert data["total"] == 0
        mock_get.assert_called_once()

def test_call_tool_get_user():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": 1, "username": "test"}
    mock_response.raise_for_status = MagicMock()
    
    with patch("httpx.AsyncClient.get", return_value=mock_response) as mock_get:
        async def run_test():
            return await call_tool("get_user", {"user_id": 1})
            
        result = anyio.run(run_test)
        assert "test" in result[0].text
        mock_get.assert_called_once()

def test_call_tool_create_user():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": 1, "username": "new"}
    mock_response.raise_for_status = MagicMock()
    
    with patch("httpx.AsyncClient.post", return_value=mock_response) as mock_post:
        async def run_test():
            return await call_tool("create_user", {"username": "new", "email": "n@e.com"})
            
        result = anyio.run(run_test)
        assert "new" in result[0].text
        mock_post.assert_called_once()
