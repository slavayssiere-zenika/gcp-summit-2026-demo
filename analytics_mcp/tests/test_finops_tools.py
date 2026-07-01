from tools.finops_tools import handle_log_ai_consumption, handle_get_finops_report
import pytest
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock

from tools.finops_tools import (
    handle_detect_usage_anomalies,
    handle_get_aiops_dashboard_data,
    handle_get_usage_statistics,
)


@pytest.mark.asyncio
async def test_handle_detect_usage_anomalies():
    mock_client = MagicMock()
    mock_query_job = MagicMock()

    class MockRow:
        def __init__(self, email, total, count, start, end):
            self.user_email = email
            self.total_tokens = total
            self.request_count = count
            self.window_start = start
            self.window_end = end

    mock_query_job.result.return_value = [
        MockRow(
            "test@example.com", 60000, 10,
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 2, tzinfo=timezone.utc),
        )
    ]
    mock_client.query.return_value = mock_query_job

    args = {"threshold_tokens_per_hour": 50000, "hours_back": 1}
    result = await handle_detect_usage_anomalies(args, mock_client, "project.dataset.table")

    assert len(result) == 1
    assert result[0].type == "text"

    data = json.loads(result[0].text)
    assert data["anomaly_count"] == 1
    assert data["anomalies"][0]["user_email"] == "test@example.com"
    assert data["anomalies"][0]["threshold_exceeded_by"] == 10000


@pytest.mark.asyncio
async def test_handle_get_aiops_dashboard_data():
    mock_internal_func = AsyncMock()
    mock_internal_func.return_value = {"dashboard": "data"}

    result = await handle_get_aiops_dashboard_data(mock_internal_func)

    assert len(result) == 1
    assert result[0].type == "text"
    assert json.loads(result[0].text) == {"dashboard": "data"}
    mock_internal_func.assert_called_once()


@pytest.mark.asyncio
async def test_handle_log_ai_consumption_success():
    mock_client = MagicMock()
    mock_client.insert_rows_json.return_value = []

    args = {
        "user_email": "test@example.com",
        "action": "test_action",
        "model": "gemini-1.5",
        "input_tokens": 10,
        "output_tokens": 20
    }

    result = await handle_log_ai_consumption(args, mock_client, "project.dataset.table")

    assert len(result) == 1
    assert "successfully" in result[0].text
    mock_client.insert_rows_json.assert_called_once()


@pytest.mark.asyncio
async def test_handle_log_ai_consumption_error():
    mock_client = MagicMock()
    mock_client.insert_rows_json.return_value = [{"error": "something went wrong"}]

    args = {
        "user_email": "test@example.com",
        "action": "test_action",
        "model": "gemini-1.5",
        "input_tokens": 10,
        "output_tokens": 20
    }

    result = await handle_log_ai_consumption(args, mock_client, "project.dataset.table")

    assert len(result) == 1
    assert "Errors occurred" in result[0].text


@pytest.mark.asyncio
async def test_handle_get_finops_report():
    mock_client = MagicMock()
    mock_query_job = MagicMock()

    class MockRow(dict):
        def __init__(self, d):
            super().__init__(d)
            for k, v in d.items():
                setattr(self, k, v)

    mock_row_dict = {
        "period": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "user_email": "test@example.com",
        "action": "test",
        "total_input": 100,
        "total_output": 200,
        "estimated_cost_usd": 0.05
    }
    mock_query_job.result.return_value = [MockRow(mock_row_dict)]
    mock_client.query.return_value = mock_query_job

    args = {"period": "weekly", "user_email": "test@example.com"}
    result = await handle_get_finops_report(args, mock_client, "project", "dataset", "table")

    assert len(result) == 1
    data = json.loads(result[0].text)
    assert data[0]["user_email"] == "test@example.com"
    assert "2026-01-01" in data[0]["period"]


@pytest.mark.asyncio
async def test_handle_log_ai_consumption_null_email():
    """Test logging consumption with missing user_email."""
    arguments = {
        "user_email": None,
        "action": "test",
        "model": "test-model",
        "input_tokens": 10,
        "output_tokens": 10,
    }
    client = MagicMock()
    result = await handle_log_ai_consumption(arguments, client, "fake_table")
    assert "Error:" in result[0].text
    assert "user_email" in result[0].text
    client.insert_rows_json.assert_not_called()


