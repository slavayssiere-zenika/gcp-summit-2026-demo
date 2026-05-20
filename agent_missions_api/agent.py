"""
agent_missions_api/agent.py — Missions Agent (Staffing Director) ADK implementation.

Ce fichier configure l'agent ADK spécialisé Missions & Staffing.
Toute la logique commune (proxy MCP, boucle runner, guardrails, FinOps,
session Redis) est importée depuis le package `agent_commons`.
"""

import logging
import os
import uuid


from google.adk.agents import Agent
from google.adk.runners import Runner
from google.genai import types


from agent_commons.finops import estimate_cost_usd, log_tokens_to_bq
from agent_commons.guardrails import (check_hallucination_guardrail,
                                      check_id_invention_guardrail)
from agent_commons.mcp_client import MCPHttpClient, auth_header_var
from agent_commons.mcp_proxy import get_cached_tools
from agent_commons.metadata import extract_metadata_from_session
from agent_commons.runner import run_agent_and_collect
from agent_commons.session import (RedisSessionService,
                                   get_missions_context,
                                   store_missions_context)
from agent_commons.ui_tools import render_ui_widgets
from shared.schemas.staffing import MissionAnalysis
from agent_commons.prompt_loader import (
    fetch_agent_prompt,
    get_or_create_gemini_context_cache,
)


app_logger = logging.getLogger(__name__)


