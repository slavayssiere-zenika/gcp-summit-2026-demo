"""
Tests unitaires pour les guardrails anti-hallucination de l'agent HR.

Couvre :
- GUARDRAIL 1 : réponse sans aucun appel d'outil (hallucination certaine)
- GUARDRAIL 2 COM-006 : search_best_candidates / search_users retournent 0 résultats
  mais l'agent produit quand même une liste de profils fictifs.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from agent import CANDIDATE_SEARCH_TOOLS, _is_empty_candidate_result
import agent as agent_module


# ---------------------------------------------------------------------------
# Tests unitaires sur _is_empty_candidate_result (niveau module)
# ---------------------------------------------------------------------------

class TestIsEmptyCandidateResult:
    """Valide la logique de détection de résultats vides."""

    def test_none_is_empty(self):
        assert _is_empty_candidate_result(None) is True

    def test_empty_list(self):
        assert _is_empty_candidate_result([]) is True

    def test_nonempty_list(self):
        assert _is_empty_candidate_result([{"id": 1, "name": "Alice"}]) is False

    def test_dict_with_empty_results_key(self):
        assert _is_empty_candidate_result({"results": [], "total": 0}) is True

    def test_dict_with_nonempty_results_key(self):
        assert _is_empty_candidate_result({"results": [{"id": 42}], "total": 1}) is False

    def test_dict_with_empty_candidates_key(self):
        assert _is_empty_candidate_result({"candidates": []}) is True

    def test_dict_with_empty_users_key(self):
        assert _is_empty_candidate_result({"users": [], "count": 0}) is True

    def test_dict_with_zero_total(self):
        assert _is_empty_candidate_result({"total": 0}) is True

    def test_dict_with_zero_count(self):
        assert _is_empty_candidate_result({"count": 0}) is True

    def test_dict_without_known_key_is_not_empty(self):
        # Un dict sans clé connue ne doit pas être faussement détecté comme vide
        assert _is_empty_candidate_result({"something": "value"}) is False

    def test_nonempty_candidates(self):
        assert _is_empty_candidate_result({"candidates": [{"id": 7}]}) is False

    def test_nonempty_users(self):
        assert _is_empty_candidate_result({"users": [{"id": 12}], "count": 1}) is False


# ---------------------------------------------------------------------------
# Tests sur CANDIDATE_SEARCH_TOOLS (périmètre de surveillance)
# ---------------------------------------------------------------------------

class TestCandidateSearchTools:
    """Vérifie que les outils surveillés sont correctement définis."""

    def test_search_best_candidates_in_set(self):
        assert "search_best_candidates" in CANDIDATE_SEARCH_TOOLS

    def test_search_users_in_set(self):
        assert "search_users" in CANDIDATE_SEARCH_TOOLS

    def test_list_users_in_set(self):
        assert "list_users" in CANDIDATE_SEARCH_TOOLS

    def test_get_users_by_tag_in_set(self):
        assert "get_users_by_tag" in CANDIDATE_SEARCH_TOOLS

    def test_non_search_tool_not_in_set(self):
        assert "get_user_competencies" not in CANDIDATE_SEARCH_TOOLS
        assert "analyze_cv" not in CANDIDATE_SEARCH_TOOLS
        assert "sync_drive_folder" not in CANDIDATE_SEARCH_TOOLS
        assert "get_candidate_rag_context" not in CANDIDATE_SEARCH_TOOLS


# ---------------------------------------------------------------------------
# Helpers pour les tests d'intégration run_agent_query
# ---------------------------------------------------------------------------

def _make_mock_event(role: str, text: str | None = None, tool_name: str | None = None,
                     tool_result=None) -> MagicMock:
    """Factory d'événements ADK mockés pour simuler le stream de runner.run_async."""
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
    part.text = text

    if tool_name:
        fc = MagicMock()
        fc.name = tool_name
        fc.args = {"query": "test"}
        part.function_call = fc

    if tool_result is not None:
        fres = MagicMock()
        fres.name = tool_name or "search_best_candidates"
        inner = MagicMock()
        inner.model_dump.return_value = tool_result
        fres.response = inner
        part.function_response = fres

    evt.content.parts = [part]
    evt.get_function_calls = MagicMock(return_value=[])

    return evt


def _setup_runner_mock(mocker, events: list):
    """Configure les mocks Runner, create_agent et get_session_service."""
    mock_session_svc = AsyncMock()
    mock_session_svc.create_session = AsyncMock()
    mock_session_svc.get_session = AsyncMock(return_value=None)

    mock_agent = MagicMock()
    mock_agent.model = "gemini-2.0-flash"

    mock_runner = MagicMock()

    async def mock_run_async(**kwargs):
        for e in events:
            yield e

    mock_runner.run_async = mock_run_async

    mocker.patch("agent.get_session_service", return_value=mock_session_svc)
    mocker.patch("agent.create_agent", return_value=mock_agent)
    mocker.patch("google.adk.runners.Runner", return_value=mock_runner)


