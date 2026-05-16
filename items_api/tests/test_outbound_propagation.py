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

        # On intercepte handle_categories_tool pour ne pas tester la logique métier.
        with patch("mcp_server.handle_categories_tool", new_callable=AsyncMock) as mock_handle:
            mock_handle.return_value = [{"text": "OK", "type": "text"}]

            tracer = trace.get_tracer(__name__)
            with tracer.start_as_current_span("test_mcp_tool_span"):
                await call_tool("some_tool", {"arg": "val"})

                # Vérifier les arguments d'instanciation de httpx.AsyncClient
                assert mock_client_class.call_count == 1
                call_kwargs = mock_client_class.call_args[1]

                assert "headers" in call_kwargs, "Le paramètre headers est manquant dans AsyncClient()"
                headers_sent = call_kwargs["headers"]

                # Vérification Auth
                assert "Authorization" in headers_sent
                assert headers_sent["Authorization"] == "Bearer test_token_mcp_server"

                # Vérification Tracing
                assert "traceparent" in headers_sent, "L'injection OpenTelemetry a échoué"
                assert "test_mcp_tool_span" not in headers_sent["traceparent"]

    auth_header_var.reset(token_id)
