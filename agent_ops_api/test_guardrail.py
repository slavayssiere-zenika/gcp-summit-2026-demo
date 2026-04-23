"""
Tests unitaires pour les guardrails anti-hallucination de l'agent Ops.

Couvre :
- GUARDRAIL 1 : réponse sans aucun appel d'outil (hallucination certaine)
  → injection du warning ⚠️ dans la réponse et les steps
- GUARDRAIL 2 : réponse avec au moins un outil → guardrail ne s'active pas
- Validation que le guardrail est bien présent dans agent.py et actif

Pattern identique à agent_hr_api/test_guardrail.py (ADR-GUARDRAIL).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import agent as agent_module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_event(role: str, text: str | None = None,
                     tool_name: str | None = None,
                     tool_result: dict | None = None) -> MagicMock:
    """Factory d'événements ADK mockés (identique au pattern HR)."""
    evt = MagicMock()
    evt.content = MagicMock()
    evt.content.role = role
    evt.actions = []
    evt.response = None
    evt.usage_metadata = None

    part = MagicMock()
    part.thought = None
    part.tool_call = None
    part.function_call = None
    part.function_response = None

    part.text = text if text else None

    if tool_name:
        fc = MagicMock()
        fc.name = tool_name
        fc.args = {"component_name": "users-api"}
        part.function_call = fc

    if tool_result is not None:
        fres = MagicMock()
        fres.name = tool_name or "check_component_health"
        inner = MagicMock()
        inner.model_dump.return_value = tool_result
        fres.response = inner
        part.function_response = fres

    evt.content.parts = [part]
    evt.get_function_calls = MagicMock(return_value=[])

    return evt


def _patch_agent_infra(mocker):
    """Patch les dépendances d'infrastructure communes à tous les tests Ops."""
    mock_session_svc = AsyncMock()
    mock_session_svc.create_session = AsyncMock()
    mock_session_svc.get_session = AsyncMock(return_value=None)

    mock_agent = MagicMock()
    mock_agent.model = "gemini-3-flash-preview"

    mock_runner = MagicMock()

    mocker.patch("agent.get_session_service", return_value=mock_session_svc)
    # Runner est importé localement dans run_agent_query : 'from google.adk.runners import Runner'
    mocker.patch("agent.Runner", return_value=mock_runner)

    return mock_session_svc, mock_agent, mock_runner


# ---------------------------------------------------------------------------
# GUARDRAIL 1 — Aucun appel d'outil (hallucination certaine)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_guardrail_no_tool_calls_injects_warning(mocker):
    """
    GUARDRAIL 1 : Si l'agent Ops répond SANS appeler aucun outil,
    le warning ⚠️ doit être injecté en tête de réponse et un step GUARDRAIL
    doit apparaître dans les steps.
    """
    evt_text = _make_mock_event("model", text="Tout fonctionne normalement. Aucun problème détecté.")

    _, _, mock_runner = _patch_agent_infra(mocker)

    async def mock_run_async(**kwargs):
        yield evt_text

    mock_runner.run_async = mock_run_async

    result = await agent_module.run_agent_query(
        "Quel est l'état général de la plateforme ?",
        session_id="ops_guard_test",
        user_id="ops_user@zenika.com"
    )

    # Le warning doit être présent dans la réponse
    assert "⚠️" in result["response"] or "ATTENTION" in result["response"], \
        "Le guardrail doit injecter un avertissement dans la réponse"
    assert "aucun outil" in result["response"].lower() or "no tool" in result["response"].lower() or \
           "GUARDRAIL" in str(result.get("steps", [])), \
        "Le guardrail doit mentionner l'absence d'outil"

    # Un step GUARDRAIL doit être présent
    guardrail_steps = [s for s in result.get("steps", []) if s.get("tool") == "GUARDRAIL"]
    assert len(guardrail_steps) >= 1, \
        "Un step GUARDRAIL doit être créé quand aucun outil n'est appelé"

    # La réponse originale ne doit pas être perdue (seulement préfixée)
    assert "normalement" in result["response"] or "plateforme" in result["response"].lower(), \
        "La réponse originale de l'agent doit être conservée (préfixée par le warning)"


