"""
Tests for ADR12-4 — agent_commons.schemas Pydantic A2A contract.

Validates:
- A2ARequest: required fields, optional fields, min_length enforcement
- AgentStep: Literal type validation
- TokenUsage: non-negative constraints
- A2AResponse: response_model compatibility, default factories
- Round-trip: model_dump → model_validate
"""

import pytest
from pydantic import ValidationError

from agent_commons.schemas import A2ARequest, A2AResponse, AgentStep, TokenUsage


class TestA2ARequest:
    def test_minimal_valid(self):
        req = A2ARequest(query="Qui sont les consultants disponibles ?")
        assert req.query == "Qui sont les consultants disponibles ?"
        assert req.session_id is None
        assert req.user_id is None

    def test_full_valid(self):
        req = A2ARequest(
            query="Staffing mission Python",
            session_id="sess-abc123",
            user_id="alice@zenika.com",
        )
        assert req.session_id == "sess-abc123"
        assert req.user_id == "alice@zenika.com"

    def test_empty_query_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            A2ARequest(query="")
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("query",) for e in errors)

    def test_model_dump_excludes_none(self):
        req = A2ARequest(query="test")
        dumped = req.model_dump(exclude_none=True)
        assert "query" in dumped
        assert "session_id" not in dumped
        assert "user_id" not in dumped


class TestAgentStep:
    def test_call_step(self):
        step = AgentStep(type="call", tool="search_users", args={"skills": ["Python"]})
        assert step.type == "call"
        assert step.tool == "search_users"

    def test_result_step(self):
        step = AgentStep(type="result", data={"items": []})
        assert step.type == "result"
        assert step.data == {"items": []}

    def test_warning_step(self):
        step = AgentStep(type="warning", tool="hr_agent:GUARDRAIL", args={"message": "hallucination"})
        assert step.type == "warning"

    def test_cache_step(self):
        step = AgentStep(type="cache", tool="semantic_cache:HIT", args={"similarity_score": 0.97})
        assert step.type == "cache"

    def test_invalid_type_rejected(self):
        with pytest.raises(ValidationError):
            AgentStep(type="unknown_type")

    def test_source_field(self):
        step = AgentStep(type="call", tool="ask_hr", source="hr_agent")
        assert step.source == "hr_agent"


class TestTokenUsage:
    def test_defaults_are_zero(self):
        usage = TokenUsage()
        assert usage.total_input_tokens == 0
        assert usage.total_output_tokens == 0
        assert usage.estimated_cost_usd == 0.0

    def test_valid_values(self):
        usage = TokenUsage(total_input_tokens=100, total_output_tokens=80, estimated_cost_usd=0.000033)
        assert usage.total_input_tokens == 100

    def test_negative_tokens_rejected(self):
        with pytest.raises(ValidationError):
            TokenUsage(total_input_tokens=-1)

    def test_negative_cost_rejected(self):
        with pytest.raises(ValidationError):
            TokenUsage(estimated_cost_usd=-0.001)


class TestA2AResponse:
    def test_minimal_valid(self):
        resp = A2AResponse(response="Voici la liste.")
        assert resp.response == "Voici la liste."
        assert resp.steps == []
        assert resp.thoughts == ""
        assert resp.usage.total_input_tokens == 0

    def test_full_valid(self):
        resp = A2AResponse(
            response="J'ai trouvé 3 consultants.",
            data={"items": [{"id": 1}]},
            steps=[AgentStep(type="call", tool="search_users", args={})],
            thoughts="Let me think...",
            usage=TokenUsage(total_input_tokens=120, total_output_tokens=80),
            source="adk_agent",
        )
        assert len(resp.steps) == 1
        assert resp.usage.total_input_tokens == 120
        assert resp.source == "adk_agent"

    def test_steps_accept_dicts(self):
        """FastAPI/Pydantic doit accepter des dicts pour les steps (désérialisation JSON)."""
        resp = A2AResponse(
            response="Ok",
            steps=[{"type": "call", "tool": "get_mission", "args": {"id": "42"}}],
        )
        assert resp.steps[0].type == "call"
        assert resp.steps[0].tool == "get_mission"

    def test_round_trip_model_dump_validate(self):
        """model_dump() → model_validate() doit être un aller-retour parfait."""
        original = A2AResponse(
            response="Test round-trip",
            steps=[AgentStep(type="warning", tool="GUARDRAIL", args={"msg": "test"})],
            usage=TokenUsage(total_input_tokens=50, total_output_tokens=30),
            source="adk_agent",
        )
        dumped = original.model_dump()
        restored = A2AResponse.model_validate(dumped)
        assert restored.response == original.response
        assert restored.steps[0].type == "warning"
        assert restored.usage.total_input_tokens == 50

    def test_degraded_field(self):
        resp = A2AResponse(response="Service indisponible.", degraded=True)
        assert resp.degraded is True

    def test_semantic_cache_hit_field(self):
        resp = A2AResponse(response="Cached.", semantic_cache_hit=True, source="semantic_cache")
        assert resp.semantic_cache_hit is True
        assert resp.source == "semantic_cache"
