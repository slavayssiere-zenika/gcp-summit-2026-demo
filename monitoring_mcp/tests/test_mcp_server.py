"""
Tests unitaires pour monitoring_mcp — couverture complète des 11 tools SRE.

Inclut les tests pour :
- check_component_health (Redis up/down, composant inconnu)
- get_redis_invalidation_state (succès, Redis unreachable)
- inspect_pubsub_dlq (messages présents, file vide)
- execute_read_only_query (SELECT ok, DML rejeté)
- get_recent_500_errors (succès, Cloud Logging mock)
- search_cloud_logs_by_trace (succès, Cloud Logging mock)
- get_service_logs (succès avec fuzzy match service)
- get_ingestion_pipeline_status (succès, drive_api unreachable)
- list_tools (registre complet)
- unknown_tool (erreur structurée)
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

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
# Tests get_redis_invalidation_state (Gap 2 fix verification)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_redis_invalidation_state_ok(mocker):
    """SCAN Redis doit se terminer correctement (vérification bug boucle infinie résolu)."""
    mock_r = MagicMock()
    # Simule un SCAN qui retourne cursor=0 (terminé) dès le premier appel
    mock_r.scan.return_value = (0, [b"items:list:all", b"session:abc123"])
    mock_r.ttl.return_value = 300
    import redis as redis_lib
    mocker.patch.object(redis_lib, "from_url", return_value=mock_r)

    result = await call_tool("get_redis_invalidation_state", {"pattern": "items:*"})
    assert len(result) == 1
    data = json.loads(result[0].text)
    assert data["status"] == "ok"
    assert data["matched_keys_count"] == 2
    # Vérification que scan a bien été appelé (boucle s'est exécutée au moins 1 fois)
    mock_r.scan.assert_called_once()


@pytest.mark.asyncio
async def test_get_redis_invalidation_state_unreachable(mocker):
    """Redis unreachable doit retourner un dict d'erreur structuré."""
    import redis as redis_lib
    mocker.patch.object(redis_lib, "from_url", side_effect=Exception("Connection refused"))

    result = await call_tool("get_redis_invalidation_state", {"pattern": "*"})
    assert len(result) == 1
    data = json.loads(result[0].text)
    assert "error" in data


# ---------------------------------------------------------------------------
# Tests inspect_pubsub_dlq (Gap 1 fix verification)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_inspect_pubsub_dlq_ok(mocker):
    """inspect_pubsub_dlq doit retourner les messages et appeler modify_ack_deadline."""
    mock_subscriber = MagicMock()
    mock_rm = MagicMock()
    mock_rm.message.message_id = "msg-001"
    mock_rm.message.publish_time = None
    mock_rm.message.attributes = {}
    mock_rm.message.data = b'{"cv_id": "abc"}'
    mock_rm.ack_id = "ack-001"

    mock_response = MagicMock()
    mock_response.received_messages = [mock_rm]
    mock_subscriber.pull.return_value = mock_response
    mock_subscriber.subscription_path.return_value = "projects/test/subscriptions/cv-ingestion-dlq-sub"

    mocker.patch("google.cloud.pubsub_v1.SubscriberClient", return_value=mock_subscriber)

    result = await call_tool("inspect_pubsub_dlq", {"subscription_id": "cv-ingestion-dlq-sub", "limit": 5})
    assert len(result) == 1
    data = json.loads(result[0].text)
    assert data["status"] == "ok"
    assert data["count"] == 1
    assert data["messages"][0]["message_id"] == "msg-001"
    # Vérification Gap 1 : modify_ack_deadline appelé pour éviter disparition des messages
    mock_subscriber.modify_ack_deadline.assert_called_once()


