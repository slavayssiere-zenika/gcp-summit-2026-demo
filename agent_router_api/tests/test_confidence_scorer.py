"""Tests unitaires pour _compute_confidence et le champ confidence (P2-4).

Couvre :
- Score 1.0 quand les tools ont été appelés sans aucun guardrail.
- Score réduit de 0.2 par step guardrail activé (GUARDRAIL_HALLUCINATION, etc.).
- Score réduit de 0.1 par step TOOL_BUDGET.
- Score réduit de 0.3 si aucun outil appelé.
- Floor à 0.0 même avec plusieurs pénalités combinées.
- Score 0.5 si steps est None ou vide (trace inconnue).
- Arrondi à 2 décimales.
- _GUARDRAIL_TOOLS contient tous les guardrails connus.
- Champ confidence propagé dans les wrappers A2A (ask_hr_agent etc.).
"""

import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from a2a_tools import (
    _GUARDRAIL_TOOLS,
    _compute_confidence,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _call_step(tool: str) -> dict:
    return {"type": "call", "tool": tool, "args": {}}


def _warning_step(tool: str) -> dict:
    return {"type": "warning", "tool": tool, "args": {"message": "test"}}


def _result_step(data: dict = None) -> dict:
    return {"type": "result", "data": data or {}}


# ---------------------------------------------------------------------------
# Tests _compute_confidence
# ---------------------------------------------------------------------------

class TestComputeConfidence:
    def test_no_steps_returns_half(self):
        """steps=[] → score 0.5 (trace inconnue)."""
        assert _compute_confidence([]) == 0.5

    def test_tool_calls_only_returns_one(self):
        """Steps avec uniquement des appels d'outils → confidence 1.0."""
        steps = [_call_step("search_users"), _call_step("get_mission"), _result_step()]
        assert _compute_confidence(steps) == 1.0

    def test_no_tool_calls_reduces_score(self):
        """Aucun appel d'outil → -0.3 (risque hallucination)."""
        steps = [_result_step(), _result_step()]
        assert _compute_confidence(steps) == 0.7

    def test_one_guardrail_reduces_by_0_2(self):
        """Un guardrail activé → -0.2."""
        steps = [_call_step("search_users"), _warning_step("GUARDRAIL_HALLUCINATION")]
        assert _compute_confidence(steps) == 0.8

    def test_two_guardrails_reduce_by_0_4(self):
        """Deux guardrails → -0.4."""
        steps = [
            _call_step("get_finops_report"),
            _warning_step("GUARDRAIL_HALLUCINATION"),
            _warning_step("GUARDRAIL_OPS_METRICS"),
        ]
        assert _compute_confidence(steps) == 0.6

    def test_tool_budget_reduces_by_0_1(self):
        """TOOL_BUDGET → -0.1."""
        steps = [_call_step("search_users"), _warning_step("TOOL_BUDGET")]
        assert _compute_confidence(steps) == 0.9

    def test_guardrail_plus_tool_budget(self):
        """Un guardrail + TOOL_BUDGET → -0.3 total."""
        steps = [
            _call_step("search_users"),
            _warning_step("GUARDRAIL_HALLUCINATION"),
            _warning_step("TOOL_BUDGET"),
        ]
        assert _compute_confidence(steps) == 0.7

    def test_no_tool_plus_guardrail_cumulative(self):
        """Pas d'appel d'outil + guardrail → -0.3 -0.2 = 0.5."""
        steps = [_warning_step("GUARDRAIL_HALLUCINATION")]
        assert _compute_confidence(steps) == 0.5

    def test_score_floored_at_zero(self):
        """Score ne peut pas descendre sous 0.0 même avec de nombreuses pénalités."""
        # no calls (-0.3) + 5 guardrails (-1.0) → floored at 0.0
        steps = [_warning_step(t) for t in [
            "GUARDRAIL_HALLUCINATION",
            "GUARDRAIL_OPS_METRICS",
            "GUARDRAIL_ID_INVENTION",
            "GUARDRAIL_GROUNDING",
            "GUARDRAIL_COM006",
        ]]
        assert _compute_confidence(steps) == 0.0

    def test_score_capped_at_one(self):
        """Score ne dépasse pas 1.0 même sans pénalité."""
        steps = [_call_step("tool_a"), _call_step("tool_b"), _result_step()]
        assert _compute_confidence(steps) <= 1.0

    def test_unknown_warning_tool_not_penalized(self):
        """Un step warning avec un tool inconnu ne doit pas pénaliser la confiance."""
        steps = [
            _call_step("search_users"),
            _warning_step("CUSTOM_UNKNOWN_GUARDRAIL"),  # not in _GUARDRAIL_TOOLS
        ]
        # Only call_step — no known guardrail fired → score = 1.0
        assert _compute_confidence(steps) == 1.0

    def test_returns_rounded_to_two_decimals(self):
        """Le score est arrondi à 2 décimales."""
        steps = [_call_step("tool_a"), _warning_step("GUARDRAIL_HALLUCINATION")]
        result = _compute_confidence(steps)
        assert result == round(result, 2)

    def test_all_known_guardrails_penalize(self):
        """Chaque outil de _GUARDRAIL_TOOLS doit entraîner une pénalité de 0.2."""
        for tool in _GUARDRAIL_TOOLS:
            steps = [_call_step("any_tool"), _warning_step(tool)]
            score = _compute_confidence(steps)
            assert score == 0.8, f"Tool '{tool}' should reduce confidence by 0.2, got {score}"

    def test_circuit_breaker_steps_empty(self):
        """Mode dégradé (circuit-breaker) retourne steps=[warning] → aucun call → 0.5."""
        steps = [_warning_step("hr_agent:CB_OPEN")]
        # CB_OPEN is not in _GUARDRAIL_TOOLS, no call → -0.3 only
        assert _compute_confidence(steps) == 0.7


# ---------------------------------------------------------------------------
# Tests de la whitelist _GUARDRAIL_TOOLS
# ---------------------------------------------------------------------------

class TestGuardrailTools:
    def test_known_guardrails_in_whitelist(self):
        """Tous les guardrails de la plateforme doivent être dans _GUARDRAIL_TOOLS."""
        expected = {
            "GUARDRAIL_HALLUCINATION",
            "GUARDRAIL_OPS_METRICS",
            "GUARDRAIL_ID_INVENTION",
            "GUARDRAIL_GROUNDING",
            "GUARDRAIL_COM006",
            "GUARDRAIL_GROUNDING_HR",
        }
        assert expected.issubset(_GUARDRAIL_TOOLS), (
            f"Missing from _GUARDRAIL_TOOLS: {expected - _GUARDRAIL_TOOLS}"
        )

    def test_tool_budget_not_in_guardrail_whitelist(self):
        """TOOL_BUDGET doit être traité séparément (pénalité -0.1) pas comme un guardrail (-0.2)."""
        assert "TOOL_BUDGET" not in _GUARDRAIL_TOOLS


# ---------------------------------------------------------------------------
# Tests d'intégration : confidence propagée dans les wrappers A2A
# ---------------------------------------------------------------------------

VALID_A2A_RESPONSE = {
    "response": "OK",
    "data": None,
    "steps": [{"type": "call", "tool": "search_users", "args": {}}],
    "thoughts": "",
    "usage": {"total_input_tokens": 10, "total_output_tokens": 5, "estimated_cost_usd": 0.0},
}

GUARDRAIL_A2A_RESPONSE = {
    "response": "⚠️ Avertissement : ...",
    "data": None,
    "steps": [
        {"type": "call", "tool": "search_users", "args": {}},
        {"type": "warning", "tool": "GUARDRAIL_HALLUCINATION", "args": {"message": "test"}},
    ],
    "thoughts": "",
    "usage": {"total_input_tokens": 10, "total_output_tokens": 5, "estimated_cost_usd": 0.0},
}


def _mock_http_response(payload: dict, mocker) -> MagicMock:
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = payload
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


@pytest.mark.asyncio
async def test_ask_hr_agent_returns_confidence_1_0_on_clean_response(mocker):
    """ask_hr_agent propage confidence=1.0 quand aucun guardrail n'a été déclenché."""
    mocker.patch("a2a_tools.A2A_CALL_DURATION")
    mocker.patch("a2a_tools.A2A_CALL_ERRORS_TOTAL")
    mocker.patch("a2a_tools.A2A_CALL_RETRIES_TOTAL")

    mock_client = AsyncMock()
    mock_client.post.return_value = _mock_http_response(VALID_A2A_RESPONSE, mocker)
    mocker.patch("a2a_tools.httpx.AsyncClient", return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=mock_client),
        __aexit__=AsyncMock(return_value=False),
    ))
    mocker.patch("a2a_tools.os.getenv", return_value="http://fake:8080")

    from a2a_tools import ask_hr_agent
    result_raw = await ask_hr_agent("Quels consultants connaissent Python ?")
    result = json.loads(result_raw["result"])

    assert "confidence" in result
    assert result["confidence"] == 1.0


