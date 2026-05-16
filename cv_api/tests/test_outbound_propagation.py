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

        # On intercepte handle_analyze_cv pour ne pas tester la logique métier,
        # mais juste garantir que le dictionnaire de headers a été construit correctement.
        with patch("mcp_server.handle_analyze_cv", new_callable=AsyncMock) as mock_handle:
            mock_handle.return_value = []

            tracer = trace.get_tracer(__name__)
            with tracer.start_as_current_span("test_mcp_tool_span"):
                await call_tool("analyze_cv", {"url": "http://test"})

                # Vérifier les arguments d'appel de handle_analyze_cv
                assert mock_handle.call_count == 1
                call_args = mock_handle.call_args[0]

                # handle_analyze_cv(client, arguments, headers, API_BASE_URL)
                assert len(
                    call_args) >= 3, "handle_analyze_cv doit recevoir les headers"
                headers_sent = call_args[2]

                # Vérification Auth
                assert "Authorization" in headers_sent
                assert headers_sent["Authorization"] == "Bearer test_token_mcp_server"

                # Vérification Tracing
                assert "traceparent" in headers_sent, "L'injection OpenTelemetry a échoué"
                assert "test_mcp_tool_span" not in headers_sent["traceparent"]

    auth_header_var.reset(token_id)
