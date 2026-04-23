"""
agent_hr_api/agent.py — HR Agent (Staffing & Compétences) ADK implementation.

Ce fichier configure l'agent ADK spécialisé Ressources Humaines.
Toute la logique commune (proxy MCP, boucle runner, guardrails, FinOps,
session Redis) est importée depuis le package `agent_commons`.
"""

import os
import uuid
import logging

import httpx
from google.genai import types
from google.adk.agents import Agent
from google.adk.runners import Runner

from agent_commons.mcp_client import MCPHttpClient, auth_header_var
from agent_commons.session import RedisSessionService
from agent_commons.metadata import extract_metadata_from_session
from agent_commons.mcp_proxy import get_cached_tools
from agent_commons.runner import run_agent_and_collect
from agent_commons.guardrails import (
    check_hallucination_guardrail,
    check_empty_candidate_guardrail,
    is_empty_candidate_result,
)
from agent_commons.finops import log_tokens_to_bq, estimate_cost_usd

app_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Outils de recherche de candidats surveillés par le guardrail COM-006.
# Si l'un de ces outils retourne une liste vide, l'agent NE DOIT PAS
# produire de profils inventés.
# ---------------------------------------------------------------------------
CANDIDATE_SEARCH_TOOLS: set[str] = {
    "search_best_candidates",
    "search_users",
    "list_users",
    "get_users_by_tag",
}

# ---------------------------------------------------------------------------
# MCP Clients — URLs propres à l'agent HR
# ---------------------------------------------------------------------------
USERS_MCP_URL = os.getenv("USERS_MCP_URL", "http://users_mcp:8000")
ITEMS_MCP_URL = os.getenv("ITEMS_MCP_URL", "http://items_mcp:8000")
COMPETENCIES_MCP_URL = os.getenv("COMPETENCIES_MCP_URL", "http://competencies_mcp:8000")
CV_MCP_URL = os.getenv("CV_MCP_URL", "http://cv_mcp:8000")
MISSIONS_MCP_URL = os.getenv("MISSIONS_MCP_URL", "http://missions_mcp:8000")

users_client = MCPHttpClient(USERS_MCP_URL)
items_client = MCPHttpClient(ITEMS_MCP_URL)
comp_client = MCPHttpClient(COMPETENCIES_MCP_URL)
cv_client = MCPHttpClient(CV_MCP_URL)
missions_client = MCPHttpClient(MISSIONS_MCP_URL)

_HR_CLIENTS_MAP = [
    ("users_mcp", users_client),
    ("items_mcp", items_client),
    ("competencies_mcp", comp_client),
    ("cv_mcp", cv_client),
    ("missions_mcp", missions_client),
]

# Cache isolé pour cet agent (mutable dict utilisé comme cache par get_cached_tools)
_HR_TOOLS_CACHE: dict = {}

# Public reference — exposée dans main.py pour /mcp/registry
HR_TOOLS: list = []

# ---------------------------------------------------------------------------
# Session service (lazy init)
# ---------------------------------------------------------------------------
_session_service = None


