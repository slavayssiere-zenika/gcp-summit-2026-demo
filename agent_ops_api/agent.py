"""
agent_ops_api/agent.py — Ops Agent (Platform Engineering, FinOps & Sécurité) ADK implementation.

Ce fichier configure l'agent ADK spécialisé Opérations.
Toute la logique commune (proxy MCP, boucle runner, guardrails, FinOps,
session Redis) est importée depuis le package `agent_commons`.
"""

import logging
import os
import uuid
from datetime import datetime as _dt, timezone


from google.adk.agents import Agent
from google.adk.runners import Runner
from google.genai import types


# AgentRegistry requis pour les MCP servers Vertex AI natifs (ex: Cloud Trace)
# Dépendance optionnelle : nécessite google-adk[a2a] + google-cloud-iamconnectorcredentials
try:
    from google.adk.integrations.agent_registry import AgentRegistry
    _AGENT_REGISTRY_AVAILABLE = True
except ImportError:
    AgentRegistry = None  # type: ignore[assignment,misc]
    _AGENT_REGISTRY_AVAILABLE = False
    app_logger = None  # sera initialisé plus bas

from agent_commons.finops import estimate_cost_usd, log_tokens_to_bq
from agent_commons.guardrails import (
    check_hallucination_guardrail,
    check_ops_metrics_guardrail,
)
from agent_commons.mcp_client import MCPHttpClient, auth_header_var
from agent_commons.mcp_proxy import get_cached_tools
from agent_commons.metadata import extract_metadata_from_session
from agent_commons.runner import run_agent_and_collect
from agent_commons.session import RedisSessionService
from agent_commons.ui_tools import render_ui_widgets
from shared.schemas.staffing import MissionAnalysis
from agent_commons.prompt_loader import (
    fetch_agent_prompt,
    get_or_create_gemini_context_cache,
)


app_logger = logging.getLogger(__name__)


def _output_schema_kwargs() -> dict:
    """Active output_schema=MissionAnalysis si ENABLE_OUTPUT_SCHEMA=true (opt-in)."""
    if os.getenv("ENABLE_OUTPUT_SCHEMA", "false").lower() == "true":
        return {"output_schema": MissionAnalysis, "output_key": "ops_result"}
    return {}


# MCP Server Cloud Trace natif Vertex AI (configuré via var d'env)
CLOUDTRACE_MCP_SERVER = os.getenv(
    "CLOUDTRACE_MCP_SERVER",
    "projects/prod-ia-staffing/locations/global/mcpServers/cloudtrace"
)
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "prod-ia-staffing")
GCP_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "global")

# ---------------------------------------------------------------------------
# MCP Clients — URLs propres à l'agent Ops
# ---------------------------------------------------------------------------
DRIVE_MCP_URL = os.getenv("DRIVE_MCP_URL", "http://drive_api:8006")
ANALYTICS_MCP_URL = os.getenv("ANALYTICS_MCP_URL", "http://analytics_mcp:8008")
MONITORING_MCP_URL = os.getenv("MONITORING_MCP_URL", "http://monitoring_mcp:8010")
PROMPTS_MCP_URL = os.getenv("PROMPTS_MCP_URL", "http://prompts_api:8000")

