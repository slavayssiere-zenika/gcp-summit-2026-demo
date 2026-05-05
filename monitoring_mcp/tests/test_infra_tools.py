import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from tools.infra_tools import (
    get_gcp_project_id,
    get_gcp_project_id_from_metadata,
    list_gcp_services_internal,
    get_infrastructure_topology
)
import os

def test_get_gcp_project_id():
    with patch.dict(os.environ, {"GCP_PROJECT_ID": "test-project"}):
        assert get_gcp_project_id() == "test-project"

@pytest.mark.asyncio
@patch('httpx.AsyncClient.get')
async def test_get_gcp_project_id_from_metadata(mock_get):
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.text = "test-metadata-project"
    mock_get.return_value = mock_res
    
    with patch.dict(os.environ, clear=True):
        assert await get_gcp_project_id_from_metadata() == "test-metadata-project"

@pytest.mark.asyncio
@patch('tools.infra_tools.get_gcp_project_id_from_metadata', new_callable=AsyncMock)
@patch('google.cloud.run_v2.ServicesAsyncClient')
async def test_list_gcp_services_internal(mock_client_class, mock_get_project):
    mock_get_project.return_value = "test-project"
    mock_client = mock_client_class.return_value
    
    class MockService:
        def __init__(self, name, uri, labels):
            self.name = name
            self.uri = uri
            self.labels = labels
            
    class AsyncIterator:
        def __init__(self, items):
            self.items = items
        def __aiter__(self):
            return self
        async def __anext__(self):
            if not self.items:
                raise StopAsyncIteration
            return self.items.pop(0)

    mock_client.list_services = AsyncMock(return_value=AsyncIterator([
        MockService("projects/test/locations/europe-west1/services/api-users", "https://users", {"env": "dev"}),
        MockService("projects/test/locations/europe-west1/services/other", "https://other", {})
    ]))
    
    results = await list_gcp_services_internal()
    assert len(results) == 1
    assert results[0]["name"] == "api-users"
    assert results[0]["location"] == "europe-west1"

@pytest.mark.asyncio
@patch('tools.infra_tools.get_gcp_project_id')
@patch('google.cloud.trace_v1.TraceServiceClient')
async def test_get_infrastructure_topology(mock_client_class, mock_get_project):
    mock_get_project.return_value = "test-project"
    mock_client = mock_client_class.return_value
    
    class MockSpan:
        def __init__(self, span_id, parent_span_id, labels):
            self.span_id = span_id
            self.parent_span_id = parent_span_id
            self.labels = labels
            
    class MockTrace:
        def __init__(self, spans):
            self.spans = spans
            
    mock_client.list_traces.return_value = [
        MockTrace([
            MockSpan("1", None, {"g.co/r/cloud_run_revision/service_name": "api-users"}),
            MockSpan("2", "1", {"db.system": "postgresql", "db.name": "users_db"})
        ])
    ]
    
    with patch('asyncio.to_thread', new_callable=AsyncMock) as mock_thread:
        mock_thread.return_value = mock_client.list_traces.return_value
        result = await get_infrastructure_topology(1)
        
    assert "nodes" in result
    assert "links" in result
    assert any(n["id"] == "api-users" for n in result["nodes"])
    assert any(n["id"] == "users_db" for n in result["nodes"])
