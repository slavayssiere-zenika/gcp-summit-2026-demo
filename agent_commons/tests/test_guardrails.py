"""Tests for agent_commons.guardrails module."""

import pytest

from agent_commons.guardrails import (
    check_empty_candidate_guardrail,
    check_hallucination_guardrail,
    is_empty_candidate_result,
    check_id_invention_guardrail,
    check_name_grounding_guardrail,
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


# ---------------------------------------------------------------------------
# Guardrail 3 — ID Invention detection
# ---------------------------------------------------------------------------

class TestCheckIdInventionGuardrail:
    def test_no_warning_when_id_is_valid(self):
        steps = [{"type": "call", "tool": "get_user", "args": {"user_id": 42}}]
        new_steps = check_id_invention_guardrail(steps)
        assert not any(s.get("tool") == "GUARDRAIL_ID_INVENTION" for s in new_steps)

    def test_warning_when_user_id_is_zero(self):
        steps = [{"type": "call", "tool": "get_user", "args": {"user_id": 0}}]
        new_steps = check_id_invention_guardrail(steps)
        assert any(s.get("tool") == "GUARDRAIL_ID_INVENTION" for s in new_steps)

    def test_warning_when_user_id_is_negative(self):
        steps = [{"type": "call", "tool": "get_user", "args": {"user_id": -1}}]
        new_steps = check_id_invention_guardrail(steps)
        assert any(s.get("tool") == "GUARDRAIL_ID_INVENTION" for s in new_steps)

    def test_warning_when_user_id_is_sentinel_string(self):
        steps = [{"type": "call", "tool": "get_user", "args": {"user_id": "user_1"}}]
        new_steps = check_id_invention_guardrail(steps)
        assert any(s.get("tool") == "GUARDRAIL_ID_INVENTION" for s in new_steps)

    def test_warning_when_user_id_is_null_string(self):
        steps = [{"type": "call", "tool": "get_user", "args": {"user_id": "null"}}]
        new_steps = check_id_invention_guardrail(steps)
        assert any(s.get("tool") == "GUARDRAIL_ID_INVENTION" for s in new_steps)

    def test_warning_on_mission_id(self):
        steps = [{"type": "call", "tool": "get_mission", "args": {"mission_id": 0}}]
        new_steps = check_id_invention_guardrail(steps)
        assert any(s.get("tool") == "GUARDRAIL_ID_INVENTION" for s in new_steps)

    def test_no_warning_on_non_id_args(self):
        """Arguments that are not entity IDs should never trigger the guardrail."""
        steps = [{"type": "call", "tool": "search_users", "args": {"query": "0 consultants Java"}}]
        new_steps = check_id_invention_guardrail(steps)
        assert not any(s.get("tool") == "GUARDRAIL_ID_INVENTION" for s in new_steps)

    def test_result_steps_are_ignored(self):
        steps = [{"type": "result", "data": {"user_id": 0}}]
        new_steps = check_id_invention_guardrail(steps)
        assert not any(s.get("tool") == "GUARDRAIL_ID_INVENTION" for s in new_steps)

    def test_caller_list_not_mutated(self):
        original = [{"type": "call", "tool": "get_user", "args": {"user_id": 0}}]
        original_len = len(original)
        _ = check_id_invention_guardrail(original)
        assert len(original) == original_len


# ---------------------------------------------------------------------------
# Guardrail 4 — Name grounding (warning only)
# ---------------------------------------------------------------------------

class TestCheckNameGroundingGuardrail:
    def _make_result_step(self, names: list[str]) -> dict:
        return {
            "type": "result",
            "data": [{"username": n} for n in names],
        }

    def test_no_warning_when_names_are_grounded(self):
        steps = [self._make_result_step(["Ahmed Kanoun", "Marie Dupont"])]
        steps.append({"type": "call", "tool": "search_users", "args": {}})
        response = "Ahmed Kanoun est disponible. Marie Dupont a un score de 0.85."
        _, new_steps = check_name_grounding_guardrail(response, steps)
        assert not any(s.get("tool") == "GUARDRAIL_NAME_GROUNDING" for s in new_steps)

    def test_warning_when_name_not_in_results(self):
        steps = [self._make_result_step(["Ahmed Kanoun"])]
        response = "Sophie Martin est experte Java. Ahmed Kanoun est disponible."
        _, new_steps = check_name_grounding_guardrail(response, steps)
        guardrail_steps = [s for s in new_steps if s.get("tool") == "GUARDRAIL_NAME_GROUNDING"]
        assert len(guardrail_steps) == 1
        assert "Sophie Martin" in guardrail_steps[0]["args"]["message"]

    def test_no_warning_when_no_tool_results(self):
        """Without tool results, the guardrail should not fire (G1 handles this)."""
        steps = [{"type": "call", "tool": "search_users", "args": {}}]
        response = "Sophie Martin est experte Java."
        _, new_steps = check_name_grounding_guardrail(response, steps)
        assert not any(s.get("tool") == "GUARDRAIL_NAME_GROUNDING" for s in new_steps)

    def test_known_entities_are_not_flagged(self):
        steps = [self._make_result_step(["Ahmed Kanoun"])]
        response = "Ahmed Kanoun maîtrise Kubernetes et Google Cloud. Spring Boot est utilisé."
        _, new_steps = check_name_grounding_guardrail(response, steps)
        assert not any(s.get("tool") == "GUARDRAIL_NAME_GROUNDING" for s in new_steps)

    def test_response_text_not_modified(self):
        """Guardrail 4 must never modify the response text."""
        steps = [self._make_result_step(["Ahmed Kanoun"])]
        response = "Sophie Martin est experte Java."
        new_response, _ = check_name_grounding_guardrail(response, steps)
        assert new_response == response

    def test_caller_steps_not_mutated(self):
        original = [self._make_result_step(["Ahmed Kanoun"])]
        original_len = len(original)
        response = "Sophie Martin est experte."
        _ = check_name_grounding_guardrail(response, original)
        assert len(original) == original_len