@pytest.mark.asyncio
async def test_guardrail_no_tool_calls_warning_step_structure(mocker):
    """
    GUARDRAIL 1 : Le step GUARDRAIL doit respecter la structure ADK standard :
    type='warning', tool='GUARDRAIL', args={'message': ...}
    """
    evt_text = _make_mock_event("model", text="Les systèmes sont opérationnels.")
    _, _, mock_runner = _patch_agent_infra(mocker)

    async def mock_run_async(**kwargs):
        yield evt_text

    mock_runner.run_async = mock_run_async

    result = await agent_module.run_agent_query(
        "Dis-moi si tout va bien",
        session_id="ops_guard_struct",
        user_id="ops_user@zenika.com"
    )

    guardrail_steps = [s for s in result.get("steps", []) if s.get("tool") == "GUARDRAIL"]
    if guardrail_steps:
        step = guardrail_steps[0]
        assert step.get("type") == "warning", "Le step GUARDRAIL doit avoir type='warning'"
        assert "args" in step, "Le step GUARDRAIL doit avoir un champ 'args'"
        assert "message" in step.get("args", {}), "Le step GUARDRAIL doit avoir args.message"


# ---------------------------------------------------------------------------
# GUARDRAIL 2 — Avec appel d'outil → le guardrail NE doit PAS s'activer
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_guardrail_not_triggered_when_tool_called(mocker):
    """
    GUARDRAIL 1 : Si l'agent Ops a appelé au moins un outil,
    le guardrail NE DOIT PAS s'activer.
    """
    evt_call = _make_mock_event("model", tool_name="check_component_health")
    evt_result = _make_mock_event("tool", tool_result={"status": "healthy", "component": "users-api"})
    evt_text = _make_mock_event("model", text="La plateforme est en bonne santé. users-api répond correctement.")

    _, _, mock_runner = _patch_agent_infra(mocker)

    async def mock_run_async(**kwargs):
        for e in [evt_call, evt_result, evt_text]:
            yield e

    mock_runner.run_async = mock_run_async

    result = await agent_module.run_agent_query(
        "Vérifie l'état de users-api",
        session_id="ops_no_guard",
        user_id="ops_user@zenika.com"
    )

    # La réponse contient les vrais résultats, pas le warning
    assert "users-api" in result["response"] or "santé" in result["response"].lower() or \
           "healthy" in result["response"].lower(), \
        "La réponse doit contenir les informations retournées par l'outil"

    # Le guardrail NE doit PAS s'activer
    guardrail_steps = [s for s in result.get("steps", []) if s.get("tool") == "GUARDRAIL"]
    assert len(guardrail_steps) == 0, \
        "Le guardrail NE DOIT PAS s'activer quand un outil a été utilisé"


@pytest.mark.asyncio
async def test_guardrail_not_triggered_with_analytics_tool(mocker):
    """
    GUARDRAIL 1 : L'appel d'un outil FinOps (get_finops_report) doit
    désactiver le guardrail hallucination.
    """
    evt_call = _make_mock_event("model", tool_name="get_finops_report")
    evt_result = _make_mock_event("tool", tool_result={"monthly": [], "daily": []})
    evt_text = _make_mock_event("model", text="Voici le rapport FinOps du mois de janvier.")

    _, _, mock_runner = _patch_agent_infra(mocker)

    async def mock_run_async(**kwargs):
        for e in [evt_call, evt_result, evt_text]:
            yield e

    mock_runner.run_async = mock_run_async

    result = await agent_module.run_agent_query(
        "Génère le rapport FinOps mensuel",
        session_id="ops_finops_test",
        user_id="ops_user@zenika.com"
    )

    guardrail_steps = [s for s in result.get("steps", []) if s.get("tool") == "GUARDRAIL"]
    assert len(guardrail_steps) == 0, \
        "get_finops_report est un vrai outil → le guardrail NE doit pas s'activer"


