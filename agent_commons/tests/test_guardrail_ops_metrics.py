"""Tests unitaires pour check_ops_metrics_guardrail (Guardrail P0-2).

Couvre :
- Pas de déclenchement si aucune métrique dans la réponse.
- Déclenchement si métriques présentes sans appel FinOps préalable.
- Pas de déclenchement si un outil FinOps a été appelé.
- Variantes de patterns de métriques (USD, tokens, €, %, ms).
- Immutabilité de la liste de steps passée en paramètre.
- Structure du step GUARDRAIL_OPS_METRICS.
"""

import pytest

from agent_commons.guardrails import (
    FINOPS_MONITORING_TOOLS,
    check_ops_metrics_guardrail,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_call_step(tool_name: str) -> dict:
    return {"type": "call", "tool": tool_name, "args": {}}


def _make_result_step(data: dict) -> dict:
    return {"type": "result", "data": data}


# ---------------------------------------------------------------------------
# Cas nominaux — pas de déclenchement
# ---------------------------------------------------------------------------

class TestOpsMetricsGuardrailNoTrigger:
    def test_no_metrics_no_trigger(self):
        """Réponse sans chiffre → guardrail silencieux."""
        response = "Tout fonctionne normalement. Les services répondent correctement."
        response_out, steps_out = check_ops_metrics_guardrail(response, [])
        assert response_out == response
        assert steps_out == []

    def test_grounded_metrics_with_finops_tool(self):
        """Réponse avec métriques ET appel FinOps préalable → pas de guardrail."""
        steps = [_make_call_step("get_finops_report")]
        response = "Le coût total est de $42.50 cette semaine. 15 000 tokens consommés."
        response_out, steps_out = check_ops_metrics_guardrail(response, steps)
        assert response_out == response
        assert not any(s.get("tool") == "GUARDRAIL_OPS_METRICS" for s in steps_out)

    def test_grounded_metrics_with_service_logs_tool(self):
        """get_service_logs est un outil FinOps/monitoring → autorise les métriques."""
        steps = [_make_call_step("get_service_logs")]
        response = "5 erreurs détectées en 10 minutes. Latence moyenne : 320ms."
        response_out, steps_out = check_ops_metrics_guardrail(response, steps)
        assert response_out == response
        assert not any(s.get("tool") == "GUARDRAIL_OPS_METRICS" for s in steps_out)

    def test_grounded_metrics_with_health_check_tool(self):
        """check_all_components_health → autorise les métriques de statut."""
        steps = [_make_call_step("check_all_components_health")]
        response = "3 services sur 10 sont en erreur. 70% de disponibilité globale."
        response_out, steps_out = check_ops_metrics_guardrail(response, steps)
        assert response_out == response
        assert not any(s.get("tool") == "GUARDRAIL_OPS_METRICS" for s in steps_out)

    def test_all_finops_tools_grant_permission(self):
        """Chaque outil de FINOPS_MONITORING_TOOLS doit autoriser les métriques."""
        response = "Résultat : $1.23, 500 tokens, 99% uptime, 150ms latency."
        for tool in FINOPS_MONITORING_TOOLS:
            steps = [_make_call_step(tool)]
            response_out, steps_out = check_ops_metrics_guardrail(response, steps)
            assert response_out == response, f"Tool '{tool}' should grant permission"
            assert not any(
                s.get("tool") == "GUARDRAIL_OPS_METRICS" for s in steps_out
            ), f"Tool '{tool}' should prevent GUARDRAIL_OPS_METRICS from firing"


# ---------------------------------------------------------------------------
# Cas de déclenchement — métriques sans appel FinOps
# ---------------------------------------------------------------------------

class TestOpsMetricsGuardrailTriggered:
    def test_dollar_amount_without_tool_triggers(self):
        """Un montant en dollars sans outil FinOps → guardrail activé."""
        response = "La plateforme a coûté $15.42 ce mois-ci."
        response_out, steps_out = check_ops_metrics_guardrail(response, [])
        assert "⚠️" in response_out
        assert any(s.get("tool") == "GUARDRAIL_OPS_METRICS" for s in steps_out)

    def test_tokens_count_without_tool_triggers(self):
        """Comptage de tokens sans outil FinOps → guardrail activé."""
        response = "Environ 50 000 tokens ont été utilisés par l'agent HR."
        response_out, steps_out = check_ops_metrics_guardrail(response, [])
        assert "⚠️" in response_out
        assert any(s.get("tool") == "GUARDRAIL_OPS_METRICS" for s in steps_out)

    def test_euro_amount_without_tool_triggers(self):
        """Montant en euros sans outil FinOps → guardrail activé."""
        response = "Le coût estimé est de 32€ pour les 7 derniers jours."
        response_out, steps_out = check_ops_metrics_guardrail(response, [])
        assert "⚠️" in response_out
        assert any(s.get("tool") == "GUARDRAIL_OPS_METRICS" for s in steps_out)

    def test_percentage_without_tool_triggers(self):
        """Pourcentage d'uptime sans outil monitoring → guardrail activé."""
        response = "La disponibilité du système est de 99.5% sur les 30 derniers jours."
        response_out, steps_out = check_ops_metrics_guardrail(response, [])
        assert "⚠️" in response_out
        assert any(s.get("tool") == "GUARDRAIL_OPS_METRICS" for s in steps_out)

    def test_millisecond_latency_without_tool_triggers(self):
        """Latence en millisecondes sans outil → guardrail activé."""
        response = "Le temps de réponse moyen est de 245ms pour l'API des missions."
        response_out, steps_out = check_ops_metrics_guardrail(response, [])
        assert "⚠️" in response_out
        assert any(s.get("tool") == "GUARDRAIL_OPS_METRICS" for s in steps_out)

    def test_usd_abbreviation_without_tool_triggers(self):
        """USD sans outil → guardrail activé."""
        response = "Le coût total est de 0.025 USD par requête."
        response_out, steps_out = check_ops_metrics_guardrail(response, [])
        assert "⚠️" in response_out
        assert any(s.get("tool") == "GUARDRAIL_OPS_METRICS" for s in steps_out)

    def test_non_finops_tool_does_not_grant_permission(self):
        """Un outil RH (search_users) ne doit PAS autoriser les métriques FinOps."""
        steps = [_make_call_step("search_users")]
        response = "Le coût total est de $42.50 cette semaine."
        response_out, steps_out = check_ops_metrics_guardrail(response, steps)
        assert "⚠️" in response_out
        assert any(s.get("tool") == "GUARDRAIL_OPS_METRICS" for s in steps_out)

    def test_result_steps_do_not_grant_permission(self):
        """Les steps de type 'result' ne comptent pas comme appels d'outils FinOps."""
        steps = [_make_result_step({"cost": 42.5})]
        response = "Le coût est de $42.50."
        response_out, steps_out = check_ops_metrics_guardrail(response, steps)
        assert "⚠️" in response_out
        assert any(s.get("tool") == "GUARDRAIL_OPS_METRICS" for s in steps_out)


# ---------------------------------------------------------------------------
# Structure du step GUARDRAIL_OPS_METRICS
# ---------------------------------------------------------------------------

class TestOpsMetricsGuardrailStepStructure:
    def test_guardrail_step_has_correct_type(self):
        response = "Coût : $10.00."
        _, steps_out = check_ops_metrics_guardrail(response, [])
        guardrail_steps = [s for s in steps_out if s.get("tool") == "GUARDRAIL_OPS_METRICS"]
        assert len(guardrail_steps) == 1
        assert guardrail_steps[0]["type"] == "warning"

    def test_guardrail_step_is_inserted_first(self):
        """Le step GUARDRAIL doit être inséré en première position."""
        existing_step = _make_call_step("search_users")
        steps = [existing_step]
        response = "Coût : $10.00."
        _, steps_out = check_ops_metrics_guardrail(response, steps)
        assert steps_out[0]["tool"] == "GUARDRAIL_OPS_METRICS"

    def test_guardrail_step_has_message_in_args(self):
        response = "Le système consomme 25 tokens par seconde."
        _, steps_out = check_ops_metrics_guardrail(response, [])
        guardrail_steps = [s for s in steps_out if s.get("tool") == "GUARDRAIL_OPS_METRICS"]
        assert "args" in guardrail_steps[0]
        assert "message" in guardrail_steps[0]["args"]
        assert len(guardrail_steps[0]["args"]["message"]) > 20

    def test_response_prefixed_with_warning(self):
        """La réponse doit être préfixée par le warning, pas remplacée."""
        original = "Le coût est de $5.00."
        response_out, _ = check_ops_metrics_guardrail(original, [])
        assert "⚠️" in response_out
        assert original in response_out, "Le texte original doit être conservé"

    def test_guardrail_fires_only_once_per_call(self):
        """Un seul step GUARDRAIL_OPS_METRICS par appel, même si plusieurs métriques."""
        response = "Coût : $10.00. Tokens : 5000. Latence : 200ms. Uptime : 99%."
        _, steps_out = check_ops_metrics_guardrail(response, [])
        guardrail_steps = [s for s in steps_out if s.get("tool") == "GUARDRAIL_OPS_METRICS"]
        assert len(guardrail_steps) == 1


# ---------------------------------------------------------------------------
# Immutabilité
# ---------------------------------------------------------------------------

class TestOpsMetricsGuardrailImmutability:
    def test_original_steps_not_mutated_when_triggered(self):
        original_steps = [_make_call_step("search_users")]
        original_len = len(original_steps)
        response = "Coût : $10.00."
        check_ops_metrics_guardrail(response, original_steps)
        assert len(original_steps) == original_len, "La liste originale ne doit pas être mutée"

    def test_original_steps_not_mutated_when_not_triggered(self):
        steps = [_make_call_step("get_finops_report")]
        original_len = len(steps)
        check_ops_metrics_guardrail("Coût : $10.00.", steps)
        assert len(steps) == original_len
