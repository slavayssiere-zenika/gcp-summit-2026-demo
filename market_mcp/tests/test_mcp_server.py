import pytest
from unittest.mock import patch, MagicMock
from mcp_server import list_tools, call_tool
import json

@pytest.mark.asyncio
async def test_list_tools():
    tools = await list_tools()
    assert len(tools) == 2
    assert tools[0].name == "get_top_market_skills"
    assert tools[1].name == "get_market_demand_volume"

@pytest.mark.asyncio
@patch('mcp_server.bigquery.Client')
async def test_get_market_demand_volume(mock_client_class):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    mock_query_job = MagicMock()
    # Mocking BigQuery Row
    mock_row = MagicMock()
    mock_row.volume = 42
    mock_query_job.result.return_value = [mock_row]
    mock_client.query.return_value = mock_query_job
    
    arguments = {"category": "Développeur"}
    result = await call_tool("get_market_demand_volume", arguments)
    
    assert len(result) == 1
    assert result[0].type == "text"
    
    data = json.loads(result[0].text)
    assert data["category"] == "Développeur"
    assert data["volume"] == 42
    
@pytest.mark.asyncio
@patch('mcp_server.bigquery.Client')
async def test_get_top_market_skills(mock_client_class):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    mock_query_job = MagicMock()
    mock_row1 = MagicMock()
    mock_row1.skill = "Python"
    mock_row1.demand_count = 100
    mock_row2 = MagicMock()
    mock_row2.skill = "SQL"
    mock_row2.demand_count = 80
    
    mock_query_job.result.return_value = [mock_row1, mock_row2]
    mock_client.query.return_value = mock_query_job
    
    arguments = {"category": "Data Engineer", "limit": 2}
    result = await call_tool("get_top_market_skills", arguments)
    
    assert len(result) == 1
    data = json.loads(result[0].text)
    assert len(data) == 2
    assert data[0]["skill"] == "Python"
    assert data[0]["demand_count"] == 100
    assert data[1]["skill"] == "SQL"
    assert data[1]["demand_count"] == 80
