"""
Tests unitaires pour vérifier la bonne propagation du token d'authentification
vers le contexte asyncio interne (auth_header_var) dans le sous-agent.
"""

from agent_commons.mcp_client import auth_header_var
from agent import run_agent_query
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
import os
import sys
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")))


@pytest.mark.asyncio
async def test_run_agent_query_sets_auth_header_var():
    """
    Vérifie que run_agent_query affecte bien auth_header_var avec le auth_token
    fourni, ce qui garantit sa survie dans l'arbre d'exécution asynchrone (Runner).
    """
    token_to_inject = "Bearer super_secret_token"

    # On mock get_cached_tools pour éviter des appels HTTP externes inutiles
    # lors du create_agent() interne.
    with patch("agent.get_cached_tools", new_callable=AsyncMock) as mock_get_tools:
        mock_get_tools.return_value = []

        # On mock create_agent pour bypasser prompts_api
        with patch("agent.create_agent", new_callable=AsyncMock) as mock_create_agent:
            mock_agent = MagicMock()
            mock_agent.model = "test-model"
            mock_create_agent.return_value = mock_agent

            # On mock run_agent_and_collect pour inspecter l'état du contexte à l'instant T
            captured_auth = []

            async def fake_run_agent_and_collect(*args, **kwargs):
                # On capture la valeur de la ContextVar à l'instant où l'agent s'apprête à tourner
                captured_auth.append(auth_header_var.get(None))
                # Renvoie un tuple correspondant à la signature attendue par run_agent_query
                return ("Réponse test", [], [], 10, 20, None, "text_only")

            with patch("agent.run_agent_and_collect", new=fake_run_agent_and_collect):
                # On mock aussi la partie finops (log_tokens_to_bq)
                with patch("agent.log_tokens_to_bq"):
                    await run_agent_query(
                        query="test query",
                        session_id="test_session",
                        auth_token=token_to_inject,
                        user_id="user_test"
                    )

            assert len(captured_auth) == 1
            assert captured_auth[0] == token_to_inject, (
                "Le contexte auth_header_var n'a pas été défini "
                "correctement avant l'exécution du Runner ADK"
            )
