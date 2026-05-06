import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp_server import call_tool, mcp_auth_header_var


@pytest.fixture(autouse=True, scope="session")
def mcp_tools_env():
    import os
    os.environ['SECRET_KEY'] = 'testsecret'
    os.environ["MISSIONS_API_URL"] = "http://test-missions"
    yield
    os.environ.pop('SECRET_KEY', None)
    os.environ.pop("MISSIONS_API_URL", None)


@pytest.mark.asyncio
async def test_list_missions_tool(mocker):
    mock_httpx = mocker.patch("mcp_server.httpx.AsyncClient")
    client_instance = AsyncMock()
    mock_httpx.return_value.__aenter__.return_value = client_instance

    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = [{"id": 1, "name": "Mission 1"}]
    client_instance.get.return_value = mock_resp

    mcp_auth_header_var.set("Bearer token")

    result = await call_tool(name="list_missions", arguments={})
    data = json.loads(result[0].text)
    
    assert data["missions"][0]["name"] == "Mission 1"


@pytest.mark.asyncio
async def test_tool_errors(mocker):
    mock_httpx = mocker.patch("mcp_server.httpx.AsyncClient")
    client_instance = AsyncMock()
    mock_httpx.return_value.__aenter__.return_value = client_instance

    mock_resp = MagicMock(status_code=422)
    mock_resp.json.return_value = {"detail": "Missing title argument"}
    # On mocke raise_for_status() pour lever une exception qui contient le texte
    import httpx
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "422 Client Error", request=MagicMock(), response=mock_resp
    )
    client_instance.post.return_value = mock_resp

    result = await call_tool(name="create_mission", arguments={})
    data = json.loads(result[0].text)
    assert data.get("success") is False
    assert "Missing title argument" in data.get("error", "") or "422" in data.get("error", "")

    result = await call_tool(name="non_existent", arguments={})
    data = json.loads(result[0].text)
    assert data.get("success") is False
    assert "Unknown tool" in data.get("error", "")
