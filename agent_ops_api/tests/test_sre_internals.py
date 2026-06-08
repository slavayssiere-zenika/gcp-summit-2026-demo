"""
test_sre_internals.py — Tests unitaires pour les fonctions internes de sre_triage.py.

Couvre :
  - _parse_report_metrics   : extraction des métriques BigQuery depuis un rapport Markdown
  - _get_webhook_url        : résolution sécurisée du webhook Google Chat (env var / Secret Manager)
  - _send_chat_notification : envoi conditionnel (OK silencieux, troncature, webhook error)
  - _send_daily_report_chat_notification : envoi rapport quotidien (toujours envoyé, troncature)
"""

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("SECRET_KEY", "testsecret_must_be_32_characters_long_for_sha256")
os.environ.setdefault("PUBSUB_INVOKER_SA_EMAIL", "")

from sre_triage import (  # noqa: E402
    SreTriageReport,
    _CHAT_REPORT_MAX_CHARS,
    _get_webhook_url,
    _parse_report_metrics,
    _send_chat_notification,
    _send_daily_report_chat_notification,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_report(**kwargs) -> SreTriageReport:
    """Construit un SreTriageReport minimal pour les tests."""
    defaults = dict(
        triggered_at="2026-06-08T08:00:00+00:00",
        hours=2,
        threshold_5xx=5,
        response="",
        severity="OK",
        source="ops_agent",
        usage={"total_input_tokens": 100, "total_output_tokens": 50, "estimated_cost_usd": 0.001},
    )
    defaults.update(kwargs)
    return SreTriageReport(**defaults)


_SAMPLE_REPORT = """\
# 🏥 Rapport SRE Automatique — 2026-06-08

## Résumé Exécutif
Plateforme nominale. 2 services sains, 1 dégradé, 1 critique.

## État des Services
| Service | Statut | Erreurs 5xx | Latence P99 |
|---------|--------|-------------|-------------|
| users_api | ✅ OK | 0 | 120 ms |
| items_api | ✅ OK | 0 | 80 ms |
| cv_api | ⚠️ WARNING | 3 | 2100 ms |
| agent_router_api | 🔴 CRITICAL | 12 | 5400 ms |

## Incidents Critiques
### agent_router_api
- Symptôme : 12 erreurs 5xx détectées
- Playbook appliqué : SRE-API-002

## Alertes Data Quality
- Type : ValidationError
- Occurrence : 7

## Alertes FinOps
✅ Consommation IA dans les normes.
"""


# ---------------------------------------------------------------------------
# Tests _parse_report_metrics
# ---------------------------------------------------------------------------

class TestParseReportMetrics:
    """Valide l'extraction structurée des métriques depuis un rapport Markdown."""

    def test_services_classified_correctly(self):
        """Les services doivent être classifiés dans les bonnes listes."""
        report = _make_report(response=_SAMPLE_REPORT, severity="CRITICAL", source="ops_agent_prd")
        metrics = _parse_report_metrics(report)

        critical = json.loads(metrics["services_critical"])
        warning = json.loads(metrics["services_warning"])
        ok = json.loads(metrics["services_ok"])

        assert "agent_router_api" in critical
        assert "cv_api" in warning
        assert "users_api" in ok
        assert "items_api" in ok

    def test_total_5xx_summed_from_table(self):
        """Le total 5xx doit additionner les valeurs numériques de la 3ème colonne."""
        report = _make_report(response=_SAMPLE_REPORT, severity="CRITICAL")
        metrics = _parse_report_metrics(report)
        # cv_api: 3, agent_router_api: 12 → 15
        assert metrics["total_5xx"] == 15

    def test_dq_errors_extracted_from_section(self):
        """Le compte dq_errors doit être extrait depuis la section Alertes Data Quality."""
        report = _make_report(response=_SAMPLE_REPORT, severity="WARNING")
        metrics = _parse_report_metrics(report)
        assert metrics["dq_errors_count"] == 7

    def test_playbook_used_detected(self):
        """playbook_used doit être True si le rapport contient une référence SRE-XXX."""
        report = _make_report(response=_SAMPLE_REPORT, severity="CRITICAL")
        metrics = _parse_report_metrics(report)
        assert metrics["playbook_used"] is True

    def test_playbook_not_used_when_missing(self):
        """playbook_used doit être False si le rapport ne contient aucune référence SRE-."""
        report = _make_report(response="Rapport sans référence playbook.", severity="OK")
        metrics = _parse_report_metrics(report)
        assert metrics["playbook_used"] is False

    def test_playbook_not_used_when_unavailable_marker(self):
        """playbook_used doit être False si le marker [Playbook indisponible] est présent."""
        report = _make_report(
            response="[Playbook indisponible] SRE- référence présente mais indisponible.",
            severity="OK",
        )
        metrics = _parse_report_metrics(report)
        assert metrics["playbook_used"] is False

    def test_followup_scheduled_only_for_critical(self):
        """followup_scheduled doit être True uniquement si severity==CRITICAL."""
        report_crit = _make_report(response=_SAMPLE_REPORT, severity="CRITICAL")
        report_ok = _make_report(response=_SAMPLE_REPORT, severity="OK")
        assert _parse_report_metrics(report_crit)["followup_scheduled"] is True
        assert _parse_report_metrics(report_ok)["followup_scheduled"] is False

    def test_env_prd_detected_from_source(self):
        """env doit être 'prd' si 'prd' est dans le champ source."""
        report = _make_report(response="", severity="OK", source="ops_agent_prd")
        metrics = _parse_report_metrics(report)
        assert metrics["env"] == "prd"

    def test_env_dev_when_source_has_no_prd(self):
        """env doit être 'dev' si 'prd' n'est pas dans source."""
        report = _make_report(response="", severity="OK", source="ops_agent")
        metrics = _parse_report_metrics(report)
        assert metrics["env"] == "dev"

    def test_report_excerpt_extracted(self):
        """report_excerpt doit contenir le texte après '## Résumé Exécutif'."""
        report = _make_report(response=_SAMPLE_REPORT, severity="OK")
        metrics = _parse_report_metrics(report)
        assert "Plateforme nominale" in metrics["report_excerpt"]

    def test_empty_report_returns_zeros(self):
        """Un rapport vide doit retourner des listes vides et des compteurs à 0."""
        report = _make_report(response="", severity="OK")
        metrics = _parse_report_metrics(report)
        assert json.loads(metrics["services_critical"]) == []
        assert json.loads(metrics["services_warning"]) == []
        assert json.loads(metrics["services_ok"]) == []
        assert metrics["total_5xx"] == 0
        assert metrics["dq_errors_count"] == 0

    def test_header_rows_not_classified_as_services(self):
        """Les lignes d'en-tête du tableau (Service, ---) ne doivent pas être classifiées."""
        report = _make_report(
            response=(
                "| Service | Statut |\\n"
                "|---------|--------|\\n"
                "| users_api | ✅ OK |\\n"
            ),
            severity="OK",
        )
        metrics = _parse_report_metrics(report)
        ok = json.loads(metrics["services_ok"])
        assert "Service" not in ok
        assert "---" not in ok

    def test_tokens_and_cost_extracted_from_usage(self):
        """tokens_in, tokens_out et cost_usd doivent venir du champ usage du rapport."""
        report = _make_report(
            response="",
            severity="OK",
            usage={"total_input_tokens": 1234, "total_output_tokens": 567, "estimated_cost_usd": 0.0042},
        )
        metrics = _parse_report_metrics(report)
        assert metrics["tokens_in"] == 1234
        assert metrics["tokens_out"] == 567
        assert metrics["cost_usd"] == pytest.approx(0.0042)

    def test_multiple_dq_occurrences_summed(self):
        """Plusieurs occurrences de 'Occurrence : N' dans la section DQ doivent être additionnées."""
        text = (
            "## Alertes Data Quality\n"
            "- Occurrence : 3\n"
            "- Occurrence : 5\n"
            "## Alertes FinOps\n"
        )
        report = _make_report(response=text, severity="WARNING")
        metrics = _parse_report_metrics(report)
        assert metrics["dq_errors_count"] == 8


# ---------------------------------------------------------------------------
# Tests _get_webhook_url
# ---------------------------------------------------------------------------

class TestGetWebhookUrl:
    """Valide la résolution du webhook Google Chat."""

    def test_returns_direct_env_var(self, monkeypatch):
        """Doit retourner directement GOOGLE_CHAT_WEBHOOK_URL si présente."""
        monkeypatch.setenv("GOOGLE_CHAT_WEBHOOK_URL", "https://chat.googleapis.com/v1/spaces/test")
        monkeypatch.delenv("GOOGLE_CHAT_WEBHOOK_SECRET_NAME", raising=False)

        url = _get_webhook_url()
        assert url == "https://chat.googleapis.com/v1/spaces/test"

    def test_returns_empty_when_no_env_and_no_secret(self, monkeypatch):
        """Doit retourner '' si ni l'env var ni le secret name ne sont définis."""
        monkeypatch.delenv("GOOGLE_CHAT_WEBHOOK_URL", raising=False)
        monkeypatch.delenv("GOOGLE_CHAT_WEBHOOK_SECRET_NAME", raising=False)
        monkeypatch.delenv("GCP_PROJECT_ID", raising=False)

        url = _get_webhook_url()
        assert url == ""

    def test_returns_empty_when_secret_name_but_no_project(self, monkeypatch):
        """Doit retourner '' si le secret name est défini mais GCP_PROJECT_ID est absent."""
        monkeypatch.delenv("GOOGLE_CHAT_WEBHOOK_URL", raising=False)
        monkeypatch.setenv("GOOGLE_CHAT_WEBHOOK_SECRET_NAME", "my-secret")
        monkeypatch.delenv("GCP_PROJECT_ID", raising=False)

        url = _get_webhook_url()
        assert url == ""

    def test_reads_from_secret_manager(self, monkeypatch):
        """Doit interroger Secret Manager si l'env var directe est absente."""
        monkeypatch.delenv("GOOGLE_CHAT_WEBHOOK_URL", raising=False)
        monkeypatch.setenv("GOOGLE_CHAT_WEBHOOK_SECRET_NAME", "chat-webhook-secret")
        monkeypatch.setenv("GCP_PROJECT_ID", "my-project")

        mock_response = MagicMock()
        mock_response.payload.data = b"https://chat.googleapis.com/v1/spaces/secret"
        mock_client = MagicMock()
        mock_client.access_secret_version.return_value = mock_response
        mock_sm_class = MagicMock(return_value=mock_client)

        with patch.dict("sys.modules", {"google.cloud.secretmanager": MagicMock(
            SecretManagerServiceClient=mock_sm_class
        )}):
            url = _get_webhook_url()

        assert url == "https://chat.googleapis.com/v1/spaces/secret"

    def test_returns_empty_when_secret_contains_placeholder(self, monkeypatch):
        """Doit retourner '' si le secret contient le marker PLACEHOLDER."""
        monkeypatch.delenv("GOOGLE_CHAT_WEBHOOK_URL", raising=False)
        monkeypatch.setenv("GOOGLE_CHAT_WEBHOOK_SECRET_NAME", "chat-secret")
        monkeypatch.setenv("GCP_PROJECT_ID", "my-project")

        mock_response = MagicMock()
        mock_response.payload.data = b"PLACEHOLDER_URL"
        mock_client = MagicMock()
        mock_client.access_secret_version.return_value = mock_response
        mock_sm_class = MagicMock(return_value=mock_client)

        with patch.dict("sys.modules", {"google.cloud.secretmanager": MagicMock(
            SecretManagerServiceClient=mock_sm_class
        )}):
            url = _get_webhook_url()

        assert url == ""

    def test_returns_empty_on_secret_manager_exception(self, monkeypatch):
        """Doit retourner '' (non-bloquant) si Secret Manager lève une exception."""
        monkeypatch.delenv("GOOGLE_CHAT_WEBHOOK_URL", raising=False)
        monkeypatch.setenv("GOOGLE_CHAT_WEBHOOK_SECRET_NAME", "chat-secret")
        monkeypatch.setenv("GCP_PROJECT_ID", "my-project")

        mock_client = MagicMock()
        mock_client.access_secret_version.side_effect = Exception("Permission denied")
        mock_sm_class = MagicMock(return_value=mock_client)

        with patch.dict("sys.modules", {"google.cloud.secretmanager": MagicMock(
            SecretManagerServiceClient=mock_sm_class
        )}):
            url = _get_webhook_url()

        assert url == ""


# ---------------------------------------------------------------------------
# Tests _send_chat_notification
# ---------------------------------------------------------------------------

class TestSendChatNotification:
    """Valide l'envoi conditionnel des notifications SRE vers Google Chat."""

    @pytest.mark.asyncio
    async def test_ok_report_does_not_send(self, monkeypatch):
        """Un rapport OK ne doit pas envoyer de notification (anti-spam)."""
        monkeypatch.setenv("GOOGLE_CHAT_WEBHOOK_URL", "https://chat.example.com/hook")
        report = _make_report(response="Tout va bien.", severity="OK")

        with patch("httpx.AsyncClient") as mock_client_cls:
            await _send_chat_notification(report)
            mock_client_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_webhook_does_not_send(self, monkeypatch):
        """Sans webhook configuré, aucun appel HTTP ne doit être effectué."""
        monkeypatch.delenv("GOOGLE_CHAT_WEBHOOK_URL", raising=False)
        monkeypatch.delenv("GOOGLE_CHAT_WEBHOOK_SECRET_NAME", raising=False)
        monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
        report = _make_report(response="Incident critique.", severity="CRITICAL")

        with patch("httpx.AsyncClient") as mock_client_cls:
            await _send_chat_notification(report)
            mock_client_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_critical_report_sends_notification(self, monkeypatch):
        """Un rapport CRITICAL avec webhook doit déclencher un POST httpx."""
        monkeypatch.setenv("GOOGLE_CHAT_WEBHOOK_URL", "https://chat.example.com/hook")
        report = _make_report(response="Incident critique détecté.", severity="CRITICAL")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("sre_triage.httpx.AsyncClient", return_value=mock_cm):
            await _send_chat_notification(report)

        mock_http.post.assert_called_once()
        call_kwargs = mock_http.post.call_args
        payload = call_kwargs[1]["json"]
        assert "TRIAGE SRE CRITICAL" in payload["text"]

    @pytest.mark.asyncio
    async def test_warning_report_sends_notification(self, monkeypatch):
        """Un rapport WARNING doit également déclencher un POST httpx."""
        monkeypatch.setenv("GOOGLE_CHAT_WEBHOOK_URL", "https://chat.example.com/hook")
        report = _make_report(response="Latence élevée détectée.", severity="WARNING")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("sre_triage.httpx.AsyncClient", return_value=mock_cm):
            await _send_chat_notification(report)

        mock_http.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_long_report_truncated_in_notification(self, monkeypatch):
        """Un rapport dépassant _CHAT_REPORT_MAX_CHARS doit être tronqué dans le payload."""
        monkeypatch.setenv("GOOGLE_CHAT_WEBHOOK_URL", "https://chat.example.com/hook")
        long_response = "X" * (_CHAT_REPORT_MAX_CHARS + 500)
        report = _make_report(response=long_response, severity="CRITICAL")

        captured_payload = {}
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_http = AsyncMock()

        async def capture_post(url, **kwargs):
            captured_payload.update(kwargs.get("json", {}))
            return mock_response

        mock_http.post = capture_post
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("sre_triage.httpx.AsyncClient", return_value=mock_cm):
            await _send_chat_notification(report)

        text = captured_payload.get("text", "")
        assert "tronqué" in text
        assert f"{_CHAT_REPORT_MAX_CHARS} caractères" in text

    @pytest.mark.asyncio
    async def test_webhook_http_error_does_not_raise(self, monkeypatch):
        """Un webhook retournant une erreur HTTP ne doit pas faire échouer le triage."""
        monkeypatch.setenv("GOOGLE_CHAT_WEBHOOK_URL", "https://chat.example.com/hook")
        report = _make_report(response="Erreur.", severity="CRITICAL")

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("sre_triage.httpx.AsyncClient", return_value=mock_cm):
            # Ne doit pas lever d'exception
            await _send_chat_notification(report)

    @pytest.mark.asyncio
    async def test_network_error_does_not_raise(self, monkeypatch):
        """Une erreur réseau (exception httpx) ne doit pas faire échouer le triage."""
        monkeypatch.setenv("GOOGLE_CHAT_WEBHOOK_URL", "https://chat.example.com/hook")
        report = _make_report(response="Erreur.", severity="WARNING")

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=Exception("Connection refused"))
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("sre_triage.httpx.AsyncClient", return_value=mock_cm):
            await _send_chat_notification(report)  # Ne doit pas lever