@pytest.mark.asyncio
async def test_guardrail_not_triggered_for_generative_tasks(mocker):
    """
    GUARDRAIL 1 (Ops custom) : Si la requête est purement générative (ex: 'Génère un prompt'),
    le guardrail NE DOIT PAS s'activer même s'il n'y a eu aucun outil appelé.
    """
    evt_text = _make_mock_event("model", text="Voici le prompt demandé : ...")

    _, _, mock_runner = _patch_agent_infra(mocker)

    async def mock_run_async(**kwargs):
        yield evt_text

    mock_runner.run_async = mock_run_async

    result = await agent_module.run_agent_query(
        "Génère un prompt de signalement d'incident technique",
        session_id="ops_generative_test",
        user_id="ops_user@zenika.com"
    )

    guardrail_steps = [s for s in result.get("steps", []) if s.get("tool") == "GUARDRAIL"]
    assert len(guardrail_steps) == 0, \
        "Tâche purement générative (génère...) → le guardrail NE doit pas s'activer"
    assert "⚠️" not in result["response"], "Le warning ne doit pas être injecté"


# ---------------------------------------------------------------------------
# Tests de structure de la réponse
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_agent_query_returns_complete_structure(mocker):
    """
    run_agent_query doit toujours retourner un dict avec les clés :
    response, data, steps, thoughts, usage.
    """
    evt_call = _make_mock_event("model", tool_name="list_gcp_services")
    evt_result = _make_mock_event("tool", tool_result={"services": []})
    evt_text = _make_mock_event("model", text="Aucun service Cloud Run trouvé.")

    _, _, mock_runner = _patch_agent_infra(mocker)

    async def mock_run_async(**kwargs):
        for e in [evt_call, evt_result, evt_text]:
            yield e

    mock_runner.run_async = mock_run_async

    result = await agent_module.run_agent_query(
        "Liste les services GCP",
        session_id="ops_struct_test",
        user_id="ops_user@zenika.com"
    )

    # Structure complète requise
    assert "response" in result, "Champ 'response' manquant"
    assert "steps" in result, "Champ 'steps' manquant"
    assert "thoughts" in result, "Champ 'thoughts' manquant"
    assert "usage" in result, "Champ 'usage' manquant"
    assert isinstance(result["steps"], list), "'steps' doit être une liste"
    assert isinstance(result["usage"], dict), "'usage' doit être un dict"

    usage = result["usage"]
    assert "total_input_tokens" in usage, "usage.total_input_tokens manquant"
    assert "total_output_tokens" in usage, "usage.total_output_tokens manquant"
    assert "estimated_cost_usd" in usage, "usage.estimated_cost_usd manquant"


@pytest.mark.asyncio
async def test_run_agent_query_session_isolation(mocker):
    """
    Deux appels avec des session_id différents ne doivent pas partager d'état.
    """
    evt_text = _make_mock_event("model", tool_name="check_all_components_health")
    evt_result = _make_mock_event("tool", tool_result=[{"status": "healthy"}])
    evt_response = _make_mock_event("model", text="Tout va bien.")

    _, _, mock_runner = _patch_agent_infra(mocker)

    async def mock_run_async(**kwargs):
        for e in [evt_text, evt_result, evt_response]:
            yield e

    mock_runner.run_async = mock_run_async

    result_1 = await agent_module.run_agent_query("Test 1", session_id="session_ops_1", user_id="u1")
    result_2 = await agent_module.run_agent_query("Test 2", session_id="session_ops_2", user_id="u2")

    # Les résultats doivent être indépendants
    assert result_1 is not None
    assert result_2 is not None
    # Les steps ne doivent pas être partagés entre sessions
    assert result_1.get("steps") is not result_2.get("steps"), \
        "Les steps ne doivent pas être partagés entre sessions"