def get_session_service() -> RedisSessionService:
    global _session_service
    if _session_service is None:
        _session_service = RedisSessionService(redis_key_prefix="adk:hr:sessions")
    return _session_service


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------
async def create_agent(session_id: str | None = None) -> Agent:
    global HR_TOOLS
    prompts_api_url = os.getenv("PROMPTS_API_URL", "http://prompts_api:8000")
    instruction_text = (
        "Tu es l'Agent RH (Staffing & Compétences) de la plateforme Zenika. "
        "Tu détiens l'expertise des utilisateurs, des items et missions."
    )
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(f"{prompts_api_url}/prompts/agent_hr_api.system_instruction/compiled")
            if res.status_code == 200:
                instruction_text = res.json()["value"]
            else:
                instruction_text += "\n[Fallback Instruction]"
    except Exception as e:
        app_logger.warning("Error fetching system prompt for HR: %s", e)

    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    tools_loaded = await get_cached_tools(_HR_CLIENTS_MAP, "[HR]", ttl=300, _cache=_HR_TOOLS_CACHE)
    HR_TOOLS = tools_loaded

    if not HR_TOOLS:
        app_logger.error(
            "[HR] 🚨 CRITICAL: 0 MCP tools loaded! Agent will have no tools and will HALLUCINATE. "
            "Check MCP service connectivity."
        )
    else:
        app_logger.info("[HR] Creating Agent with %d tools...", len(HR_TOOLS))

    agent = Agent(
        name="assistant_zenika_hr",
        model=model,
        generate_content_config=types.GenerateContentConfig(
            http_options=types.HttpOptions(
                retry_options=types.HttpRetryOptions(initial_delay=1, attempts=2),
            ),
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode="AUTO")
            ),
        ),
        instruction=instruction_text,
        description="Le module spécialisé dans les ressources humaines et le staffing.",
        tools=HR_TOOLS,
    )
    app_logger.info("[HR] Agent created successfully with %d tools.", len(HR_TOOLS))
    return agent


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
async def run_agent_query(
    query: str,
    session_id: str | None = None,
    user_id: str = "user_1",
) -> dict:
    # Session éphémère par requête — évite la contamination de contexte.
    # La persistance conversationnelle est gérée par Redis côté agent_router_api.
    ephemeral_session_id = str(uuid.uuid4())
    session_service = get_session_service()

    app_logger.info("[HR] Initializing Agent and Runner (session: %s)...", ephemeral_session_id[:8])
    agent = await create_agent(ephemeral_session_id)
    runner = Runner(app_name="zenika_hr_assistant", agent=agent, session_service=session_service)
    await session_service.create_session(
        app_name="zenika_hr_assistant", user_id=user_id, session_id=ephemeral_session_id
    )

    # COM-006 : accumule les résultats des outils de recherche de candidats
    candidate_search_results: list[dict] = []

    # Run the ADK loop
    response_text, steps, thoughts, total_input_tokens, total_output_tokens, last_tool_data = (
        await run_agent_and_collect(runner, user_id, ephemeral_session_id, query, "hr", "[HR]")
    )

    # Collect COM-006 candidate search results from steps
    for i, s in enumerate(steps):
        if s.get("type") == "call" and s.get("tool") in CANDIDATE_SEARCH_TOOLS:
            # Find the next result step
            for s2 in steps[i + 1:]:
                if s2.get("type") == "result":
                    candidate_search_results.append({"tool": s["tool"], "result": s2["data"]})
                    break

    # --- Foolproof metadata reconstruction from Redis session ---
    try:
        updated_session = await session_service.get_session(
            app_name="zenika_hr_assistant", user_id=user_id, session_id=ephemeral_session_id
        )
        if updated_session:
            meta = extract_metadata_from_session(updated_session)
            steps = meta.get("steps", [])
            thoughts = [meta.get("thoughts", "")] if meta.get("thoughts") else []
            last_tool_data = meta.get("data")
            app_logger.info("[HR] Post-processed metadata: %d steps.", len(steps))
    except Exception as e:
        app_logger.error("[HR] Error in metadata post-processing: %s", e)

    # --- FinOps async logging ---
    log_tokens_to_bq(
        session_id=session_id,
        action="hr_agent_execution",
        model=agent.model,
        input_tokens=total_input_tokens,
        output_tokens=total_output_tokens,
        query=query,
        auth_header=auth_header_var.get(),
    )

    # --- Guardrail 1 : zéro appel d'outil ---
    response_text, steps = check_hallucination_guardrail(response_text, steps, "[HR]")

    # --- Guardrail 2 : COM-006 résultats vides ---
    response_text, steps, last_tool_data_override = check_empty_candidate_guardrail(
        candidate_search_results, response_text, steps, "[HR]"
    )
    if last_tool_data_override is None and candidate_search_results and all(
        is_empty_candidate_result(r["result"]) for r in candidate_search_results
    ):
        last_tool_data = None
    elif last_tool_data_override is not None:
        last_tool_data = last_tool_data_override

    return {
        "response": response_text,
        "data": last_tool_data,
        "steps": steps,
        "thoughts": "\n".join(thoughts),
        "usage": {
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "estimated_cost_usd": estimate_cost_usd(total_input_tokens, total_output_tokens),
        },
    }
