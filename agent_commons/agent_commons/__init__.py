"""
agent_commons — Shared ADK agent utilities for Zenika multi-agent platform.

Public modules:
  - mcp_client   : MCPHttpClient, MCPSseClient, auth_header_var
  - session      : RedisSessionService
  - metadata     : extract_metadata_from_session
  - mcp_proxy    : create_mcp_tool_proxy, get_cached_tools
  - runner       : run_agent_and_collect
  - guardrails   : check_hallucination_guardrail, check_empty_candidate_guardrail
  - finops       : log_tokens_to_bq
  - schemas      : A2ARequest, A2AResponse, AgentStep, TokenUsage  [ADR12-4]
"""

__version__ = "1.0.0"
