"""
Tests unitaires pour vérifier la bonne propagation des headers (JWT et OTel)
lors des appels sortants via MCPHttpClient.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

from agent_commons.mcp_client import MCPHttpClient, auth_header_var

# Simuler un provider de trace basique pour l'injection
trace.set_tracer_provider(TracerProvider())


@pytest.fixture
def mock_httpx_client():
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_instance = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_instance
        yield mock_client_class, mock_instance


@pytest.mark.asyncio
async def test_mcp_http_client_propagates_auth_and_trace(mock_httpx_client):
    """
    Vérifie que call_tool extrait bien auth_header_var et inject() les traces
    et passe le tout au constructeur de httpx.AsyncClient(headers=...)
    """
    mock_class, mock_instance = mock_httpx_client

    # Mock de la réponse de l'API MCP
    mock_response = MagicMock()
    mock_response.status_code = 200  # http_call_with_retry inspecte status_code
    mock_response.json.return_value = {"result": [{"text": "success", "type": "text"}]}
    mock_response.raise_for_status = MagicMock()
    mock_instance.post.return_value = mock_response

    client = MCPHttpClient("http://fake_mcp:8000")

    # 1. Simuler l'injection d'un token JWT dans le contexte (effectuée par les routeurs)
    auth_token = "Bearer test_token_123"
    token_token = auth_header_var.set(auth_token)

    # 2. Simuler un contexte de trace OpenTelemetry
    tracer = trace.get_tracer(__name__)

    try:
        with tracer.start_as_current_span("test_span"):
            # L'appel à la fonction
            result = await client.call_tool("my_tool", {"arg": "value"})

            # Vérifications
            assert result == [{"text": "success", "type": "text"}]

            # Vérifier les arguments d'instanciation de httpx.AsyncClient
            assert mock_class.call_count == 1
            call_kwargs = mock_class.call_args[1]
            assert "headers" in call_kwargs, "Le paramètre headers est manquant"
            headers_sent = call_kwargs["headers"]

            # A) Vérification Auth
            assert "Authorization" in headers_sent
            assert headers_sent["Authorization"] == "Bearer test_token_123"

            # B) Vérification Tracing (opentelemetry.propagate.inject ajoute traceparent)
            assert "traceparent" in headers_sent, "L'injection OpenTelemetry a échoué"
            assert "test_span" not in headers_sent["traceparent"]  # traceparent formaté

    finally:
        auth_header_var.reset(token_token)


@pytest.mark.asyncio
async def test_mcp_http_client_works_without_auth(mock_httpx_client):
    """
    Vérifie que l'absence de JWT ne fait pas crasher le client et que les traces passent quand même.
    """
    mock_class, mock_instance = mock_httpx_client

    mock_response = MagicMock()
    mock_response.status_code = 200  # http_call_with_retry inspecte status_code
    mock_response.json.return_value = {"result": [{"text": "success", "type": "text"}]}
    mock_response.raise_for_status = MagicMock()
    mock_instance.post.return_value = mock_response

    client = MCPHttpClient("http://fake_mcp:8000")

    # On s'assure qu'aucun token n'est set
    assert auth_header_var.get(None) is None

    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("test_span_no_auth"):
        await client.call_tool("my_tool", {})

        call_kwargs = mock_class.call_args[1]
        headers_sent = call_kwargs.get("headers", {})

        assert "Authorization" not in headers_sent
        assert "traceparent" in headers_sent
