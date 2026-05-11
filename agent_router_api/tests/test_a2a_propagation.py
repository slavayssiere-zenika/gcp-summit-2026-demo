"""
Tests unitaires pour vérifier la bonne propagation des headers (JWT et OTel)
lors des appels sortants via l'A2aRequestInterceptor et _call_sub_agent.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import httpx
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

from a2a_tools import A2aRequestInterceptor, _call_sub_agent
from mcp_client import auth_header_var

trace.set_tracer_provider(TracerProvider())


def test_a2a_request_interceptor_injects_auth():
    """
    Vérifie que l'intercepteur lit bien auth_header_var et l'ajoute 
    aux headers de la requête httpx.
    """
    auth_token = "Bearer test_a2a_token"
    token = auth_header_var.set(auth_token)
    
    try:
        interceptor = A2aRequestInterceptor()
        
        # Simuler une requête httpx
        request = httpx.Request("POST", "http://fake_url")
        assert "Authorization" not in request.headers
        
        auth_val = auth_header_var.get(None)
        print("DEBUG auth_val:", auth_val)
        
        # Exécuter l'intercepteur (générateur)
        generator = interceptor.auth_flow(request)
        modified_request = next(generator)
        
        assert "Authorization" in modified_request.headers
        assert modified_request.headers["Authorization"] == "Bearer test_a2a_token"
        
    finally:
        auth_header_var.reset(token)


@pytest.mark.asyncio
async def test_call_sub_agent_propagates_traces():
    """
    Vérifie que la fonction _call_sub_agent() injecte bien le contexte OpenTelemetry
    (traceparent) dans les headers HTTP transmis au httpx.AsyncClient.
    """
    # On mock le httpx.AsyncClient pour intercepter les headers envoyés
    with patch("a2a_tools.httpx.AsyncClient") as mock_client_class:
        mock_instance = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "OK"}
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200
        mock_instance.post.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_instance
        
        tracer = trace.get_tracer(__name__)
        
        with tracer.start_as_current_span("test_a2a_span"):
            result = await _call_sub_agent(
                agent_name="test_agent",
                url="http://fake_sub_agent",
                query="Hello",
                user_id="user_123"
            )
            
            assert result == {"response": "OK"}
            
            # Vérifier l'instanciation du client
            assert mock_client_class.call_count == 1
            call_kwargs = mock_client_class.call_args[1]
            
            assert "headers" in call_kwargs
            headers_sent = call_kwargs["headers"]
            
            assert "traceparent" in headers_sent, "Le header traceparent n'a pas été injecté"
            assert "test_a2a_span" not in headers_sent["traceparent"]