@pytest.mark.asyncio
async def test_ask_hr_agent_returns_confidence_below_1_on_guardrail(mocker):
    """ask_hr_agent propage confidence<1.0 quand un guardrail s'est déclenché."""
    mocker.patch("a2a_tools.A2A_CALL_DURATION")
    mocker.patch("a2a_tools.A2A_CALL_ERRORS_TOTAL")
    mocker.patch("a2a_tools.A2A_CALL_RETRIES_TOTAL")

    mock_client = AsyncMock()
    mock_client.post.return_value = _mock_http_response(GUARDRAIL_A2A_RESPONSE, mocker)
    mocker.patch("a2a_tools.httpx.AsyncClient", return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=mock_client),
        __aexit__=AsyncMock(return_value=False),
    ))
    mocker.patch("a2a_tools.os.getenv", return_value="http://fake:8080")

    from a2a_tools import ask_hr_agent
    result_raw = await ask_hr_agent("test")
    result = json.loads(result_raw["result"])

    assert result["confidence"] < 1.0
    assert result["confidence"] == 0.8  # 1.0 - 0.2 (one guardrail)


@pytest.mark.asyncio
async def test_confidence_schema_validation(mocker):
    """Le champ confidence respecte les contraintes Pydantic (0.0 <= confidence <= 1.0)."""
    from agent_commons.schemas import A2AResponse

    # Valid: confidence = 0.8
    response = A2AResponse(
        response="OK",
        confidence=0.8,
    )
    assert response.confidence == 0.8

    # Valid: confidence = None
    response_none = A2AResponse(response="OK", confidence=None)
    assert response_none.confidence is None


@pytest.mark.asyncio
async def test_confidence_schema_rejects_out_of_range(mocker):
    """Pydantic rejette une confidence < 0.0 ou > 1.0."""
    from pydantic import ValidationError
    from agent_commons.schemas import A2AResponse

    with pytest.raises(ValidationError):
        A2AResponse(response="OK", confidence=1.5)

    with pytest.raises(ValidationError):
        A2AResponse(response="OK", confidence=-0.1)