# ---------------------------------------------------------------------------
# Tests d'intégration run_agent_query — GUARDRAIL COM-006
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_guardrail_com006_triggered_when_search_returns_empty_list(mocker):
    """
    COM-006 : Si search_best_candidates retourne [] et que l'agent produit
    quand même du texte avec des noms, le guardrail doit substituer la réponse.
    """
    events = [
        _make_mock_event("model", tool_name="search_best_candidates"),
        _make_mock_event("tool", tool_result=[]),  # résultat vide
        _make_mock_event("model", text="Voici 3 consultants : Alice, Bob, Charlie."),  # hallucination
    ]
    _setup_runner_mock(mocker, events)

    result = await agent_module.run_agent_query("Qui connaît Cobol ?", session_id="test")

    assert "Aucun profil trouvé" in result["response"]
    assert "Souhaitez-vous élargir" in result["response"]
    # La réponse hallucinée NE DOIT PAS apparaître
    assert "Alice" not in result["response"]
    assert result["data"] is None

    guardrail_steps = [s for s in result["steps"] if s.get("tool") == "GUARDRAIL_COM006"]
    assert len(guardrail_steps) == 1, "Le step GUARDRAIL_COM006 doit être présent"
    assert "search_best_candidates" in guardrail_steps[0]["args"]["message"]


@pytest.mark.asyncio
async def test_guardrail_com006_triggered_when_search_returns_empty_dict(mocker):
    """
    COM-006 : Format dict {\"results\": [], \"total\": 0} doit aussi déclencher le guardrail.
    """
    events = [
        _make_mock_event("model", tool_name="search_best_candidates"),
        _make_mock_event("tool", tool_result={"results": [], "total": 0}),
        _make_mock_event("model", text="Je n'ai pas trouvé mais voici David M. qui pourrait convenir."),
    ]
    _setup_runner_mock(mocker, events)

    result = await agent_module.run_agent_query("Expert Cobol disponible ?", session_id="test")

    assert "Aucun profil trouvé" in result["response"]
    guardrail_steps = [s for s in result["steps"] if s.get("tool") == "GUARDRAIL_COM006"]
    assert len(guardrail_steps) == 1


@pytest.mark.asyncio
async def test_guardrail_com006_not_triggered_when_results_found(mocker):
    """
    COM-006 NÉGATIF : Si search_best_candidates retourne des résultats réels,
    le guardrail NE DOIT PAS s'activer et la réponse de l'agent doit être préservée.
    """
    events = [
        _make_mock_event("model", tool_name="search_best_candidates"),
        _make_mock_event("tool", tool_result=[{"id": 42, "name": "Alice Dupont", "score": 0.92}]),
        _make_mock_event("model", text="Alice Dupont (ID #42) est disponible avec un score de 0.92."),
    ]
    _setup_runner_mock(mocker, events)

    result = await agent_module.run_agent_query("Qui connaît Python ?", session_id="test")

    assert "Alice Dupont" in result["response"]
    guardrail_steps = [s for s in result["steps"] if s.get("tool") == "GUARDRAIL_COM006"]
    assert len(guardrail_steps) == 0, "Le guardrail NE DOIT PAS se déclencher quand des résultats existent"


@pytest.mark.asyncio
async def test_guardrail_com006_not_triggered_when_no_search_tool_called(mocker):
    """
    COM-006 NÉGATIF : Si aucun outil de recherche de candidats n'est appelé,
    le guardrail COM-006 ne doit pas s'activer (GUARDRAIL 1 peut s'activer à la place).
    """
    events = [
        _make_mock_event("model", tool_name="get_user_competencies"),
        _make_mock_event("tool", tool_result={"competencies": ["Python", "Java"]}),
        _make_mock_event("model", text="Sébastien maîtrise Python et Java."),
    ]
    _setup_runner_mock(mocker, events)

    result = await agent_module.run_agent_query("Compétences de Sébastien ?", session_id="test")

    guardrail_com006_steps = [s for s in result["steps"] if s.get("tool") == "GUARDRAIL_COM006"]
    assert len(guardrail_com006_steps) == 0, "COM-006 ne doit pas se déclencher pour get_user_competencies"


# ---------------------------------------------------------------------------
# Tests d'intégration run_agent_query — GUARDRAIL 1 (zéro outil)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_guardrail1_no_tool_calls_triggers_warning(mocker):
    """
    GUARDRAIL 1 : Si l'agent répond sans appeler aucun outil, le warning de
    hallucination doit être injecté dans la réponse ET dans les steps.
    """
    events = [
        _make_mock_event("model", text="Jean Martin est disponible dès lundi."),
    ]
    _setup_runner_mock(mocker, events)

    result = await agent_module.run_agent_query("Qui est disponible ?", session_id="test")

    assert "⚠️ ATTENTION" in result["response"]
    assert "aucun outil MCP consulté" in result["response"]
    # Le texte original doit toujours être présent (on le préfixe, on ne le remplace pas)
    assert "Jean Martin" in result["response"]

    guardrail_steps = [s for s in result["steps"] if s.get("tool") == "GUARDRAIL"]
    assert len(guardrail_steps) == 1


@pytest.mark.asyncio
async def test_guardrail1_not_triggered_when_tools_called(mocker):
    """
    GUARDRAIL 1 NÉGATIF : Si des outils sont appelés, aucun warning de hallucination
    de type GUARDRAIL (zéro-outil) ne doit apparaître.
    """
    events = [
        _make_mock_event("model", tool_name="search_best_candidates"),
        _make_mock_event("tool", tool_result=[{"id": 1}]),
        _make_mock_event("model", text="Résultat trouvé."),
    ]
    _setup_runner_mock(mocker, events)

    result = await agent_module.run_agent_query("Expert AWS ?", session_id="test")

    guardrail_steps = [s for s in result["steps"] if s.get("tool") == "GUARDRAIL"]
    assert len(guardrail_steps) == 0
