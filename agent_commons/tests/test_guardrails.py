"""Tests for agent_commons.guardrails module."""

import pytest

from agent_commons.guardrails import (
    check_empty_candidate_guardrail,
    check_hallucination_guardrail,
    is_empty_candidate_result,
)


# ---------------------------------------------------------------------------
# Guardrail 1 — Zero tool calls
# ---------------------------------------------------------------------------

class TestCheckHallucinationGuardrail:
    def test_no_warning_when_tool_was_called(self):
        steps = [{"type": "call", "tool": "search_users", "args": {}}]
        response, new_steps = check_hallucination_guardrail("Some answer", steps)
        assert response == "Some answer"
        assert new_steps == steps  # unchanged

    def test_warning_injected_when_no_tool_called(self):
        steps = []
        response, new_steps = check_hallucination_guardrail("Invented answer", steps)
        assert "⚠️" in response
        assert any(s.get("tool") == "GUARDRAIL" for s in new_steps)

    def test_no_action_when_response_is_empty(self):
        steps = []
        response, new_steps = check_hallucination_guardrail("", steps)
        assert response == ""
        assert new_steps == []

    def test_caller_steps_list_not_mutated(self):
        original = []
        _, new_steps = check_hallucination_guardrail("answer", original)
        assert original == []  # caller's list is untouched

    def test_result_steps_do_not_count_as_tool_calls(self):
        """Only 'call' type steps satisfy the guardrail — results alone are not enough."""
        steps = [{"type": "result", "data": {}}]
        _, new_steps = check_hallucination_guardrail("answer", steps)
        assert any(s.get("tool") == "GUARDRAIL" for s in new_steps)


# ---------------------------------------------------------------------------
# Guardrail 2 — COM-006 (empty candidate results)
# ---------------------------------------------------------------------------

class TestIsEmptyCandidateResult:
    def test_none_is_empty(self):
        assert is_empty_candidate_result(None) is True

    def test_empty_list_is_empty(self):
        assert is_empty_candidate_result([]) is True

    def test_nonempty_list_is_not_empty(self):
        assert is_empty_candidate_result([{"id": 1}]) is False

    def test_dict_with_empty_results_key(self):
        assert is_empty_candidate_result({"results": [], "total": 0}) is True

    def test_dict_with_nonempty_results_key(self):
        assert is_empty_candidate_result({"results": [{"id": 1}]}) is False

    def test_dict_with_total_zero(self):
        assert is_empty_candidate_result({"total": 0}) is True

    def test_dict_with_count_zero(self):
        assert is_empty_candidate_result({"count": 0}) is True

    def test_dict_with_positive_total(self):
        assert is_empty_candidate_result({"total": 5}) is False


class TestCheckEmptyCandidateGuardrail:
    def test_no_candidate_results_no_action(self):
        response, steps, data = check_empty_candidate_guardrail([], "answer", [])
        assert response == "answer"
        assert steps == []
        assert data is None

    def test_nonempty_results_no_action(self):
        search_results = [{"tool": "search_users", "result": [{"id": 1}]}]
        response, steps, data = check_empty_candidate_guardrail(search_results, "answer", [])
        assert response == "answer"

    def test_all_empty_results_triggers_override(self):
        search_results = [
            {"tool": "search_best_candidates", "result": []},
            {"tool": "search_users", "result": {"total": 0}},
        ]
        response, steps, data = check_empty_candidate_guardrail(search_results, "Invented list", [])
        assert "Aucun profil trouvé" in response
        assert any(s.get("tool") == "GUARDRAIL_COM006" for s in steps)
        assert data is None

    def test_partially_empty_does_not_trigger(self):
        """COM-006 fires only when ALL searches are empty."""
        search_results = [
            {"tool": "search_best_candidates", "result": []},
            {"tool": "search_users", "result": [{"id": 1}]},
        ]
        response, steps, _ = check_empty_candidate_guardrail(search_results, "answer", [])
        assert response == "answer"
        assert not any(s.get("tool") == "GUARDRAIL_COM006" for s in steps)

    def test_caller_steps_not_mutated(self):
        original_steps = []
        search_results = [{"tool": "search_users", "result": []}]
        _, new_steps, _ = check_empty_candidate_guardrail(search_results, "answer", original_steps)
        assert original_steps == []
