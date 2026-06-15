import os
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

# Mock the environment to avoid real calls during imports
os.environ["SECRET_KEY"] = "testsecret_must_be_32_characters_long_for_sha256"


@pytest.fixture(autouse=True)
def mock_oidc_verification():
    with patch("shared.auth.jwt.google_id_token.verify_oauth2_token") as mock_verify:
        mock_verify.return_value = {"email": "allowed@test.com"}
        yield mock_verify


from main import app  # noqa: E402

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


def test_classify_report_ok():
    from sre_triage import classify_report
    report = (
        "# Rapport Triage SRE\n\n"
        "## 📋 Statut des Services\n"
        "| Service | Statut | Détails |\n"
        "|---|---|---|\n"
        "| users_api | ✅ OK | Aucune erreur |\n"
        "| items_api | ✅ OK | Aucune erreur |\n\n"
        "## Incidents Critiques\n"
        "Aucun incident critique détecté.\n\n"
        "## Alertes Data Quality\n"
        "Aucune dégradation de la qualité des données.\n\n"
        "## Alertes FinOps\n"
        "Consommation IA dans les normes.\n\n"
        "## Tendances historiques (Ignoré par le trieur)\n"
        "- 2026-06-07 : 🔴 users_api en panne (résolu)\n"
    )
    assert classify_report(report) == "OK"


def test_classify_report_critical_service():
    from sre_triage import classify_report
    report = (
        "# Rapport Triage SRE\n\n"
        "## 📋 Statut des Services\n"
        "| Service | Statut | Détails |\n"
        "|---|---|---|\n"
        "| users_api | 🔴 CRITICAL | 5xx threshold exceeded |\n"
        "| items_api | ✅ OK | Aucune erreur |\n"
    )
    assert classify_report(report) == "CRITICAL"


def test_classify_report_critical_section():
    from sre_triage import classify_report
    report = (
        "# Rapport Triage SRE\n\n"
        "## 📋 Statut des Services\n"
        "| Service | Statut | Détails |\n"
        "|---|---|---|\n"
        "| users_api | ✅ OK | Aucune erreur |\n\n"
        "## Incidents Critiques\n"
        "- 🔴 Erreur critique détectée sur alloydb.\n"
    )
    assert classify_report(report) == "CRITICAL"


def test_classify_report_warning_service():
    from sre_triage import classify_report
    report = (
        "# Rapport Triage SRE\n\n"
        "## 📋 Statut des Services\n"
        "| Service | Statut | Détails |\n"
        "|---|---|---|\n"
        "| users_api | ⚠️ WARNING | High latency |\n"
    )
    assert classify_report(report) == "WARNING"


def test_classify_report_warning_data_quality():
    from sre_triage import classify_report
    report = (
        "# Rapport Triage SRE\n\n"
        "## 📋 Statut des Services\n"
        "| Service | Statut | Détails |\n"
        "|---|---|---|\n"
        "| users_api | ✅ OK | Aucune erreur |\n\n"
        "## Alertes Data Quality\n"
        "- ⚠️ 15 CVs ont un score de fiabilité faible.\n"
    )
    assert classify_report(report) == "WARNING"


def test_classify_report_warning_finops():
    from sre_triage import classify_report
    report = (
        "# Rapport Triage SRE\n\n"
        "## 📋 Statut des Services\n"
        "| Service | Statut | Détails |\n"
        "|---|---|---|\n"
        "| users_api | ✅ OK | Aucune erreur |\n\n"
        "## Alertes FinOps\n"
        "- ⚠️ Augmentation de 50% de la consommation Gemini.\n"
    )
    assert classify_report(report) == "WARNING"


@patch("sre_triage.run_daily_report")
def test_daily_report_endpoint(mock_run_daily_report):
    mock_run_daily_report.return_value = "Daily Report Content"

    # Send a request to daily-report
    response = client.post(
        "/tasks/daily-report",
        headers={"Authorization": "Bearer fake-token"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["report"] == "Daily Report Content"


def test_daily_report_endpoint_missing_auth():
    """Le endpoint /tasks/daily-report doit retourner 401 sans token Bearer."""
    response = client.post("/tasks/daily-report")
    assert response.status_code == 401


@patch("sre_triage.run_daily_report")
def test_daily_report_endpoint_agent_failure(mock_run_daily_report):
    """Le endpoint /tasks/daily-report doit retourner 500 si run_daily_report lève une exception."""
    mock_run_daily_report.side_effect = Exception("LLM timeout")

    response = client.post(
        "/tasks/daily-report",
        headers={"Authorization": "Bearer fake-token"},
    )
    assert response.status_code == 500
    payload = response.json()
    assert "detail" in payload
    assert "LLM timeout" in payload["detail"]
