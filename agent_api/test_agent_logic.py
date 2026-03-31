import pytest
from unittest.mock import MagicMock, patch
import json
from conftest import app
from agent import list_users, get_user, create_user, get_items_by_user, run_agent_query

import anyio

def test_web_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

def test_web_static_files(client):
    assert client.get("/").status_code == 200
    assert client.get("/docs-users").status_code == 200
    assert client.get("/docs-items").status_code == 200
    assert client.get("/styles.css").status_code == 200

def test_list_users_tool_logic():
    mock_mcp = MagicMock()
    mock_mcp.call_tool.return_value = [{"text": '{"items": [{"id": 1, "username": "u1"}], "total": 1}'}]
    
    with patch("agent_api.agent.get_users_mcp", return_value=mock_mcp):
        result = list_users(0, 10)
        assert "items" in result["result"]
        assert "u1" in result["result"]

def test_get_user_tool_logic():
    mock_mcp = MagicMock()
    mock_mcp.call_tool.return_value = [{"text": '{"id": 1, "username": "u1"}'}]
    
    with patch("agent_api.agent.get_users_mcp", return_value=mock_mcp):
        result = get_user(1)
        assert "u1" in result["result"]

def test_create_user_tool_logic():
    mock_mcp = MagicMock()
    mock_mcp.call_tool.return_value = [{"text": '{"id": 1, "username": "newuser"}'}]
    
    with patch("agent_api.agent.get_users_mcp", return_value=mock_mcp):
        result = create_user("newuser", "new@e.com", "New User")
        assert "newuser" in result["result"]

def test_get_items_by_user_tool_logic():
    mock_mcp = MagicMock()
    mock_mcp.call_tool.return_value = [{"text": '{"items": [{"id": 10, "name": "item1"}], "total": 1}'}]
    
    with patch("agent_api.agent.get_items_mcp", return_value=mock_mcp):
        result = get_items_by_user(1)
        assert "item1" in result["result"]

def test_run_agent_query_logic():
    # Mock the Agent from ADK
    mock_agent = MagicMock()
    mock_agent.run.return_value = MagicMock()
    mock_agent.run.return_value.text = "Hello result"
    
    with patch("agent_api.agent.Agent", return_value=mock_agent):
        async def run_test():
            return await run_agent_query("hello")
        
        result = anyio.run(run_test)
        assert result["response"] == "Hello result"
        assert result["source"] == "gemini"

def test_query_endpoint(client):
    # Mocking agent run to avoid actual call
    mock_result = {"response": "Hi", "source": "gemini", "data": {}}
    with patch("agent_api.agent.run_agent_query", return_value=mock_result):
        response = client.post("/query", json={"query": "test"})
        assert response.status_code == 200
        assert response.json()["response"] == "Hi"
