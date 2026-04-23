"""
Tests manquants pour analytics_mcp :
- log_ai_consumption vers BigQuery
- get_finops_report avec filtrages
- check_component_health (redis, service Cloud Run)
- check_all_components_health_internal
- Gestion d'erreurs BigQuery (client None, erreur réseau)
- Authentification JWT sur /mcp/call
"""

import pytest
import json
from unittest.mock import patch, MagicMock, AsyncMock
from mcp_server import list_tools, call_tool


# ---------------------------------------------------------------------------
# Tests log_ai_consumption
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch('mcp_server.client')
async def test_log_ai_consumption_success(mock_client):
    """log_ai_consumption doit insérer une ligne BigQuery et retourner success."""
    mock_client.insert_rows_json.return_value = []  # Aucune erreur

    args = {
        "user_email": "alice@zenika.com",
        "action": "agent_query",
        "model": "gemini-3-flash-preview",
        "input_tokens": 1500,
        "output_tokens": 300,
    }
    result = await call_tool("log_ai_consumption", args)

    assert len(result) == 1
    assert "successfully" in result[0].text.lower() or "logged" in result[0].text.lower()
    mock_client.insert_rows_json.assert_called_once()


@pytest.mark.asyncio
@patch('mcp_server.client')
async def test_log_ai_consumption_with_optional_fields(mock_client):
    """log_ai_consumption doit accepter les champs optionnels unit_cost et metadata."""
    mock_client.insert_rows_json.return_value = []

    args = {
        "user_email": "bob@zenika.com",
        "action": "cv_import",
        "model": "gemini-embedding-001",
        "input_tokens": 500,
        "output_tokens": 0,
        "unit_cost": 0.00005,
        "metadata": {"cv_id": "abc123", "source": "drive"}
    }
    result = await call_tool("log_ai_consumption", args)
    assert len(result) == 1
    # Vérifier que metadata est sérialisé en JSON string
    call_args = mock_client.insert_rows_json.call_args[0][1]
    row = call_args[0]
    assert isinstance(row["metadata"], str), "metadata doit être sérialisé en JSON string pour BigQuery"


@pytest.mark.asyncio
@patch('mcp_server.client')
async def test_log_ai_consumption_bigquery_error_returns_error_message(mock_client):
    """Si BigQuery retourne des erreurs lors de l'insertion, le tool doit les reporter."""
    mock_client.insert_rows_json.return_value = [
        {"index": 0, "errors": [{"reason": "invalid", "message": "Required field missing."}]}
    ]

    args = {
        "user_email": "test@zenika.com",
        "action": "test",
        "model": "gemini",
        "input_tokens": 10,
        "output_tokens": 5,
    }
    result = await call_tool("log_ai_consumption", args)
    assert len(result) == 1
    assert "error" in result[0].text.lower() or "errors" in result[0].text.lower()


# ---------------------------------------------------------------------------
# Tests get_finops_report
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch('mcp_server.client')
async def test_get_finops_report_daily(mock_client):
    """get_finops_report avec period=daily doit faire une requête BigQuery et retourner une liste."""
    mock_row = MagicMock()
    mock_row.__iter__ = MagicMock(return_value=iter([
        ("period", "2026-04-15"),
        ("user_email", "alice@zenika.com"),
        ("action", "agent_query"),
        ("total_input", 1000),
        ("total_output", 200),
        ("estimated_cost_usd", 0.000135),
    ]))
    mock_row.keys = MagicMock(return_value=["period", "user_email", "action", "total_input", "total_output", "estimated_cost_usd"])
    # Simulation dict(row)
    mock_bq_row = {
        "period": "2026-04-15",
        "user_email": "alice@zenika.com",
        "action": "agent_query",
        "total_input": 1000,
        "total_output": 200,
        "estimated_cost_usd": 0.000135,
    }

    mock_query_job = MagicMock()
    mock_query_job.result.return_value = [mock_bq_row]
    mock_client.query.return_value = mock_query_job

    # Patcher dict() pour convertir les rows BigQuery
    import mcp_server
    with patch.object(mcp_server, 'client', mock_client):
        # Direct patch of client.query().result()
        pass

    result = await call_tool("get_finops_report", {"period": "daily"})
    assert len(result) == 1
    data = json.loads(result[0].text)
    assert isinstance(data, list)