# ---------------------------------------------------------------------------
# Tests _send_daily_report_chat_notification
# ---------------------------------------------------------------------------

class TestSendDailyReportChatNotification:
    """Valide l'envoi du rapport quotidien vers Google Chat."""

    @pytest.mark.asyncio
    async def test_sends_report_with_webhook(self, monkeypatch):
        """Le rapport quotidien doit toujours être envoyé si le webhook est présent."""
        monkeypatch.setenv("GOOGLE_CHAT_WEBHOOK_URL", "https://chat.example.com/hook")

        captured_payload = {}
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_http = AsyncMock()

        async def capture_post(url, **kwargs):
            captured_payload.update(kwargs.get("json", {}))
            return mock_response

        mock_http.post = capture_post
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("sre_triage.httpx.AsyncClient", return_value=mock_cm):
            await _send_daily_report_chat_notification("Rapport du jour.", "2026-06-07")

        text = captured_payload.get("text", "")
        assert "RAPPORT D'USAGE QUOTIDIEN" in text
        assert "2026-06-07" in text
        assert "Rapport du jour." in text

    @pytest.mark.asyncio
    async def test_no_webhook_does_not_send(self, monkeypatch):
        """Sans webhook, aucun appel HTTP ne doit être effectué."""
        monkeypatch.delenv("GOOGLE_CHAT_WEBHOOK_URL", raising=False)
        monkeypatch.delenv("GOOGLE_CHAT_WEBHOOK_SECRET_NAME", raising=False)
        monkeypatch.delenv("GCP_PROJECT_ID", raising=False)

        with patch("httpx.AsyncClient") as mock_cls:
            await _send_daily_report_chat_notification("Rapport.", "2026-06-07")
            mock_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_long_report_truncated(self, monkeypatch):
        """Un rapport trop long doit être tronqué et inclure un avertissement."""
        monkeypatch.setenv("GOOGLE_CHAT_WEBHOOK_URL", "https://chat.example.com/hook")
        long_report = "Y" * (_CHAT_REPORT_MAX_CHARS + 200)

        captured_payload = {}
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_http = AsyncMock()

        async def capture_post(url, **kwargs):
            captured_payload.update(kwargs.get("json", {}))
            return mock_response

        mock_http.post = capture_post
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("sre_triage.httpx.AsyncClient", return_value=mock_cm):
            await _send_daily_report_chat_notification(long_report, "2026-06-07")

        text = captured_payload.get("text", "")
        assert "tronqué" in text

    @pytest.mark.asyncio
    async def test_webhook_error_does_not_raise(self, monkeypatch):
        """Une réponse HTTP non-200 du webhook ne doit pas lever d'exception."""
        monkeypatch.setenv("GOOGLE_CHAT_WEBHOOK_URL", "https://chat.example.com/hook")

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Too Many Requests"
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("sre_triage.httpx.AsyncClient", return_value=mock_cm):
            await _send_daily_report_chat_notification("Rapport.", "2026-06-07")

    @pytest.mark.asyncio
    async def test_network_exception_does_not_raise(self, monkeypatch):
        """Une exception réseau ne doit pas faire échouer le rapport quotidien."""
        monkeypatch.setenv("GOOGLE_CHAT_WEBHOOK_URL", "https://chat.example.com/hook")

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=Exception("Timeout"))
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("sre_triage.httpx.AsyncClient", return_value=mock_cm):
            await _send_daily_report_chat_notification("Rapport.", "2026-06-07")
