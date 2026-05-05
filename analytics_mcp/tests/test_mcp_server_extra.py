import pytest
import os
import json
from unittest.mock import MagicMock, patch, AsyncMock
from mcp_server import (
    get_gcp_project_id_from_metadata,
    get_gcp_project_id,
    call_tool,
    get_aiops_dashboard_data_internal,
    list_tools,
    main
)

@pytest.mark.asyncio
async def test_get_gcp_project_id_from_metadata_env():
    with patch.dict(os.environ, {"GCP_PROJECT_ID": "test-project-123"}):
        pid = await get_gcp_project_id_from_metadata()
        assert pid == "test-project-123"

@pytest.mark.asyncio
@patch('httpx.AsyncClient.get')
async def test_get_gcp_project_id_from_metadata_http(mock_get):
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.text = "test-metadata-project\n"
    mock_get.return_value = mock_res
    
    with patch.dict(os.environ, clear=True):
        pid = await get_gcp_project_id_from_metadata()
        assert pid == "test-metadata-project"

def test_get_gcp_project_id_adc():
    with patch.dict(os.environ, {"GCP_PROJECT_ID": ""}):
        with patch('google.auth.default') as mock_default:
            mock_default.return_value = (None, "adc-project")
            assert get_gcp_project_id() == "adc-project"

@pytest.mark.asyncio
@patch('mcp_server.client')
async def test_call_tool_detect_usage_anomalies(mock_client):
    mock_query_job = MagicMock()
    mock_query_job.result.return_value = []
    mock_client.query.return_value = mock_query_job

    result = await call_tool("detect_usage_anomalies", {"threshold_tokens_per_hour": 1000})
    assert len(result) == 1
    data = json.loads(result[0].text)
    assert "anomalies" in data

@pytest.mark.asyncio
@patch('mcp_server.get_aiops_dashboard_data_internal')
async def test_call_tool_get_aiops_dashboard_data(mock_internal):
    mock_internal.return_value = {"dashboard": "data"}
    result = await call_tool("get_aiops_dashboard_data", {})
    assert len(result) == 1
    data = json.loads(result[0].text)
    assert data == {"dashboard": "data"}

@pytest.mark.asyncio
@patch('mcp_server.client')
async def test_get_aiops_dashboard_data_internal_execution(mock_client):
    mock_query_job = MagicMock()
    
    class MockRow(dict):
        def __init__(self, d):
            super().__init__(d)
            for k, v in d.items():
                setattr(self, k, v)
                
    mock_query_job.result.return_value = [MockRow({"month": None, "day": None, "count": 1})]
    mock_client.query.return_value = mock_query_job
    
    res = await get_aiops_dashboard_data_internal()
    assert "monthly" in res
    assert "daily" in res

@pytest.mark.asyncio
@patch('mcp_server.server.run', new_callable=AsyncMock)
@patch('mcp.server.stdio.stdio_server')
async def test_main(mock_stdio_server, mock_server_run):
    # Setup mock stdio server context manager
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__.return_value = (MagicMock(), MagicMock())
    mock_stdio_server.return_value = mock_ctx
    
    await main()
    mock_server_run.assert_called_once()