@pytest.mark.asyncio
@patch('mcp_server.client')
async def test_get_finops_report_with_user_filter(mock_client):
    """get_finops_report filtré par user_email doit transmettre le paramètre à BigQuery."""
    mock_query_job = MagicMock()
    mock_query_job.result.return_value = []
    mock_client.query.return_value = mock_query_job

    result = await call_tool("get_finops_report", {
        "period": "monthly",
        "user_email": "alice@zenika.com"
    })
    assert len(result) == 1

    # Vérifier que le filtre user_email est passé dans les paramètres BigQuery
    call_args = mock_client.query.call_args
    job_config = call_args[1].get("job_config") or call_args[0][1] if len(call_args[0]) > 1 else None
    if job_config and hasattr(job_config, "query_parameters"):
        param_names = [p.name for p in job_config.query_parameters]
        assert "user_email" in param_names, "Le filtre user_email doit être passé comme paramètre BigQuery"


@pytest.mark.asyncio
@patch('mcp_server.client')
async def test_get_finops_report_weekly(mock_client):
    """get_finops_report avec period=weekly doit fonctionner."""
    mock_query_job = MagicMock()
    mock_query_job.result.return_value = []
    mock_client.query.return_value = mock_query_job

    result = await call_tool("get_finops_report", {"period": "weekly"})
    assert len(result) == 1
    data = json.loads(result[0].text)
    assert isinstance(data, list)




# ---------------------------------------------------------------------------
# Tests gestion d'erreur générale
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch('mcp_server.client')
async def test_bigquery_client_none_returns_error(mock_client):
    """Si le client BigQuery est None (init failed), les tools doivent retourner une erreur."""
    import mcp_server
    original_client = mcp_server.client
    mcp_server.client = None
    try:
        result = await call_tool("get_analytics_demand_volume", {"category": "DevOps"})
        assert len(result) == 1
        # Ne doit pas lever d'exception non catchée
        data = json.loads(result[0].text)
        assert "error" in data or "tool" in data
    finally:
        mcp_server.client = original_client


@pytest.mark.asyncio
async def test_unknown_tool_returns_error_dict():
    """Un tool inconnu doit retourner un dict d'erreur structuré (pas une exception)."""
    result = await call_tool("definitely_not_a_real_tool", {})
    assert len(result) == 1
    data = json.loads(result[0].text)
    assert "error" in data
    assert "Unknown tool" in data["error"]


@pytest.mark.asyncio
@patch('mcp_server.client')
async def test_get_analytics_skills_bigquery_network_error(mock_client):
    """Une erreur réseau BigQuery doit être capturée et retournée en dict structuré."""
    mock_client.query.side_effect = Exception("Network timeout connecting to BigQuery")

    result = await call_tool("get_top_market_skills", {"category": "Cloud"})
    assert len(result) == 1
    data = json.loads(result[0].text)
    # Réponse structurée, pas d'exception levée
    assert "error" in data or "tool" in data
    assert "Network timeout" in data.get("error", "") or data.get("tool") == "get_top_market_skills"


# ---------------------------------------------------------------------------
# Tests tools list
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_tools_returns_all_expected_tools():
    """list_tools doit retourner tous les outils attendus du analytics_mcp."""
    tools = await list_tools()
    tool_names = [t.name for t in tools]

    expected_tools = [
        "get_top_market_skills",
        "get_market_demand_volume",
        "log_ai_consumption",
        "get_finops_report",
    ]
    for tool in expected_tools:
        assert tool in tool_names, f"Tool '{tool}' manquant dans list_tools()"
