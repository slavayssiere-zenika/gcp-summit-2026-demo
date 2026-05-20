"""
Tests unitaires pour le Guardrail de Niveau 0 (Pre-Generation Interception).

Vérifie la détection et l'interception immédiate des identifiants inventés
ou erronés dans les clients MCP HTTP et SSE.
"""

import pytest
from unittest.mock import patch

from agent_commons.mcp_client import (
    MCPHttpClient,
    MCPSseClient,
    InvalidToolArgumentError,
    validate_tool_arguments,
)


def test_validate_tool_arguments_success():
    """Vérifie que la validation réussit avec des arguments valides."""
    # Des identifiants valides ne doivent pas lever d'erreur
    validate_tool_arguments("search_users", {"user_id": 42})
    validate_tool_arguments("get_user", {"id": "user-uuid-1234-5678"})
    validate_tool_arguments("list_missions", {"mission_id": "mission-45"})
    validate_tool_arguments("update_competency", {"competency_id": "python-expert"})

    # Des arguments non identifiants peuvent avoir n'importe quelle valeur
    validate_tool_arguments("search_users", {"query": "user_1"})
    validate_tool_arguments("search_users", {"limit": 0})
    validate_tool_arguments("search_users", {"score": -1})
    validate_tool_arguments("search_users", {"active": "null"})


def test_validate_tool_arguments_failure():
    """Vérifie que la validation échoue avec des arguments suspects ou fictifs."""
    suspicious_cases = [
        # Clés d'ID avec des valeurs de sentinelle suspectes
        ("user_id", "user_1"),
        ("user_id", "user1"),
        ("id", "null"),
        ("mission_id", "none"),
        ("candidate_id", "unknown"),
        ("competency_id", "123"),
        ("item_id", "999"),
        ("folder_id", "9999"),
        ("agent_id", "id"),
        ("user_id", "<id>"),
        ("user_id", "<user_id>"),
        # Clés d'ID avec des entiers <= 0
        ("user_id", 0),
        ("user_id", -1),
        ("user_id", -999),
        # Clés d'ID sous forme de chaînes numériques <= 0
        ("id", "0"),
        ("id", "-1"),
        ("id", " -5  "),  # Espaces superflus
        # Casse et espaces
        ("USER_ID", " USER_1 "),
        ("Id", "  NULL  "),
    ]

    for key, value in suspicious_cases:
        with pytest.raises(InvalidToolArgumentError) as exc_info:
            validate_tool_arguments("my_tool", {key: value})

        # Le message d'erreur doit être clair et en français
        err_msg = str(exc_info.value)
        assert f"L'identifiant '{value}' fourni pour le paramètre '{key}'" in err_msg
        assert "interception Guardrail de Niveau 0" in err_msg
        assert "Veuillez utiliser un outil de recherche approprié" in err_msg


@pytest.mark.asyncio
async def test_mcp_http_client_intercepts_invalid_args():
    """Vérifie que MCPHttpClient intercepte l'appel avant de faire la requête réseau."""
    client = MCPHttpClient("http://fake_mcp:8000")

    # Si la validation n'intercepte pas, cela ferait un appel httpx (non mocké ici) et lèverait une autre erreur.
    # Ici, l'exception InvalidToolArgumentError doit être levée immédiatement.
    with patch("httpx.AsyncClient") as mock_client_class:
        with pytest.raises(InvalidToolArgumentError):
            await client.call_tool("search_users", {"user_id": "user_1"})

        # Le mock d'AsyncClient ne doit jamais avoir été appelé
        assert mock_client_class.call_count == 0


@pytest.mark.asyncio
async def test_mcp_sse_client_intercepts_invalid_args():
    """Vérifie que MCPSseClient intercepte l'appel avant d'initialiser la session SSE."""
    client = MCPSseClient("http://fake_mcp:8000")

    with patch("mcp.client.sse.sse_client") as mock_sse_client:
        with pytest.raises(InvalidToolArgumentError):
            await client.call_tool("get_mission", {"mission_id": 0})

        assert mock_sse_client.call_count == 0
