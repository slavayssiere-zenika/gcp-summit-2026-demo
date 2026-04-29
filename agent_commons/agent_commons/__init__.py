"""
agent_commons — Shared ADK agent utilities for Zenika multi-agent platform.

Public modules:
  - mcp_client      : MCPHttpClient, MCPSseClient, auth_header_var
  - session         : RedisSessionService
  - metadata        : extract_metadata_from_session
  - mcp_proxy       : create_mcp_tool_proxy, get_cached_tools
  - runner          : run_agent_and_collect
  - guardrails      : check_hallucination_guardrail, check_empty_candidate_guardrail,
                      check_id_invention_guardrail, check_name_grounding_guardrail
  - finops          : log_tokens_to_bq
  - schemas         : QueryRequest, A2ARequest, A2AResponse, AgentStep, TokenUsage,
                      get_tool_metadata  [ADR12-4]
  - taxonomy_utils  : extract_mid_parents, extract_leaf_names, build_taxonomy_context
  - jwt_middleware  : verify_jwt_bearer, verify_jwt_request, ALGORITHM  [Zero-Trust §4]
  - exception_handler: report_exception_to_prompts_api, make_global_exception_handler
"""

__version__ = "1.1.0"
