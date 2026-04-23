"""
Tests unitaires pour monitoring_mcp
"""

import pytest
import json
from unittest.mock import patch, MagicMock, AsyncMock
from mcp_server import list_tools, call_tool

# ---------------------------------------------------------------------------
# Tests check_component_health
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_component_health_redis_success(mocker):
    """check_component_health pour 'redis' doit ping Redis et retourner healthy."""
    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    import redis as redis_lib
    mocker.patch.object(redis_lib, "from_url", return_value=mock_redis)

    result = await call_tool("check_component_health", {"component_name": "redis-cache"})
    assert len(result) == 1
    data = json.loads(result[0].text)
    assert data["status"] == "healthy"
    assert "redis" in data.get("component", "").lower() or "redis" in data.get("message", "").lower()


@pytest.mark.asyncio
async def test_check_component_health_redis_down(mocker):
    """check_component_health pour Redis hors-ligne doit retourner unhealthy."""
    import redis as redis_lib
    mocker.patch.object(redis_lib, "from_url", side_effect=Exception("Connection refused"))

    result = await call_tool("check_component_health", {"component_name": "redis-cache"})
    assert len(result) == 1
    data = json.loads(result[0].text)
    assert data["status"] in ["unhealthy", "error"]


@pytest.mark.asyncio
async def test_check_component_health_unknown_component():
    """Un composant inconnu doit retourner status='not_found'."""
    result = await call_tool("check_component_health", {"component_name": "totally-unknown-xyz"})
    assert len(result) == 1
    data = json.loads(result[0].text)
    assert data["status"] in ["not_found", "unknown", "error", "unreachable"]

# ---------------------------------------------------------------------------
# Tests gestion d'erreur générale
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unknown_tool_returns_error_dict():
    """Un tool inconnu doit retourner un dict d'erreur structuré (pas une exception)."""
    result = await call_tool("definitely_not_a_real_tool", {})
    assert len(result) == 1
    data = json.loads(result[0].text)
    assert "error" in data
    assert "Unknown tool" in data["error"]

# ---------------------------------------------------------------------------
# Tests tools list
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_tools_returns_all_expected_tools():
    """list_tools doit retourner tous les outils attendus du monitoring_mcp."""
    tools = await list_tools()
    tool_names = [t.name for t in tools]

    expected_tools = [
        "get_infrastructure_topology",
        "get_service_logs",
        "list_gcp_services",
        "check_component_health",
        "check_all_components_health",
        "get_ingestion_pipeline_status",
        "search_cloud_logs_by_trace",
        "get_recent_500_errors",
        "inspect_pubsub_dlq",
        "get_redis_invalidation_state",
        "execute_read_only_query",
    ]
    for tool in expected_tools:
        assert tool in tool_names, f"Tool '{tool}' manquant dans list_tools()"
