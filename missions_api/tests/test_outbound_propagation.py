"""
Tests unitaires pour vérifier la bonne propagation des headers (JWT et OTel)
lors des appels HTTP sortants effectués par le serveur MCP (ex: vers ses propres endpoints).
"""

import pytest
from unittest.mock import AsyncMock, patch

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

# Importation directe depuis mcp_server
from mcp_server import call_tool
from shared.auth.context import auth_header_var

trace.set_tracer_provider(TracerProvider())


@pytest.mark.asyncio
async def test_mcp_server_call_tool_propagates_headers():
    """
    Vérifie que call_tool() lit auth_header_var et utilise opentelemetry.propagate.inject
    pour populer le dictionnaire de headers avant de créer le httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0)).
    """
    auth_token = "Bearer test_token_mcp_server"
    token_id = auth_header_var.set(auth_token)

    # Mock global de httpx.AsyncClient
    with patch("mcp_server.httpx.AsyncClient") as mock_client_class:
        mock_instance = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_instance

        # On intercepte httpx.AsyncClient pour ne pas faire de vrai call
        # mock_instance a déjà été créé plus haut et assigné à la valeur de retour du context manager
        mock_post = AsyncMock()
        mock_instance.post = mock_post
        mock_post.return_value.json.return_value = {"id": 1}
        mock_post.return_value.raise_for_status = lambda: None

        tracer = trace.get_tracer(__name__)
        with tracer.start_as_current_span("test_mcp_tool_span"):
            await call_tool("create_mission", {"title": "Test", "description": "Desc"})

            # Vérifier les arguments d'appel de client.post (si l'implémentation passe les headers au .post)
            # ou à l'instanciation de httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0)) si passé au constructeur.
            # Dans missions_api, headers n'est pas passé au constructeur, il est passé au .post
            assert mock_post.call_count == 1
            call_kwargs = mock_post.call_args[1]

            assert "headers" in call_kwargs, "Le paramètre headers est manquant dans l'appel .post()"
            headers_sent = call_kwargs["headers"]

            # Vérification Auth
            assert "Authorization" in headers_sent
            assert headers_sent["Authorization"] == "Bearer test_token_mcp_server"

            # Vérification Tracing
            assert "traceparent" in headers_sent, "L'injection OpenTelemetry a échoué"
            assert "test_mcp_tool_span" not in headers_sent["traceparent"]

    auth_header_var.reset(token_id)
