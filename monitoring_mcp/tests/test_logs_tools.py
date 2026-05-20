import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools.logs_tools import (
    _sanitize_log_filter,
    get_service_logs_internal,
    search_cloud_logs_by_trace_internal,
    get_recent_500_errors_internal
)


@pytest.fixture
def mock_entry():
    class MockEntry:
        def __init__(self, ts, severity, payload_msg, res_labels=None, trace_id=None, req_status=None):
            self.timestamp = ts
            self.severity = severity
            self.json_payload = {"message": payload_msg}
            self.payload = payload_msg

            self.resource = MagicMock()
            self.resource.labels = res_labels or {"service_name": "test-service"}
            self.resource.type = "cloud_run_revision"

            self.trace = trace_id

            if req_status:
                self.http_request = {"requestMethod": "GET", "requestUrl": "http://test", "status": req_status}
            else:
                self.http_request = None

    return MockEntry


@pytest.mark.asyncio
@patch('google.cloud.logging_v2.Client')
@patch('tools.logs_tools.list_gcp_services_internal', new_callable=AsyncMock)
async def test_get_service_logs_internal(mock_list_services, mock_client_class, mock_entry):
    mock_list_services.return_value = [{"name": "test-service-dev"}]
    mock_client = mock_client_class.return_value

    ts = datetime.datetime.now(datetime.timezone.utc)
    mock_client.list_entries.return_value = [
        mock_entry(ts, "ERROR", "Something failed")
    ]

    result = await get_service_logs_internal("test-service", limit=10, hours_lookback=1, severity="ERROR")
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["severity"] == "ERROR"
    assert result[0]["cloud_run_service"] == "test-service-dev"


@pytest.mark.asyncio
@patch('google.cloud.logging_v2.Client')
async def test_search_cloud_logs_by_trace_internal(mock_client_class, mock_entry):
    mock_client = mock_client_class.return_value

    ts = datetime.datetime.now(datetime.timezone.utc)
    mock_client.list_entries.return_value = [
        mock_entry(ts, "INFO", "Trace log")
    ]

    result = await search_cloud_logs_by_trace_internal("trace-12345")
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["message"] == "Trace log"


@pytest.mark.asyncio
@patch('google.cloud.logging_v2.Client')
async def test_get_recent_500_errors_internal(mock_client_class, mock_entry):
    mock_client = mock_client_class.return_value

    ts = datetime.datetime.now(datetime.timezone.utc)
    mock_client.list_entries.return_value = [
        mock_entry(ts, "ERROR", "Internal Server Error", req_status=500, trace_id="projects/p/traces/123")
    ]

    result = await get_recent_500_errors_internal(limit=5)
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["request"]["status"] == 500
    assert result[0]["trace_id"] == "123"


def test_sanitize_log_filter():
    assert _sanitize_log_filter("valid-service-123") == "valid-service-123"
    assert _sanitize_log_filter("injected\" OR \"\"=\"") == "injected OR ="
    assert _sanitize_log_filter("path\\to\\trace") == "pathtotrace"
    assert _sanitize_log_filter("null\x00byte") == "nullbyte"
