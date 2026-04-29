"""
agent_missions_api/agent.py — Missions Agent (Staffing Director) ADK implementation.

Ce fichier configure l'agent ADK spécialisé Missions & Staffing.
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
    check_id_invention_guardrail,
)
from agent_commons.finops import log_tokens_to_bq, estimate_cost_usd

app_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MCP Clients — l'agent Missions n'a besoin que de ces 4 MCPs :
#   missions_mcp : CRUD missions
#   cv_mcp       : search_best_candidates, get_candidate_rag_context
#   users_mcp    : profil consultant (nom, email, agence)
#   competencies_mcp : taxonomie des compétences (matching)
# Les MCP items et drive ne sont pas nécessaires pour le Staffing Director.
# ---------------------------------------------------------------------------
MISSIONS_MCP_URL = os.getenv("MISSIONS_MCP_URL", "http://missions_mcp:8000")
CV_MCP_URL = os.getenv("CV_MCP_URL", "http://cv_mcp:8000")
USERS_MCP_URL = os.getenv("USERS_MCP_URL", "http://users_mcp:8000")
COMPETENCIES_MCP_URL = os.getenv("COMPETENCIES_MCP_URL", "http://competencies_mcp:8000")

missions_client = MCPHttpClient(MISSIONS_MCP_URL)
cv_client = MCPHttpClient(CV_MCP_URL)
users_client = MCPHttpClient(USERS_MCP_URL)
comp_client = MCPHttpClient(COMPETENCIES_MCP_URL)

_MISSIONS_CLIENTS_MAP = [
    ("missions_mcp", missions_client),
    ("cv_mcp", cv_client),
    ("users_mcp", users_client),
    ("competencies_mcp", comp_client),
]

# Cache isolé pour cet agent
_MISSIONS_TOOLS_CACHE: dict = {}

# Public reference
MISSIONS_TOOLS: list = []

# ---------------------------------------------------------------------------
# Session service (lazy init) — préfixe Redis distinct des autres agents
# ---------------------------------------------------------------------------
_session_service = None


def get_session_service() -> RedisSessionService:
    global _session_service
    if _session_service is None:
        _session_service = RedisSessionService(
            redis_key_prefix="adk:missions:sessions",
            # DB 12 — distinct de HR (10), Ops (11), Router (9)
            redis_url=os.getenv("REDIS_URL", "redis://redis:6379/12"),
        )
    return _session_service


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------
async def create_agent(session_id: str | None = None) -> Agent:
    global MISSIONS_TOOLS
    prompts_api_url = os.getenv("PROMPTS_API_URL", "http://prompts_api:8000")
    instruction_text = (
        "Tu es l'Agent Missions (Staffing Director) de la plateforme Zenika. "
        "Tu es spécialisé dans la gestion des missions client et le staffing des consultants."
    )
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(f"{prompts_api_url.rstrip('/')}/agent_missions_api.system_instruction/compiled")
            if res.status_code == 200:
                instruction_text = res.json()["value"]
            else:
                instruction_text += "\n[Fallback Instruction]"
    except Exception as e:
        app_logger.warning("[MISSIONS] Error fetching system prompt: %s", e)

    # AGENTS.md §1.4 : variable dédiée per-agent. GEMINI_MODEL est le fallback legacy.
    model = os.getenv("GEMINI_MISSIONS_MODEL", os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview"))
    tools_loaded = await get_cached_tools(_MISSIONS_CLIENTS_MAP, "[MISSIONS]", ttl=300, _cache=_MISSIONS_TOOLS_CACHE)
    MISSIONS_TOOLS = tools_loaded

    if not MISSIONS_TOOLS:
        app_logger.error(
            "[MISSIONS] 🚨 CRITICAL: 0 MCP tools loaded! "
            "Agent will have no tools and will HALLUCINATE. Check MCP service connectivity."
        )
    else:
        app_logger.info("[MISSIONS] Creating Agent with %d tools...", len(MISSIONS_TOOLS))

    agent = Agent(
        name="assistant_zenika_missions",
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
        description="Le module spécialisé dans la gestion des missions client et le staffing de consultants.",
        tools=MISSIONS_TOOLS,
    )
    app_logger.info("[MISSIONS] Agent created successfully with %d tools.", len(MISSIONS_TOOLS))
    return agent


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
async def run_agent_query(
    query: str,
    session_id: str | None = None,
    user_id: str = "user_1",
) -> dict:
    # Session éphémère par requête.
    ephemeral_session_id = str(uuid.uuid4())
    session_service = get_session_service()

    app_logger.info("[MISSIONS] Initializing Agent and Runner (session: %s)...", ephemeral_session_id[:8])
    agent = await create_agent(ephemeral_session_id)
    runner = Runner(app_name="zenika_missions_assistant", agent=agent, session_service=session_service)
    await session_service.create_session(
        app_name="zenika_missions_assistant", user_id=user_id, session_id=ephemeral_session_id
    )

    response_text, steps, thoughts, total_input_tokens, total_output_tokens, last_tool_data = (
        await run_agent_and_collect(runner, user_id, ephemeral_session_id, query, "missions", "[MISSIONS]")
    )

    # --- Foolproof metadata reconstruction from Redis session ---
    try:
        updated_session = await session_service.get_session(
            app_name="zenika_missions_assistant", user_id=user_id, session_id=ephemeral_session_id
        )
        if updated_session:
            meta = extract_metadata_from_session(updated_session)
            steps = meta.get("steps", [])
            thoughts = [meta.get("thoughts", "")] if meta.get("thoughts") else []
            last_tool_data = meta.get("data")
            app_logger.info("[MISSIONS] Post-processed metadata: %d steps.", len(steps))
    except Exception as e:
        app_logger.error("[MISSIONS] Error in metadata post-processing: %s", e)

    # --- FinOps async logging (avec retry tenacity côté finops.py) ---
    log_tokens_to_bq(
        session_id=session_id,
        action="missions_agent_execution",
        model=agent.model,
        input_tokens=total_input_tokens,
        output_tokens=total_output_tokens,
        query=query,
        auth_header=auth_header_var.get(),
    )

    # --- Guardrail anti-hallucination (G1) ---
    response_text, steps = check_hallucination_guardrail(response_text, steps, "[MISSIONS]")

    # --- Guardrail 3 : invention d'ID ---
    steps = check_id_invention_guardrail(steps, "[MISSIONS]")

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
