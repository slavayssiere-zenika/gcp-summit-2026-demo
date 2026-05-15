"""
test_schemas_agent_response.py — Tests unitaires du contrat AgentQueryResponse.

Valide que le schéma Pydantic est correctement défini et que les
migrations de champs (breaking changes) sont détectées immédiatement.
"""

import pytest
from pydantic import ValidationError

from agent_commons.schemas import (
    AgentQueryResponse,
    AgentStep,
    TokenUsage,
)


class TestAgentStep:
    """Tests de validation du modèle AgentStep."""

    def test_minimal_step(self):
        """Un step minimal avec juste le type est valide."""
        step = AgentStep(type="call")
        assert step.type == "call"
        assert step.tool is None
        assert step.args is None
        assert step.data is None
        assert step.source is None

    def test_full_step(self):
        """Un step complet avec tous les champs."""
        step = AgentStep(
            type="call",
            tool="ask_hr_agent",
            args={"query": "Qui est disponible ?"},
            data={"items": []},
            source="hr_agent",
        )
        assert step.tool == "ask_hr_agent"
        assert step.args == {"query": "Qui est disponible ?"}
        assert step.source == "hr_agent"

    @pytest.mark.parametrize("step_type", ["call", "result", "warning", "cache"])
    def test_valid_step_types(self, step_type: str):
        """Tous les types de steps littéraux sont acceptés."""
        step = AgentStep(type=step_type)
        assert step.type == step_type


class TestTokenUsage:
    """Tests de validation du modèle TokenUsage."""

    def test_default_values(self):
        """Les valeurs par défaut sont toutes à zéro."""
        usage = TokenUsage()
        assert usage.total_input_tokens == 0
        assert usage.total_output_tokens == 0
        assert usage.estimated_cost_usd == 0.0

    def test_valid_usage(self):
        """Un usage avec des valeurs réalistes."""
        usage = TokenUsage(
            total_input_tokens=1500,
            total_output_tokens=300,
            estimated_cost_usd=0.000203,
        )
        assert usage.total_input_tokens == 1500
        assert usage.total_output_tokens == 300
        assert usage.estimated_cost_usd == pytest.approx(0.000203)


class TestAgentQueryResponse:
    """Tests de validation du contrat AgentQueryResponse."""

    def _minimal_response(self) -> dict:
        """Payload minimal valide pour AgentQueryResponse."""
        return {"response": "Voici les résultats."}

    def test_minimal_payload(self):
        """Un payload avec juste 'response' est valide (tous les autres ont des defaults)."""
        r = AgentQueryResponse(**self._minimal_response())
        assert r.response == "Voici les résultats."
        assert r.thoughts == ""
        assert r.data is None
        assert r.display_type is None
        assert r.steps == []
        assert r.source == "adk_agent"
        assert r.session_id is None
        assert r.confidence is None
        assert r.semantic_cache_hit is None
        assert r.degraded is None
        assert r.usage.total_input_tokens == 0

    def test_full_payload(self):
        """Un payload complet avec tous les champs est accepté."""
        payload = {
            "response": "J'ai trouvé 3 consultants.",
            "thoughts": "Je dois chercher les profils...",
            "data": {"items": [{"id": 1, "name": "Alice"}]},
            "display_type": "consultants",
            "steps": [{"type": "call", "tool": "ask_hr_agent", "args": {}}],
            "source": "adk_agent",
            "session_id": "alice@zenika.com",
            "usage": {
                "total_input_tokens": 800,
                "total_output_tokens": 200,
                "estimated_cost_usd": 0.00012,
            },
            "confidence": 0.9,
            "semantic_cache_hit": False,
            "degraded": False,
        }
        r = AgentQueryResponse(**payload)
        assert r.response == "J'ai trouvé 3 consultants."
        assert r.display_type == "consultants"
        assert r.confidence == 0.9
        assert r.semantic_cache_hit is False
        assert r.degraded is False
        assert len(r.steps) == 1
        assert r.steps[0].tool == "ask_hr_agent"

    def test_response_required(self):
        """Le champ 'response' est obligatoire — ValidationError si absent."""
        with pytest.raises(ValidationError) as exc_info:
            AgentQueryResponse()  # type: ignore[call-arg]
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("response",) for e in errors)

    def test_confidence_bounds(self):
        """Le score de confiance doit être entre 0.0 et 1.0."""
        # Valide à 0.0 et 1.0
        AgentQueryResponse(response="ok", confidence=0.0)
        AgentQueryResponse(response="ok", confidence=1.0)
        AgentQueryResponse(response="ok", confidence=0.75)

        # Invalide au-dessus de 1.0
        with pytest.raises(ValidationError):
            AgentQueryResponse(response="ok", confidence=1.1)

        # Invalide en-dessous de 0.0
        with pytest.raises(ValidationError):
            AgentQueryResponse(response="ok", confidence=-0.1)

    def test_model_dump_roundtrip(self):
        """model_dump() produit un dict compatible avec model_validate()."""
        original = AgentQueryResponse(
            response="Test",
            thoughts="Pensées",
            steps=[AgentStep(type="call", tool="search_users")],
            usage=TokenUsage(total_input_tokens=100, total_output_tokens=50),
            confidence=1.0,
            session_id="user@zenika.com",
        )
        dumped = original.model_dump()
        reconstructed = AgentQueryResponse.model_validate(dumped)
        assert reconstructed.response == original.response
        assert reconstructed.confidence == original.confidence
        assert len(reconstructed.steps) == 1
        assert reconstructed.steps[0].tool == "search_users"

    def test_degraded_response(self):
        """Un payload de mode dégradé (circuit-breaker) est accepté."""
        r = AgentQueryResponse(
            response="❌ Le sous-agent est temporairement indisponible.",
            degraded=True,
            source="error",
        )
        assert r.degraded is True
        assert r.source == "error"

    def test_semantic_cache_response(self):
        """Un payload de cache sémantique est correctement typé."""
        r = AgentQueryResponse(
            response="Réponse depuis le cache.",
            source="semantic_cache",
            semantic_cache_hit=True,
        )
        assert r.semantic_cache_hit is True
        assert r.source == "semantic_cache"

    def test_steps_are_typed(self):
        """Les steps passés en dict sont convertis en AgentStep."""
        r = AgentQueryResponse(
            response="ok",
            steps=[
                {"type": "call", "tool": "ask_hr_agent"},
                {"type": "warning", "tool": "GUARDRAIL_HALLUCINATION"},
            ],
        )
        assert all(isinstance(s, AgentStep) for s in r.steps)
        assert r.steps[0].type == "call"
        assert r.steps[1].type == "warning"
