"""
agent_commons — Shared ADK agent utilities for Zenika multi-agent platform.

Public modules:
  - mcp_client      : MCPHttpClient, MCPSseClient, auth_header_var
  - circuit_breaker : CircuitBreaker, CircuitOpenError, get_circuit_breaker
  - session         : RedisSessionService
  - metadata        : extract_metadata_from_session
  - mcp_proxy       : create_mcp_tool_proxy, get_cached_tools
  - runner          : run_agent_and_collect
  - guardrails      : check_hallucination_guardrail, check_empty_candidate_guardrail,
                      check_id_invention_guardrail, check_name_grounding_guardrail
  - finops          : log_tokens_to_bq
  - schemas         : QueryRequest, A2ARequest, A2AResponse, AgentQueryResponse,
                       AgentStep, TokenUsage, get_tool_metadata  [ADR12-4]
  - http_resilience : http_call_with_retry, build_retry_after_headers,
                       RetryExhaustedError, is_retryable_status  [Résilience §12]
  - taxonomy_utils  : extract_mid_parents, extract_leaf_names, build_taxonomy_context
  - jwt_middleware  : verify_jwt_bearer, verify_jwt_request, ALGORITHM  [Zero-Trust §4]
  - exception_handler: report_exception_to_prompts_api, make_global_exception_handler
"""

__version__ = "1.1.0"


# Monkeypatch google-genai Client to respect GEMINI_API_BASE_URL and VERTEX_API_BASE_URL
try:
    import os
    import logging
    from google import genai
    from google.genai import types

    logger = logging.getLogger("agent_commons.gemini_mock")
    _original_init = genai.Client.__init__

    def _patched_init(self, *args, **kwargs):
        gemini_base = os.getenv("GEMINI_API_BASE_URL")
        vertex_base = os.getenv("VERTEX_API_BASE_URL")

        # In google-genai SDK, vertexai can be passed as vertexai=True or as the first positional argument
        is_vertex = kwargs.get("vertexai") or (len(args) > 0 and args[0] is True)
        base_url = vertex_base if (is_vertex and vertex_base) else gemini_base

        # Zero-Trust Production Guardrail (bypasses local mocks in GCP environments)
        if base_url:
            is_gcp_run = os.getenv("K_SERVICE") is not None
            is_local_mock = any(mock in base_url for mock in ["mock_gemini", "localhost", "127.0.0.1"])
            if is_gcp_run and is_local_mock:
                logger.warning(
                    "[gemini_mock] ALERTE SECURITE : tentative de redirection vers un mock local (%s) "
                    "ignoree en production GCP.", base_url
                )
                base_url = None

        if base_url:
            http_opts = kwargs.get("http_options")
            if not http_opts:
                http_opts = types.HttpOptions()
            elif isinstance(http_opts, dict):
                http_opts = types.HttpOptions(**http_opts)
            http_opts.baseUrl = base_url
            kwargs["http_options"] = http_opts

            if not is_vertex and not kwargs.get("api_key"):
                kwargs["api_key"] = "mock-key-local"

        _original_init(self, *args, **kwargs)

    genai.Client.__init__ = _patched_init
except ImportError:
    pass