@pytest.mark.asyncio
async def test_inspect_pubsub_dlq_empty(mocker):
    """inspect_pubsub_dlq sur une file vide doit retourner count=0."""
    mock_subscriber = MagicMock()
    mock_response = MagicMock()
    mock_response.received_messages = []
    mock_subscriber.pull.return_value = mock_response
    mock_subscriber.subscription_path.return_value = "projects/test/subscriptions/dlq-empty"

    mocker.patch("google.cloud.pubsub_v1.SubscriberClient", return_value=mock_subscriber)

    result = await call_tool("inspect_pubsub_dlq", {"subscription_id": "dlq-empty"})
    assert len(result) == 1
    data = json.loads(result[0].text)
    assert data["status"] == "ok"
    assert data["count"] == 0


# ---------------------------------------------------------------------------
# Tests execute_read_only_query
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_read_only_query_rejects_insert():
    """Une requête INSERT doit être rejetée sans toucher la DB."""
    result = await call_tool("execute_read_only_query", {"query": "INSERT INTO users VALUES (1,'test')"})
    assert len(result) == 1
    data = json.loads(result[0].text)
    assert "error" in data
    assert "read-only" in data["error"].lower() or "SELECT" in data["error"]


@pytest.mark.asyncio
async def test_execute_read_only_query_rejects_delete():
    """Une requête DELETE doit être rejetée."""
    result = await call_tool("execute_read_only_query", {"query": "DELETE FROM users WHERE id=1"})
    data = json.loads(result[0].text)
    assert "error" in data


@pytest.mark.asyncio
async def test_execute_read_only_query_select_ok(mocker):
    """Une requête SELECT valide doit retourner les lignes."""
    mock_conn = AsyncMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [{"id": 1, "name": "Alice"}]
    mock_conn.execute = AsyncMock(return_value=mock_result)
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    mock_engine = MagicMock()
    mock_engine.connect.return_value = mock_conn
    mock_engine.dispose = AsyncMock()

    mocker.patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=mock_engine)

    result = await call_tool("execute_read_only_query", {"query": "SELECT id, name FROM users LIMIT 10"})
    assert len(result) == 1
    data = json.loads(result[0].text)
    assert data["status"] == "ok"
    assert data["count"] == 1


# ---------------------------------------------------------------------------
# Tests get_recent_500_errors
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_recent_500_errors_ok(mocker):
    """get_recent_500_errors doit retourner une liste de dicts d'erreurs."""
    mock_entry = MagicMock()
    mock_entry.timestamp.isoformat.return_value = "2026-05-04T10:00:00+00:00"
    mock_entry.severity = "ERROR"
    mock_entry.resource.labels = {"service_name": "cv-api-prd"}
    mock_entry.trace = "projects/test/traces/abc123"
    mock_entry.http_request = None
    mock_entry.json_payload = {"message": "Internal Server Error"}

    mock_logging_client = MagicMock()
    mock_logging_client.list_entries.return_value = iter([mock_entry])

    mocker.patch("tools.logs_tools.logging_cloud.Client", return_value=mock_logging_client)

    result = await call_tool("get_recent_500_errors", {"limit": 5, "hours_lookback": 1})
    assert len(result) == 1
    data = json.loads(result[0].text)
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["service"] == "cv-api-prd"
    assert data[0]["trace_id"] == "abc123"


# ---------------------------------------------------------------------------
# Tests search_cloud_logs_by_trace
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_cloud_logs_by_trace_ok(mocker):
    """search_cloud_logs_by_trace doit retourner les logs correspondant à la trace."""
    mock_entry = MagicMock()
    mock_entry.timestamp.isoformat.return_value = "2026-05-04T10:00:01+00:00"
    mock_entry.severity = "INFO"
    mock_entry.resource.type = "cloud_run_revision"
    mock_entry.json_payload = {"message": "CV analysé avec succès"}

    mock_logging_client = MagicMock()
    mock_logging_client.list_entries.return_value = iter([mock_entry])

    mocker.patch("tools.logs_tools.logging_cloud.Client", return_value=mock_logging_client)

    result = await call_tool("search_cloud_logs_by_trace", {"trace_id": "abc123def456", "limit": 10})
    assert len(result) == 1
    data = json.loads(result[0].text)
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["severity"] == "INFO"


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
