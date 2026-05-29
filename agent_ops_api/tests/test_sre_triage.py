import os
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

# Mock the environment to avoid real calls during imports
os.environ["SECRET_KEY"] = "testsecret_must_be_32_characters_long_for_sha256"
os.environ["PUBSUB_INVOKER_SA_EMAIL"] = ""

from main import app

client = TestClient(app)


@patch("main.run_sre_triage")
def test_sre_triage_success(mock_run_sre_triage):
    # Mock return value of run_sre_triage
    mock_run_sre_triage.return_value = AsyncMock()
    mock_run_sre_triage.return_value.triggered_at = "2026-05-29T10:00:00Z"
    mock_run_sre_triage.return_value.services_inspected = None
    mock_run_sre_triage.return_value.hours = 1
    mock_run_sre_triage.return_value.threshold_5xx = 5
    mock_run_sre_triage.return_value.response = "Diagnose result"
    mock_run_sre_triage.return_value.steps = []
    mock_run_sre_triage.return_value.thoughts = ""
    mock_run_sre_triage.return_value.usage = {}
    mock_run_sre_triage.return_value.source = "ops_agent"
    mock_run_sre_triage.return_value.severity = "OK"

    # Send a request with a fake Bearer token
    response = client.post(
        "/tasks/sre-triage",
        json={"hours": 2, "threshold_5xx": 10},
        headers={"Authorization": "Bearer fake-token"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["response"] == "Diagnose result"
    assert payload["hours"] == 1
