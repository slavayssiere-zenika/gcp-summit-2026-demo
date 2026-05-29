import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tools.gcp_monitoring_tools import (
    list_alert_policies_internal,
    list_alerts_internal,
    list_timeseries_internal
)


@pytest.mark.asyncio
@patch("tools.gcp_monitoring_tools._get_auth_headers", new_callable=AsyncMock)
@patch("httpx.AsyncClient.get", new_callable=AsyncMock)
async def test_list_alert_policies_internal(mock_get, mock_auth):
    mock_auth.return_value = {"Authorization": "Bearer token", "Content-Type": "application/json"}

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "alertPolicies": [{"name": "projects/p/alertPolicies/1", "displayName": "Policy 1"}]
    }
    mock_get.return_value = mock_response

    result = await list_alert_policies_internal("projects/p")
    assert isinstance(result, dict)
    assert "alertPolicies" in result
    assert len(result["alertPolicies"]) == 1
    assert result["alertPolicies"][0]["displayName"] == "Policy 1"


@pytest.mark.asyncio
@patch("tools.gcp_monitoring_tools._get_auth_headers", new_callable=AsyncMock)
@patch("tools.gcp_monitoring_tools.list_alert_policies_internal", new_callable=AsyncMock)
@patch("tools.pipeline_tools.check_all_components_health_internal", new_callable=AsyncMock)
@patch("tools.logs_tools.get_recent_500_errors_internal", new_callable=AsyncMock)
async def test_list_alerts_internal(mock_errors, mock_health, mock_policies, mock_auth):
    mock_auth.return_value = {"Authorization": "Bearer token", "Content-Type": "application/json"}

    mock_policies.return_value = {
        "alertPolicies": [
            {
                "name": "projects/p/alertPolicies/1",
                "displayName": "[SLO-FAST-BURN] Agent HR API — Disponibilité — dev",
                "conditions": [
                    {
                        "conditionThreshold": {
                            "filter": 'select_slo_burn_rate("projects/p/services/agent-hr-api-service-dev")',
                            "thresholdValue": 14.4
                        }
                    }
                ]
            }
        ]
    }

    mock_health.return_value = {
        "composants": {
            "agent-hr-api-prd": "unreachable"
        }
    }

    mock_errors.return_value = []

    result = await list_alerts_internal("projects/p")
    assert isinstance(result, dict)
    assert "alerts" in result
    assert len(result["alerts"]) == 1
    assert result["alerts"][0]["state"] == "OPEN"
    assert "agent hr" in result["alerts"][0]["policy_display_name"].lower()


@pytest.mark.asyncio
@patch("tools.gcp_monitoring_tools._get_auth_headers", new_callable=AsyncMock)
@patch("httpx.AsyncClient.get", new_callable=AsyncMock)
async def test_list_timeseries_internal(mock_get, mock_auth):
    mock_auth.return_value = {"Authorization": "Bearer token", "Content-Type": "application/json"}

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"timeSeries": [{"metric": {"type": "run.googleapis.com/request_count"}}]}
    mock_get.return_value = mock_response

    result = await list_timeseries_internal(
        name="projects/p",
        filter_str="metric.type = \"run.googleapis.com/request_count\"",
        interval={"startTime": "2026-05-29T10:00:00Z", "endTime": "2026-05-29T11:00:00Z"},
        view="FULL",
        aggregation={"alignmentPeriod": "60s", "perSeriesAligner": "ALIGN_SUM"}
    )

    assert isinstance(result, dict)
    assert "timeSeries" in result
    assert len(result["timeSeries"]) == 1
