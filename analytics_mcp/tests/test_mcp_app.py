import pytest
from unittest.mock import MagicMock, patch, AsyncMock, mock_open
from fastapi.testclient import TestClient
from mcp_app import app, report_exception_to_prompts_api
import json

client = TestClient(app, raise_server_exceptions=False)

@pytest.fixture
def override_verify_jwt():
    def _override():
        return {"sub": "user@example.com", "role": "admin"}
    from mcp_app import verify_jwt
    app.dependency_overrides[verify_jwt] = _override
    yield
    app.dependency_overrides.pop(verify_jwt, None)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "analytics-mcp"}

@patch('mcp_server.client', MagicMock())
def test_ready_success():
    with patch('asyncio.to_thread', new_callable=AsyncMock) as mock_thread:
        response = client.get("/ready")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

@patch('mcp_server.client', None)
def test_ready_no_client():
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "unhealthy"

def test_get_version():
    response = client.get("/version")
    assert response.status_code == 200
    assert "version" in response.json()

def test_get_spec():
    with patch('builtins.open', mock_open(read_data="test spec")):
        response = client.get("/spec")
        assert response.status_code == 200

@pytest.mark.asyncio
@patch('httpx.AsyncClient.post')
async def test_report_exception_to_prompts_api(mock_post):
    mock_post.return_value = MagicMock(status_code=200)
    await report_exception_to_prompts_api("test_service", "error", "trace", "token")
    mock_post.assert_called_once()

@pytest.mark.asyncio
async def test_global_exception_handler():
    # Trigger global exception handler by hitting a route that raises Exception
    @app.get("/trigger_error")
    def trigger_error():
        raise ValueError("test error")
        
    with patch('mcp_app.report_exception_to_prompts_api', new_callable=AsyncMock) as mock_report:
        response = client.get("/trigger_error", headers={"Authorization": "Bearer token"})
        assert response.status_code == 500
        mock_report.assert_called_once()

def test_get_tools(override_verify_jwt):
    with patch('mcp_app.list_tools', new_callable=AsyncMock) as mock_list_tools:
        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.description = "desc"
        mock_tool.inputSchema = {}
        mock_list_tools.return_value = [mock_tool]
        
        response = client.get("/mcp/tools", headers={"Authorization": "Bearer token"})
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["name"] == "test_tool"

@patch('mcp_app.call_tool', new_callable=AsyncMock)
def test_execute_tool(mock_call_tool, override_verify_jwt):
    mock_res = MagicMock()
    mock_res.model_dump.return_value = {"text": "success"}
    mock_call_tool.return_value = [mock_res]
    
    response = client.post("/mcp/call", json={"name": "test_tool", "arguments": {}}, headers={"Authorization": "Bearer token"})
    assert response.status_code == 200
    assert response.json()["result"][0]["text"] == "success"

@patch('redis.from_url')
def test_get_aiops_metrics_cache_hit(mock_redis_from_url, override_verify_jwt):
    mock_redis = MagicMock()
    mock_redis.get.return_value = json.dumps({"dashboard": "data"})
    mock_redis_from_url.return_value = mock_redis
    
    response = client.get("/metrics/aiops", headers={"Authorization": "Bearer token"})
    assert response.status_code == 200
    assert response.json() == {"dashboard": "data"}

@patch('mcp_app.bq_client')
@patch('httpx.AsyncClient.post', new_callable=AsyncMock)
def test_detect_finops_anomalies(mock_post, mock_bq_client, override_verify_jwt):
    mock_query_job = MagicMock()

    class MockRow:
        def __init__(self, email, total):
            self.user_email = email
            self.total_tokens = total

    mock_query_job.result.return_value = [MockRow("bad_user@example.com", 600000)]
    mock_bq_client.query.return_value = mock_query_job

    mock_post_res = MagicMock()
    mock_post_res.status_code = 200
    mock_post.return_value = mock_post_res

    response = client.post("/admin/finops/detect", headers={"Authorization": "Bearer token"})
    assert response.status_code == 200
    assert response.json()["anomalies_detected"] == 1
    assert response.json()["details"][0]["email"] == "bad_user@example.com"
