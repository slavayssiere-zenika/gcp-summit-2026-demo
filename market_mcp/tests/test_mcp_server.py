import pytest
from unittest.mock import patch, MagicMock
from mcp_server import list_tools, call_tool
import json

@pytest.mark.asyncio
async def test_list_tools():
    tools = await list_tools()
    assert len(tools) == 6
    assert tools[0].name == "get_top_market_skills"
    assert tools[1].name == "get_market_demand_volume"
    assert tools[2].name == "log_ai_consumption"
    assert tools[3].name == "get_finops_report"
    assert tools[4].name == "get_infrastructure_topology"
    assert tools[5].name == "get_aiops_dashboard_data"

@pytest.mark.asyncio
@patch('mcp_server.client')
async def test_get_market_demand_volume(mock_client):
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
@patch('mcp_server.client')
async def test_get_top_market_skills(mock_client):
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

@pytest.mark.asyncio
@patch('google.cloud.trace_v1.TraceServiceClient')
async def test_get_infrastructure_topology(mock_trace_client_class):
    from mcp_server import get_infrastructure_topology
    mock_client = MagicMock()
    mock_trace_client_class.return_value = mock_client
    
    # Mocking trace objects
    mock_trace = MagicMock()
    mock_span = MagicMock()
    mock_span.span_id = "span1"
    mock_span.parent_span_id = None
    mock_span.labels = {"g.co/r/cloud_run_revision/service_name": "agent-api"}
    
    mock_span2 = MagicMock()
    mock_span2.span_id = "span2"
    mock_span2.parent_span_id = "span1"
    mock_span2.labels = {"g.co/r/cloud_run_revision/service_name": "users-api"}
    
    mock_trace.spans = [mock_span, mock_span2]
    mock_client.list_traces.return_value = [mock_trace]
    
    result = await get_infrastructure_topology(hours_lookback=1)
    
    assert "nodes" in result
    assert "links" in result
    # Filter only zenika nodes
    node_ids = [n["id"] for n in result["nodes"]]
    assert "agent-api" in node_ids
    assert "users-api" in node_ids
    
    assert len(result["links"]) == 1
    assert result["links"][0]["source"] == "agent-api"
    assert result["links"][0]["target"] == "users-api"
