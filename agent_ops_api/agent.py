"""
agent_ops_api/agent.py — Ops Agent (Platform Engineering, FinOps & Sécurité) ADK implementation.

Ce fichier configure l'agent ADK spécialisé Opérations.
Toute la logique commune (proxy MCP, boucle runner, guardrails, FinOps,
session Redis) est importée depuis le package `agent_commons`.
"""

import os
import uuid
import logging
from datetime import datetime as _dt

import httpx
from google.genai import types
from google.adk.agents import Agent
from google.adk.runners import Runner

from agent_commons.mcp_client import MCPHttpClient, auth_header_var
from agent_commons.session import RedisSessionService
from agent_commons.metadata import extract_metadata_from_session
from agent_commons.mcp_proxy import get_cached_tools
from agent_commons.runner import run_agent_and_collect
from agent_commons.guardrails import check_hallucination_guardrail
from agent_commons.finops import log_tokens_to_bq, estimate_cost_usd

app_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MCP Clients — URLs propres à l'agent Ops
# ---------------------------------------------------------------------------
DRIVE_MCP_URL = os.getenv("DRIVE_MCP_URL", "http://drive_api:8006")
MARKET_MCP_URL = os.getenv("MARKET_MCP_URL", "http://market_mcp:8008")
MONITORING_MCP_URL = os.getenv("MONITORING_MCP_URL", "http://monitoring_mcp:8010")
PROMPTS_MCP_URL = os.getenv("PROMPTS_MCP_URL", "http://prompts_api:8000")

drive_client = MCPHttpClient(DRIVE_MCP_URL)
market_client = MCPHttpClient(MARKET_MCP_URL)
monitoring_client = MCPHttpClient(MONITORING_MCP_URL)
prompts_client = MCPHttpClient(PROMPTS_MCP_URL)

_OPS_CLIENTS_MAP = [
    ("drive", drive_client),
    ("market", market_client),
    ("monitoring", monitoring_client),
    ("prompts", prompts_client),
]

# Cache isolé pour cet agent
_OPS_TOOLS_CACHE: dict = {}

# Public reference — exposée dans main.py pour /mcp/registry
OPS_TOOLS: list = []

# ---------------------------------------------------------------------------
# Session service (lazy init)
# ---------------------------------------------------------------------------
_session_service = None


def get_session_service() -> RedisSessionService:
    global _session_service
    if _session_service is None:
        _session_service = RedisSessionService(redis_key_prefix="adk:ops:sessions")
    return _session_service


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------
async def create_agent(session_id: str | None = None) -> Agent:
    global OPS_TOOLS
    prompts_api_url = os.getenv("PROMPTS_API_URL", "http://prompts_api:8000")
    instruction_text = (
        "Tu es l'Agent Ops (Platform Engineering, FinOps & Sécurité) de la plateforme Zenika. "
        "Tu détiens l'expertise des logs et de l'infra."
    )
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(f"{prompts_api_url}/prompts/agent_ops_api.system_instruction")
            if res.status_code == 200:
                instruction_text = res.json()["value"]
            else:
                instruction_text += "\n[Fallback Instruction]"
    except Exception as e:
        app_logger.warning("Error fetching system prompt for Ops: %s", e)

    # Injection de la date UTC pour les filtrages BigQuery temporels
    current_datetime_utc = _dt.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    instruction_text += (
        f"\n\n## Contexte Temporel\n"
        f"Date et heure actuelles (UTC) : **{current_datetime_utc}**.\n"
        f"Utilise cette date comme référence pour tous les filtrages temporels BigQuery.\n"
        f"Exemple : `DATE(timestamp) = '{_dt.utcnow().strftime('%Y-%m-%d')}'`"
    )

    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    tools_loaded = await get_cached_tools(_OPS_CLIENTS_MAP, "[Ops]", ttl=300, _cache=_OPS_TOOLS_CACHE)
    OPS_TOOLS = tools_loaded

    app_logger.info("[Ops] Creating Agent with %d tools...", len(OPS_TOOLS))
    agent = Agent(
        name="assistant_zenika_ops",
        model=model,
        generate_content_config=types.GenerateContentConfig(
            http_options=types.HttpOptions(
                retry_options=types.HttpRetryOptions(initial_delay=1, attempts=2),
            ),
        ),
        instruction=instruction_text,
        description="Le module spécialisé dans les Opérations, FinOps, Log Monitoring.",
        tools=OPS_TOOLS,
    )
    app_logger.info("[Ops] Agent created successfully.")
    return agent


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
async def run_agent_query(
    query: str,
    session_id: str | None = None,
    user_id: str = "user_1",
) -> dict:
    ephemeral_session_id = str(uuid.uuid4())
    session_service = get_session_service()

    app_logger.info("[Ops] Initializing Agent and Runner (session: %s)...", ephemeral_session_id[:8])
    agent = await create_agent(ephemeral_session_id)
    runner = Runner(app_name="zenika_ops_assistant", agent=agent, session_service=session_service)
    await session_service.create_session(
        app_name="zenika_ops_assistant", user_id=user_id, session_id=ephemeral_session_id
    )

    response_text, steps, thoughts, total_input_tokens, total_output_tokens, last_tool_data = (
        await run_agent_and_collect(runner, user_id, ephemeral_session_id, query, "ops", "[Ops]")
    )

    # --- Foolproof metadata reconstruction from Redis session ---
    try:
        updated_session = await session_service.get_session(
            app_name="zenika_ops_assistant", user_id=user_id, session_id=ephemeral_session_id
        )
        if updated_session:
            meta = extract_metadata_from_session(updated_session)
            steps = meta.get("steps", [])
            thoughts = [meta.get("thoughts", "")] if meta.get("thoughts") else []
            last_tool_data = meta.get("data")
            app_logger.info("[Ops] Post-processed metadata: %d steps.", len(steps))
    except Exception as e:
        app_logger.error("[Ops] Error in metadata post-processing: %s", e)

    # --- FinOps async logging ---
    log_tokens_to_bq(
        session_id=session_id,
        action="ops_agent_execution",
        model=agent.model,
        input_tokens=total_input_tokens,
        output_tokens=total_output_tokens,
        query=query,
        auth_header=auth_header_var.get(),
    )

    # --- Guardrail anti-hallucination ---
    response_text, steps = check_hallucination_guardrail(response_text, steps, "[Ops]")

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
