import os
os.environ['SECRET_KEY'] = 'testsecret'
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

# Patch instrument_app before importing mcp_app to prevent telemetry errors during testing
with patch("opentelemetry.instrumentation.fastapi.FastAPIInstrumentor.instrument_app"):
    from mcp_app import app

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "cv-mcp"}

@patch("mcp_app.list_tools")
def test_get_tools_success(mock_list_tools):
    # Setup mock tool
    mock_tool = MagicMock()
    mock_tool.name = "my_tool"
    mock_tool.description = "A mock tool"
    mock_tool.inputSchema = {"type": "object"}
    mock_list_tools.return_value = [mock_tool]

    # Test
    response = client.get("/mcp/tools")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "my_tool"
    assert data[0]["description"] == "A mock tool"
    assert data[0]["inputSchema"] == {"type": "object"}

@patch("mcp_app.call_tool")
def test_execute_tool_success(mock_call_tool):
    # Setup mock result
    mock_result = MagicMock()
    mock_result.model_dump.return_value = {"output": "success"}
    mock_call_tool.return_value = [mock_result]

    # Test
    response = client.post(
        "/mcp/call",
        json={"name": "my_tool", "arguments": {"arg1": "value1"}},
        headers={"Authorization": "Bearer fake_token"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["result"] == [{"output": "success"}]
    mock_call_tool.assert_called_once_with("my_tool", {"arg1": "value1"})

@patch("mcp_app.call_tool")
def test_execute_tool_error(mock_call_tool):
    mock_call_tool.side_effect = Exception("Tool execution failed")

    # Test
    response = client.post(
        "/mcp/call",
        json={"name": "bad_tool", "arguments": {}}
    )
    assert response.status_code == 500
    data = response.json()
    assert "Tool execution failed" in data["detail"]