drive_client = MCPHttpClient(DRIVE_MCP_URL)
market_client = MCPHttpClient(ANALYTICS_MCP_URL)
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
    _default = (
        "Tu es l'Agent Ops (Platform Engineering, FinOps & Sécurité) de la plateforme Zenika. "
        "Tu détiens l'expertise des logs et de l'infra."
    )
    instruction_text = await fetch_agent_prompt(
        prompt_key="agent_ops_api.system_instruction",
        default_text=_default,
        auth_header=auth_header_var.get(),
        agent_prefix="[Ops]",
    )

    # Injection de la date UTC pour les filtrages BigQuery temporels
    current_datetime_utc = _dt.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    instruction_text += (
        f"\n\n## Contexte Temporel\n"
        f"Date et heure actuelles (UTC) : **{current_datetime_utc}**.\n"
        f"Utilise cette date comme référence pour tous les filtrages temporels BigQuery.\n"
        f"Exemple : `DATE(timestamp) = '{_dt.now(timezone.utc).strftime('%Y-%m-%d')}'`\n\n"
        f"## Analyse des Traces et Performances\n"
        f"Tu disposes de l'outil serveur Cloud Trace natif pour interroger directement "
        f"les traces de requêtes et leurs latences (spans). Utilise-le pour identifier pro-activement "
        f"les goulots d'étranglement de l'infrastructure. Si tu détectes une trace anormalement lente ou en erreur, "
        f"récupère l'ID de cette trace et utilise l'outil `search_cloud_logs_by_trace` "
        f"pour corréler la latence avec les logs d'application correspondants."
    )

    # AGENTS.md §1.4 : variable dédiée per-agent. GEMINI_MODEL est le fallback legacy.
    model = os.getenv("GEMINI_OPS_MODEL", os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview"))
    tools_loaded = await get_cached_tools(_OPS_CLIENTS_MAP, "[Ops]", ttl=300, _cache=_OPS_TOOLS_CACHE)

    # Intégration du serveur Cloud Trace natif Vertex AI via AgentRegistry
    # AgentRegistry.get_mcp_toolset() retourne un BaseToolset — compatible Agent(tools=[])
    # Contrairement à types.Tool(mcp_servers=[...]) qui est rejeté par l'ADK LlmAgent validator.
    cloudtrace_toolset = None
    if _AGENT_REGISTRY_AVAILABLE and os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() == "true":
        try:
            registry = AgentRegistry(project_id=GCP_PROJECT_ID, location=GCP_LOCATION)
            cloudtrace_toolset = registry.get_mcp_toolset(CLOUDTRACE_MCP_SERVER)
            app_logger.info("[Ops] ✅ Cloud Trace MCP toolset chargé depuis Vertex AI Agent Registry.")
        except Exception as e:
            app_logger.warning("[Ops] ⚠️ Cloud Trace MCP toolset non disponible : %s", e)

    tools_loaded = await get_cached_tools(_OPS_CLIENTS_MAP, "[OPS]", ttl=300, _cache=_OPS_TOOLS_CACHE)
    OPS_TOOLS = tools_loaded + [render_ui_widgets]
    if cloudtrace_toolset is not None:
        OPS_TOOLS.append(cloudtrace_toolset)

    app_logger.info("[Ops] Creating Agent with %d tools...", len(OPS_TOOLS))

    # ── Context Caching Gemini ────────────────────────────────────────────────
    cache_name = await get_or_create_gemini_context_cache(
        prompt_key="agent_ops_api.system_instruction",
        prompt_text=instruction_text,
        model=model,
        agent_prefix="[Ops]",
    )

    cached_content = None
    if cache_name:
        cached_content = cache_name
        instruction_text = ""

    agent = Agent(
        name="assistant_zenika_ops",
        model=model,
        generate_content_config=types.GenerateContentConfig(
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode="AUTO")
            ),
            http_options=types.HttpOptions(
                retry_options=types.HttpRetryOptions(initial_delay=1, attempts=2),
            ),
            cached_content=cached_content,
        ),
        instruction=instruction_text,
        description="Le module spécialisé dans les Opérations, FinOps, Log Monitoring.",
        tools=OPS_TOOLS,
        **_output_schema_kwargs(),
    )
    app_logger.info("[Ops] Agent created successfully.")
    return agent


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def check_ops_hallucination_guardrail(query: str, response_text: str, steps: list[dict]) -> tuple[str, list[dict]]:
    """Guardrail spécifique pour Ops : ignore le faux positif si la tâche est purement générative."""
    if any(s.get("type") == "call" for s in steps):
        return response_text, steps

    generative_keywords = [
        "génère", "genere", "rédige", "redige", "écris", "ecris", "propose"
    ]
    query_lower = query.lower()

    is_generative = any(kw in query_lower for kw in generative_keywords)

    if is_generative:
        app_logger.info("[Ops] ℹ️ Zero tools called, but query appears generative. Bypassing hallucination guardrail.")
        return response_text, steps

    return check_hallucination_guardrail(response_text, steps, "[Ops]")


async def run_agent_query(
    query: str,
    session_id: str | None = None,
    auth_token: str | None = None,
    user_id: str = "user_1",
) -> dict:
    # Fix JWT propagation [STAFF-007] — re-setter auth_header_var dans CE contexte asyncio
    if auth_token:
        auth_header_var.set(auth_token)

    ephemeral_session_id = str(uuid.uuid4())
    session_service = get_session_service()

    app_logger.info("[Ops] Initializing Agent and Runner (session: %s)...", ephemeral_session_id[:8])
    agent = await create_agent(ephemeral_session_id)
    runner = Runner(app_name="zenika_ops_assistant", agent=agent, session_service=session_service)
    await session_service.create_session(
        app_name="zenika_ops_assistant", user_id=user_id, session_id=ephemeral_session_id
    )

    response_text, steps, thoughts, total_input_tokens, total_output_tokens, last_tool_data, display_type = (
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

    # --- Guardrail 1 : anti-hallucination (zéro appel d'outil) ---
    response_text, steps = check_ops_hallucination_guardrail(query, response_text, steps)

    # --- Guardrail P0-2 : métriques chiffrées sans données FinOps réelles ---
    response_text, steps = check_ops_metrics_guardrail(response_text, steps, "[Ops]")

    # --- ENABLE_OUTPUT_SCHEMA : display_type depuis MissionAnalysis (source de vérité) ---
    # Quand output_schema=MissionAnalysis est actif, le LLM renseigne display_type dans
    # la réponse JSON structurée. On l'utilise en priorité sur render_ui_widgets.
    if os.getenv("ENABLE_OUTPUT_SCHEMA", "false").lower() == "true":
        try:
            ops_result = getattr(updated_session, "state", {}).get("ops_result")
            if ops_result and isinstance(ops_result, dict) and ops_result.get("display_type"):
                schema_display_type = ops_result["display_type"]
                if schema_display_type != display_type:
                    app_logger.info(
                        "[Ops] display_type override: render_ui_widgets=%r → output_schema=%r",
                        display_type, schema_display_type,
                    )
                display_type = schema_display_type
        except Exception as e:
            app_logger.warning("[Ops] Impossible de lire ops_result.display_type : %s", e)

    return {
        "response": response_text,
        "data": last_tool_data,
        "display_type": display_type,  # Pydantic (ENABLE_OUTPUT_SCHEMA) > render_ui_widgets
        "steps": steps,
        "thoughts": "\n".join(thoughts),
        "usage": {
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "estimated_cost_usd": estimate_cost_usd(total_input_tokens, total_output_tokens),
        },
    }
