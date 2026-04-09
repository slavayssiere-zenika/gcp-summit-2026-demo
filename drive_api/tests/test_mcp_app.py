import os
os.environ['SECRET_KEY'] = 'testsecret'
from fastapi.testclient import TestClient
from mcp_app import app
import pytest

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_get_tools():
    response = client.get("/mcp/tools")
    assert response.status_code == 200
    tools = response.json()
    assert isinstance(tools, list)
    assert len(tools) > 0
    # verify add_drive_folder exists
    assert any(t["name"] == "add_drive_folder" for t in tools)

def test_call_tool_invalid():
    response = client.post("/mcp/call", json={"name": "invalid_tool"})
    assert response.status_code == 200
    result = response.json()["result"]
    assert "Unknown tool" in result[0]["text"]
