import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import json

# Patch USERS_API_URL, COMPETENCIES_API_URL, CV_API_URL
import os
os.environ["CV_API_URL"] = "http://test-cv"

from mcp_server import call_tool, mcp_auth_header_var

@pytest.mark.asyncio
async def test_analyze_cv_tool(mocker):
    mock_httpx = mocker.patch("mcp_server.httpx.AsyncClient")
    client_instance = AsyncMock()
    mock_httpx.return_value.__aenter__.return_value = client_instance
    
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"message": "Success", "user_id": 1, "competencies_assigned": 5}
    client_instance.post.return_value = mock_resp

    mcp_auth_header_var.set("Bearer token")
    
    result = await call_tool(name="analyze_cv", arguments={"url": "http://test.com/cv"})
    assert "Success" in result[0].text

@pytest.mark.asyncio
async def test_search_best_candidates_tool(mocker):
    mock_httpx = mocker.patch("mcp_server.httpx.AsyncClient")
    client_instance = AsyncMock()
    mock_httpx.return_value.__aenter__.return_value = client_instance
    
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = [{"user_id": 1, "similarity_score": 0.9}]
    client_instance.get.return_value = mock_resp

    mcp_auth_header_var.set("Bearer token")

    result = await call_tool(name="search_best_candidates", arguments={"query": "Java developer", "limit": 5})
    assert "similarity_score" in result[0].text

@pytest.mark.asyncio
async def test_recalculate_competencies_tree_tool(mocker):
    mock_httpx = mocker.patch("mcp_server.httpx.AsyncClient")
    client_instance = AsyncMock()
    mock_httpx.return_value.__aenter__.return_value = client_instance
    
    import httpx
    # simulate HTTPError for branch coverage
    # First success
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"tree": {"Root": "Child"}}
    client_instance.post.return_value = mock_resp

    mcp_auth_header_var.set("Bearer token")

    result = await call_tool(name="recalculate_competencies_tree", arguments={})
    assert "Root" in result[0].text
    
    # 2. exception coverage
    client_instance.post.side_effect = Exception("General error")
    result = await call_tool(name="recalculate_competencies_tree", arguments={})
    assert "Request failed: General error" in result[0].text

@pytest.mark.asyncio
async def test_tool_errors(mocker):
    result = await call_tool(name="analyze_cv", arguments={})
    assert "Error: Missing url argument" in result[0].text

    result = await call_tool(name="search_best_candidates", arguments={})
    assert "Error: Missing query argument" in result[0].text

    result = await call_tool(name="non_existent", arguments={})
    assert "Unknown tool" in result[0].text
