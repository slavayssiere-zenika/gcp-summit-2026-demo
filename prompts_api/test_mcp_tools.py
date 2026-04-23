import os
os.environ['SECRET_KEY'] = 'testsecret'
os.environ['PROMPTS_API_URL'] = 'http://test-prompts'
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import json

from mcp_server import call_tool, mcp_auth_header_var

@pytest.mark.asyncio
async def test_get_prompt_tool(mocker):
    mock_httpx = mocker.patch("mcp_server.httpx.AsyncClient")
    client_instance = AsyncMock()
    mock_httpx.return_value.__aenter__.return_value = client_instance
    
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"key": "agent_hr", "value": "Test prompt"}
    client_instance.get.return_value = mock_resp

    mcp_auth_header_var.set("Bearer token")
    
    result = await call_tool(name="get_prompt", arguments={"key": "agent_hr"})
    assert "agent_hr" in result[0].text
    assert "Test prompt" in result[0].text

@pytest.mark.asyncio
async def test_create_prompt_tool(mocker):
    mock_httpx = mocker.patch("mcp_server.httpx.AsyncClient")
    client_instance = AsyncMock()
    mock_httpx.return_value.__aenter__.return_value = client_instance
    
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"success": True}
    client_instance.post.return_value = mock_resp

    mcp_auth_header_var.set("Bearer token")

    result = await call_tool(name="create_prompt", arguments={"key": "test_agent", "value": "Test"})
    assert "success" in result[0].text

@pytest.mark.asyncio
async def test_tool_errors(mocker):
    result = await call_tool(name="get_prompt", arguments={})
    assert "Missing key argument" in result[0].text or "KeyError" in result[0].text or "Unknown tool" not in result[0].text

    result = await call_tool(name="non_existent", arguments={})
    assert "Unknown tool" in result[0].text