# ---------------------------------------------------------------------------
# Tests handle_get_usage_statistics
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_get_usage_statistics_happy_path():
    """handle_get_usage_statistics retourne les métriques BigQuery pour une date donnée."""
    mock_client = MagicMock()

    class MockRow:
        unique_visitors = 42
        total_requests = 1500
        router_requests = 800
        agent_queries = 150
        blocked_scans = 10

    mock_query_job = MagicMock()
    mock_query_job.result.return_value = [MockRow()]
    mock_client.query.return_value = mock_query_job

    args = {"date": "2026-06-07"}
    result = await handle_get_usage_statistics(args, mock_client, "my-project", "finops_prd")

    assert len(result) == 1
    data = json.loads(result[0].text)
    assert data["date"] == "2026-06-07"
    assert data["unique_visitors"] == 42
    assert data["total_requests"] == 1500
    assert data["router_requests"] == 800
    assert data["agent_queries"] == 150
    assert data["blocked_scans"] == 10
    assert data["status"] == "success"

    # Vérifie que la query utilise bien le _TABLE_SUFFIX avec le format YYYYMMDD
    call_args = mock_client.query.call_args
    query_str = call_args[0][0]
    assert "_TABLE_SUFFIX" in query_str, "La query doit utiliser _TABLE_SUFFIX (tables shardées par jour)"
    assert "run_googleapis_com_requests_*" in query_str, "La query doit cibler le wildcard de tables shardées"
    # Vérifie le paramètre : table_suffix = "20260607"
    job_config = call_args[1].get("job_config") or call_args[0][1]
    params = {p.name: p.value for p in job_config.query_parameters}
    assert params.get("table_suffix") == "20260607", (
        f"Le suffixe doit être '20260607', got: {params.get('table_suffix')}"
    )


@pytest.mark.asyncio
async def test_handle_get_usage_statistics_no_data():
    """handle_get_usage_statistics retourne status no_data si la requête retourne 0 lignes."""
    mock_client = MagicMock()
    mock_query_job = MagicMock()
    mock_query_job.result.return_value = []  # Aucune ligne
    mock_client.query.return_value = mock_query_job

    args = {"date": "2026-06-07"}
    result = await handle_get_usage_statistics(args, mock_client, "my-project", "finops_prd")

    assert len(result) == 1
    data = json.loads(result[0].text)
    assert data["status"] == "no_data"
    assert data["unique_visitors"] == 0
    assert data["total_requests"] == 0


@pytest.mark.asyncio
async def test_handle_get_usage_statistics_fallback_on_exception():
    """handle_get_usage_statistics retourne status fallback_no_table si BigQuery lève une exception."""
    mock_client = MagicMock()
    mock_client.query.side_effect = Exception("Table not found in location US")

    args = {"date": "2026-06-07"}
    result = await handle_get_usage_statistics(args, mock_client, "my-project", "finops_prd")

    assert len(result) == 1
    data = json.loads(result[0].text)
    assert data["status"] == "fallback_no_table"
    assert data["unique_visitors"] == "[N/D]"
    assert data["total_requests"] == "[N/D]"
    assert "Table not found" in data.get("error_detail", "")


@pytest.mark.asyncio
async def test_handle_get_usage_statistics_default_date_yesterday():
    """handle_get_usage_statistics utilise la date de la veille si l'argument date est absent."""
    mock_client = MagicMock()
    mock_query_job = MagicMock()
    mock_query_job.result.return_value = []
    mock_client.query.return_value = mock_query_job

    from datetime import datetime, timedelta, timezone
    expected_date = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

    args = {}  # Pas de date fournie
    result = await handle_get_usage_statistics(args, mock_client, "my-project", "finops_prd")

    assert len(result) == 1
    data = json.loads(result[0].text)
    assert data["date"] == expected_date, f"La date par défaut devrait être {expected_date}"


@pytest.mark.asyncio
async def test_handle_get_usage_statistics_client_none():
    """handle_get_usage_statistics retourne un fallback propre si le client BigQuery est None."""
    args = {"date": "2026-06-07"}
    result = await handle_get_usage_statistics(args, None, "my-project", "finops_prd")

    assert len(result) == 1
    data = json.loads(result[0].text)
    assert data["status"] == "fallback_no_table"
    assert data["unique_visitors"] == "[N/D]"
