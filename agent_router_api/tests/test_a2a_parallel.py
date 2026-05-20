"""
Tests unitaires pour valider la parallélisation A2A via ask_mixed_agents.
"""
import json
from unittest.mock import AsyncMock, patch
import pytest


@pytest.mark.asyncio
async def test_ask_mixed_agents_both_success():
    """Vérifie le fonctionnement nominal de ask_mixed_agents quand les deux agents répondent."""
    hr_response = {
        "result": json.dumps({
            "agent": "hr_agent",
            "response": "Réponse RH : Dev Python trouvé.",
            "thoughts": "Raisonnement RH...",
            "confidence": 0.9,
        })
    }
    ops_response = {
        "result": json.dumps({
            "agent": "ops_agent",
            "response": "Réponse Ops : Mission BNP active.",
            "thoughts": "Raisonnement Ops...",
            "confidence": 0.8,
        })
    }

    with patch("a2a_tools.ask_hr_agent", new=AsyncMock(return_value=hr_response)) as mock_hr, \
         patch("a2a_tools.ask_ops_agent", new=AsyncMock(return_value=ops_response)) as mock_ops:

        from a2a_tools import ask_mixed_agents
        result = await ask_mixed_agents("Trouve un dev Python et vérifie BNP", user_id="user_test")

        # Vérification des appels
        mock_hr.assert_called_once_with("Trouve un dev Python et vérifie BNP", "user_test")
        mock_ops.assert_called_once_with("Trouve un dev Python et vérifie BNP", "user_test")

        # Vérification du résultat combiné
        parsed = json.loads(result["result"])
        assert parsed["agent"] == "mixed_agents"
        assert "Réponse RH : Dev Python trouvé." in parsed["response"]
        assert "Réponse Ops : Mission BNP active." in parsed["response"]
        assert "[HR] Raisonnement RH..." in parsed["thoughts"]
        assert "[Ops] Raisonnement Ops..." in parsed["thoughts"]
        assert parsed["confidence"] == 0.85  # (0.9 + 0.8) / 2


@pytest.mark.asyncio
async def test_ask_mixed_agents_one_failure():
    """Vérifie le fonctionnement de ask_mixed_agents quand un agent lève une exception."""
    hr_response = {
        "result": json.dumps({
            "agent": "hr_agent",
            "response": "Réponse RH : Alice disponible.",
            "thoughts": "Raisonnement RH...",
            "confidence": 1.0,
        })
    }

    with patch("a2a_tools.ask_hr_agent", new=AsyncMock(return_value=hr_response)) as mock_hr, \
         patch("a2a_tools.ask_ops_agent", new=AsyncMock(side_effect=Exception("Timeout Connection"))) as mock_ops:

        from a2a_tools import ask_mixed_agents
        result = await ask_mixed_agents("Alice BNP", user_id="user_test")

        mock_hr.assert_called_once()
        mock_ops.assert_called_once()

        parsed = json.loads(result["result"])
        assert parsed["agent"] == "mixed_agents"
        assert "Réponse RH : Alice disponible." in parsed["response"]
        assert "❌ Erreur lors de l'appel à l'agent Ops" in parsed["response"]
        assert parsed["confidence"] == 0.5  # (1.0 + 0.0) / 2
