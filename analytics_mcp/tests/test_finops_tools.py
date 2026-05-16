from tools.finops_tools import handle_log_ai_consumption, handle_get_finops_report
import pytest
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock

from tools.finops_tools import handle_detect_usage_anomalies, handle_get_aiops_dashboard_data


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
        MockRow("test@example.com", 60000, 10, datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 1, 2, tzinfo=timezone.utc))
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