def _output_schema_kwargs() -> dict:
    """Active output_schema=MissionAnalysis si ENABLE_OUTPUT_SCHEMA=true (opt-in).

    Si requires_human_approval=True dans la réponse, le handler déclenchera le HITL.
    """
    if os.getenv("ENABLE_OUTPUT_SCHEMA", "false").lower() == "true":
        return {"output_schema": MissionAnalysis, "output_key": "missions_result"}
    return {}


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
    _default = (
        "Tu es l'Agent Missions (Staffing Director) de la plateforme Zenika. "
        "Tu es sp\u00e9cialis\u00e9 dans la gestion des missions client et le staffing des consultants."
    )
    instruction_text = await fetch_agent_prompt(
        prompt_key="agent_missions_api.system_instruction",
        default_text=_default,
        auth_header=auth_header_var.get(),
        agent_prefix="[MISSIONS]",
    )

    # AGENTS.md §1.4 : variable dédiée per-agent. GEMINI_MODEL est le fallback legacy.
    model = os.getenv("GEMINI_MISSIONS_MODEL", os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview"))
    tools_loaded = await get_cached_tools(_MISSIONS_CLIENTS_MAP, "[MISSIONS]", ttl=300, _cache=_MISSIONS_TOOLS_CACHE)
    MISSIONS_TOOLS = tools_loaded + [render_ui_widgets]

    if not MISSIONS_TOOLS:
        app_logger.error(
            "[MISSIONS] 🚨 CRITICAL: 0 MCP tools loaded! "
            "Agent will have no tools and will HALLUCINATE. Check MCP service connectivity."
        )
    else:
        app_logger.info("[MISSIONS] Creating Agent with %d tools...", len(MISSIONS_TOOLS))

    # ── Context Caching Gemini ────────────────────────────────────────────────
    cache_name = await get_or_create_gemini_context_cache(
        prompt_key="agent_missions_api.system_instruction",
        prompt_text=instruction_text,
        model=model,
        agent_prefix="[MISSIONS]",
    )

    cached_content = None
    if cache_name:
        cached_content = cache_name
        instruction_text = ""

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
            cached_content=cached_content,
        ),
        instruction=instruction_text,
        description="Le module spécialisé dans la gestion des missions client et le staffing de consultants.",
        tools=MISSIONS_TOOLS,
        **_output_schema_kwargs(),
    )
    app_logger.info("[MISSIONS] Agent created successfully with %d tools.", len(MISSIONS_TOOLS))
    return agent


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
async def run_agent_query(
    query: str,
    session_id: str | None = None,
    auth_token: str | None = None,
    user_id: str = "user_1",
) -> dict:
    # Fix JWT propagation [STAFF-007] — re-setter auth_header_var dans CE contexte asyncio
    if auth_token:
        auth_header_var.set(auth_token)

    # Session éphémère par requête.
    ephemeral_session_id = str(uuid.uuid4())
    session_service = get_session_service()

    app_logger.info("[MISSIONS] Initializing Agent and Runner (session: %s)...", ephemeral_session_id[:8])

    # --- [§3.3] Mémoire cross-session : injection du contexte mission si disponible ---
    cached_context = None
    if session_id:
        try:
            r = session_service.r
            cached_context = get_missions_context(r, session_id)
            if cached_context:
                app_logger.info(
                    "[MISSIONS] 🧠 Contexte mission restauré depuis Redis (mission_id=%s)",
                    cached_context.get("mission_id", "?"),
                )
        except Exception as e:
            app_logger.warning("[MISSIONS] Impossible de lire le contexte mission Redis: %s", e)

    agent = await create_agent(ephemeral_session_id)
    runner = Runner(app_name="zenika_missions_assistant", agent=agent, session_service=session_service)
    await session_service.create_session(
        app_name="zenika_missions_assistant", user_id=user_id, session_id=ephemeral_session_id
    )

    response_text, steps, thoughts, total_input_tokens, total_output_tokens, last_tool_data, display_type = (
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

            # --- [§3.3] Persistance du contexte mission si un appel get_mission a eu lieu ---
            if session_id and last_tool_data and isinstance(last_tool_data, dict):
                mission_id = last_tool_data.get("id") or last_tool_data.get("mission_id")
                if mission_id:
                    try:
                        store_missions_context(session_service.r, session_id, {
                            "mission_id": mission_id,
                            "title": last_tool_data.get("title", ""),
                            "status": last_tool_data.get("status", ""),
                            "required_skills": last_tool_data.get("required_skills", []),
                            "client": last_tool_data.get("client", ""),
                        })
                        app_logger.info(
                            "[MISSIONS] 🧠 Contexte mission persisté en Redis (mission_id=%s)",
                            mission_id,
                        )
                    except Exception as e:
                        app_logger.warning("[MISSIONS] Impossible de persister le contexte mission: %s", e)
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

    # --- Phase 3 HITL post-processing ---
    # Si ENABLE_OUTPUT_SCHEMA=true, l'agent peut produire un MissionAnalysis structuré.
    # On inspecte l'état de session pour détecter requires_human_approval=True.
    hitl_request_data = None
    if os.getenv("ENABLE_OUTPUT_SCHEMA", "false").lower() == "true":
        try:
            hitl_request_data = await _maybe_trigger_hitl(
                session_service=session_service,
                app_name="zenika_missions_assistant",
                user_id=user_id,
                session_id=ephemeral_session_id,
                caller_session_id=session_id,
                auth_token=auth_token,
            )
        except Exception as e:
            app_logger.warning("[MISSIONS][HITL] Impossible de déclencher le HITL : %s", e)

    # Injecter hitl_request dans data si déclenché
    merged_data = last_tool_data
    if hitl_request_data:
        merged_data = {**(last_tool_data or {}), "hitl_request": hitl_request_data}

    # --- ENABLE_OUTPUT_SCHEMA : display_type depuis MissionAnalysis (source de vérité) ---
    # Quand output_schema=MissionAnalysis est actif, le LLM renseigne display_type dans
    # la réponse JSON structurée. On l'utilise en priorité sur render_ui_widgets.
    if os.getenv("ENABLE_OUTPUT_SCHEMA", "false").lower() == "true":
        try:
            missions_result = getattr(updated_session, "state", {}).get("missions_result")
            if missions_result and isinstance(missions_result, dict) and missions_result.get("display_type"):
                schema_display_type = missions_result["display_type"]
                if schema_display_type != display_type:
                    app_logger.info(
                        "[MISSIONS] display_type override: render_ui_widgets=%r → output_schema=%r",
                        display_type, schema_display_type,
                    )
                display_type = schema_display_type
        except Exception as e:
            app_logger.warning("[MISSIONS] Impossible de lire missions_result.display_type : %s", e)

    return {
        "response": response_text,
        "data": merged_data,
        "display_type": display_type,  # Pydantic (ENABLE_OUTPUT_SCHEMA) > render_ui_widgets
        "steps": steps,
        "thoughts": "\n".join(thoughts),
        "usage": {
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "estimated_cost_usd": estimate_cost_usd(total_input_tokens, total_output_tokens),
        },
    }


async def _maybe_trigger_hitl(
    session_service,
    app_name: str,
    user_id: str,
    session_id: str,
    caller_session_id: str | None,
    auth_token: str | None,  # noqa: ARG001 — conservé pour compatibilité API future
) -> dict | None:
    """Inspecte la session ADK pour un MissionAnalysis avec requires_human_approval=True.

    Si trouvé, crée une entrée Redis directement via hitl_create_entry() (import interne)
    — sans aller-retour HTTP ni loopback Cloud Run.
    Retourne le payload hitl_request à injecter dans la réponse A2A, ou None.
    """
    try:
        updated_session = await session_service.get_session(
            app_name=app_name, user_id=user_id, session_id=session_id
        )
        if not updated_session:
            return None

        # L'output_key par défaut est "missions_result" (voir _output_schema_kwargs)
        missions_result = getattr(updated_session, "state", {}).get("missions_result")
        if not missions_result or not isinstance(missions_result, dict):
            return None

        if not missions_result.get("requires_human_approval", False):
            return None

        app_logger.info(
            "[MISSIONS][HITL] requires_human_approval=True détecté — création demande HITL directe"
        )

        # Import local pour éviter la dépendance circulaire au module level
        # (agent.py est importé par main.py qui définit hitl_create_entry)

        # Import local depuis hitl_router pour éviter la dépendance circulaire
        # (agent.py est importé par main.py → on ne peut pas importer main au niveau module)
        from hitl_router import hitl_create_entry  # noqa: PLC0415

        result = await hitl_create_entry(
            mission_title=missions_result.get("mission_title", "Mission inconnue"),
            reason=missions_result.get("approval_reason") or (
                f"Urgence '{missions_result.get('urgency_level', 'unknown')}' "
                f"— validation managériale requise."
            ),
            candidates=[
                {
                    "consultant_id": c.get("consultant_id", 0),
                    "full_name": c.get("full_name", ""),
                    "confidence_score": c.get("confidence_score", 0.0),
                }
                for c in missions_result.get("recommended_consultants", [])
            ],
            urgency_level=missions_result.get("urgency_level", "medium"),
            session_id=caller_session_id or "",
        )

        return {
            "hitl_id": result["hitl_id"],
            "expires_at": result["expires_at"],
            "mission_title": missions_result.get("mission_title", ""),
            "reason": missions_result.get("approval_reason", "Validation requise."),
            "candidates": missions_result.get("recommended_consultants", []),
        }

    except Exception as e:
        app_logger.error("[MISSIONS][HITL] _maybe_trigger_hitl error: %s", e, exc_info=True)
        return None
