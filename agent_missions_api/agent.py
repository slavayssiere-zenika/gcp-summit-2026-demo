import asyncio
import json
import logging
import inspect
import os
import time
import uuid
from typing import Optional

from google.genai import types
from google.adk.agents import Agent
from google.adk.runners import Runner
import httpx
from opentelemetry.propagate import inject
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from mcp_client import MCPHttpClient, auth_header_var

app_logger = logging.getLogger(__name__)

_session_service = None


def get_session_service():
    global _session_service
    if _session_service is None:
        from session import RedisSessionService
        _session_service = RedisSessionService()
    return _session_service


# ---------------------------------------------------------------------------
# MCP Clients — uniquement les MCPs dont l'agent Missions a besoin :
#   • missions_mcp  : CRUD missions (list, get, create, reanalyze…)
#   • cv_mcp        : search_best_candidates, get_candidate_rag_context
#   • users_mcp     : profil consultant (nom, email, agence)
#   • competencies_mcp: taxonomie des compétences (pour enrichir le matching)
# Les MCP items et drive NE sont PAS nécessaires pour le Staffing Director.
# ---------------------------------------------------------------------------
MISSIONS_MCP_URL = os.getenv("MISSIONS_MCP_URL", "http://missions_mcp:8000")
CV_MCP_URL = os.getenv("CV_MCP_URL", "http://cv_mcp:8000")
USERS_MCP_URL = os.getenv("USERS_MCP_URL", "http://users_mcp:8000")
COMPETENCIES_MCP_URL = os.getenv("COMPETENCIES_MCP_URL", "http://competencies_mcp:8000")

missions_client = MCPHttpClient(MISSIONS_MCP_URL)
cv_client = MCPHttpClient(CV_MCP_URL)
users_client = MCPHttpClient(USERS_MCP_URL)
comp_client = MCPHttpClient(COMPETENCIES_MCP_URL)

MISSIONS_TOOLS: list = []

# --- MCP Tools Cache (5 min TTL) ---
_tools_cache: list = []
_tools_cache_ts: float = 0.0
_TOOLS_CACHE_TTL = 300  # secondes


def create_mcp_tool_proxy(client: MCPHttpClient, tool_def: dict):
    """
    Crée dynamiquement une fonction Python async encapsulant un outil MCP.
    Nécessaire pour que le SDK ADK Google puisse valider et appeler l'outil
    comme une fonction native avec une signature d'inspection correcte.
    """
    name = tool_def["name"]
    desc = tool_def.get("description", "No description")
    schema = tool_def.get("parameters", tool_def.get("inputSchema", {}))

    async def mcp_tool_wrapper(**kwargs):
        return await client.call_tool(name, kwargs)

    mcp_tool_wrapper.__name__ = name
    mcp_tool_wrapper.__doc__ = desc

    params = []
    properties = schema.get("properties", {})
    required = schema.get("required", [])

    for p_name, p_def in properties.items():
        p_type = object  # fallback sûr : isinstance(None, object) → True
        js_type = p_def.get("type")
        if js_type == "string":
            p_type = str
        elif js_type == "integer":
            p_type = int
        elif js_type == "number":
            p_type = float
        elif js_type == "boolean":
            p_type = bool
        # NB: array → JAMAIS list (Gemini rejette items manquants)

        default = inspect.Parameter.empty
        if p_name not in required:
            default = p_def.get("default", None)

        params.append(inspect.Parameter(
            p_name,
            inspect.Parameter.KEYWORD_ONLY,
            default=default,
            annotation=p_type
        ))

    mcp_tool_wrapper.__signature__ = inspect.Signature(params)
    return mcp_tool_wrapper


async def _get_cached_tools() -> list:
    global _tools_cache, _tools_cache_ts
    if _tools_cache and (time.time() - _tools_cache_ts) < _TOOLS_CACHE_TTL:
        app_logger.info("[MISSIONS] Using cached MCP tool definitions (%d tools).", len(_tools_cache))
        return _tools_cache

    app_logger.info("[MISSIONS] Fetching MCP tool definitions from MCP sidecars...")

    # Outils d'infrastructure exclus du contexte LLM pour éviter la confusion
    NON_BUSINESS_TOOLS = {"health_check", "ping", "healthcheck", "health", "status"}

    raw_tools = []
    for name, client in [
        ("missions_mcp", missions_client),
        ("cv_mcp", cv_client),
        ("users_mcp", users_client),
        ("competencies_mcp", comp_client),
    ]:
        app_logger.info("[MISSIONS] Connecting to %s at %s ...", name, client.url)
        try:
            service_tools = await client.list_tools()
            count = 0
            for t in service_tools:
                try:
                    proxy = create_mcp_tool_proxy(client, t)
                    raw_tools.append(proxy)
                    count += 1
                except Exception as te:
                    app_logger.error("[MISSIONS] Failed to proxy tool %s: %s", t.get("name"), te)
            app_logger.info("[MISSIONS] ✅ Loaded %d tools from %s.", count, name)
        except Exception as e:
            app_logger.error(
                "[MISSIONS] ❌ Could NOT load tools from %s (%s): %s — agent will have REDUCED capabilities",
                name, client.url, e
            )

    # Dédoublonnage (Gemini rejette les déclarations de fonctions en double)
    seen_names: set = set()
    tools = []
    for proxy in raw_tools:
        fn_name = proxy.__name__
        if fn_name in NON_BUSINESS_TOOLS:
            app_logger.debug("[MISSIONS] Skipping non-business tool: %s", fn_name)
            continue
        if fn_name in seen_names:
            app_logger.warning("[MISSIONS] Duplicate tool name '%s' skipped (kept first).", fn_name)
            continue
        seen_names.add(fn_name)
        tools.append(proxy)

    _tools_cache = tools
    _tools_cache_ts = time.time()

    global MISSIONS_TOOLS
    MISSIONS_TOOLS = tools

    app_logger.info("[MISSIONS] Cached %d unique business MCP tools (TTL=%ds).", len(tools), _TOOLS_CACHE_TTL)
    return tools


async def create_agent(session_id: str | None = None):
    global MISSIONS_TOOLS

    prompts_api_url = os.getenv("PROMPTS_API_URL", "http://prompts_api:8000")
    instruction_text = (
        "Tu es l'Agent Missions (Staffing Director) de la plateforme Zenika. "
        "Tu es spécialisé dans la gestion des missions client et le staffing des consultants."
    )
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(f"{prompts_api_url}/prompts/agent_missions_api.system_instruction")
            if res.status_code == 200:
                instruction_text = res.json()["value"]
            else:
                instruction_text += "\n[Fallback Instruction]"
    except Exception as e:
        app_logger.warning("[MISSIONS] Error fetching system prompt: %s", e)

    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    tools_loaded = await _get_cached_tools()
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
            )
        ),
        instruction=instruction_text,
        description="Le module spécialisé dans la gestion des missions client et le staffing de consultants.",
        tools=MISSIONS_TOOLS
    )

    app_logger.info("[MISSIONS] Agent created successfully with %d tools.", len(MISSIONS_TOOLS))
    return agent


async def run_agent_query(query: str, session_id: str | None = None, user_id: str = "user_1") -> dict:

    # Session éphémère par requête — évite la contamination de contexte inter-requêtes.
    # La persistance conversationnelle est gérée par Redis côté agent_router_api.
    ephemeral_session_id = str(uuid.uuid4())
    session_service = get_session_service()

    app_logger.info("[MISSIONS] Initializing Agent and Runner (session: %s)...", ephemeral_session_id[:8])
    agent = await create_agent(ephemeral_session_id)
    runner = Runner(app_name="zenika_missions_assistant", agent=agent, session_service=session_service)
    app_logger.info("[MISSIONS] Runner initialized.")

    await session_service.create_session(
        app_name="zenika_missions_assistant",
        user_id=user_id,
        session_id=ephemeral_session_id
    )

    response_parts = []
    last_tool_data = None
    steps = []
    seen_steps: set = set()
    thoughts = []
    total_input_tokens = 0
    total_output_tokens = 0

    new_message = types.Content(role="user", parts=[types.Part(text=query)])

    app_logger.info("[MISSIONS] Starting runner.run_async...")
    async for event in runner.run_async(
        user_id=user_id,
        session_id=ephemeral_session_id,
        new_message=new_message
    ):
        has_content = hasattr(event, "content") and event.content is not None

        if has_content:
            # 1. Extraction exhaustive depuis les parts
            for part in (list(event.content.parts) if hasattr(event.content, "parts") else []):
                # a) Thoughts (Gemini 2.0 Thinking)
                thought_val = getattr(part, "thought", None)
                if thought_val:
                    thoughts.append(str(thought_val))

                # b) Tool Calls
                tcall = getattr(part, "tool_call", None) or getattr(part, "function_call", None)
                if tcall:
                    calls = tcall if isinstance(tcall, list) else [tcall]
                    for call in calls:
                        name = getattr(call, "name", "unknown")
                        args = getattr(call, "args", {})
                        sig = f"call:{name}:{json.dumps(args, sort_keys=True)}"
                        if sig not in seen_steps:
                            app_logger.info("[MISSIONS] Tool Call: %s", name)
                            steps.append({"type": "call", "tool": name, "args": args})
                            seen_steps.add(sig)

                # c) Tool Results
                fres = getattr(part, "function_response", None)
                if fres:
                    res_data = getattr(fres, "response", fres)
                    if hasattr(res_data, "model_dump"):
                        res_data = res_data.model_dump()
                    elif hasattr(res_data, "dict"):
                        res_data = res_data.dict()
                    # Unwrap MCP 'result' JSON string
                    if (
                        isinstance(res_data, dict)
                        and "result" in res_data
                        and isinstance(res_data["result"], str)
                        and res_data["result"].startswith("{")
                    ):
                        try:
                            res_data = json.loads(res_data["result"])
                        except Exception:
                            pass
                    sig = f"result:{json.dumps(res_data, sort_keys=True)}"
                    if sig not in seen_steps:
                        last_tool_data = res_data
                        steps.append({"type": "result", "data": res_data})
                        seen_steps.add(sig)

        # 1.1 Structure alternative (actions)
        if hasattr(event, "actions") and event.actions:
            for action in event.actions:
                tc = getattr(action, "tool_call", None)
                if tc:
                    name = getattr(tc, "name", "unknown")
                    args = getattr(tc, "args", {})
                    sig = f"call:{name}:{json.dumps(args, sort_keys=True)}"
                    if sig not in seen_steps:
                        app_logger.info("[MISSIONS] Tool Call (actions): %s", name)
                        steps.append({"type": "call", "tool": name, "args": args})
                        seen_steps.add(sig)

        if hasattr(event, "get_function_calls"):
            for fc in (event.get_function_calls() or []):
                name = getattr(fc, "name", "unknown")
                args = getattr(fc, "args", {})
                sig = f"call:{name}:{json.dumps(args, sort_keys=True)}"
                if sig not in seen_steps:
                    steps.append({"type": "call", "tool": name, "args": args})
                    seen_steps.add(sig)

        # 2. Agrégation de la réponse textuelle
        role_val = getattr(event.content, "role", "").lower() if has_content else ""
        is_assistant = role_val in ["assistant", "model", "assistant_zenika_missions"]
        if has_content and is_assistant:
            if isinstance(event.content, str):
                response_parts.append(event.content)
            elif hasattr(event.content, "parts"):
                for part in event.content.parts:
                    if (
                        getattr(part, "text", None)
                        and not getattr(part, "tool_call", None)
                        and not getattr(part, "thought", None)
                    ):
                        response_parts.append(part.text)

        # 3. Usage tracking (FinOps)
        u = (
            getattr(event.response, "usage_metadata", None)
            if hasattr(event, "response")
            else getattr(event, "usage_metadata", None)
        )
        if u:
            it = getattr(u, "prompt_token_count", 0) or (u.get("prompt_token_count", 0) if isinstance(u, dict) else 0)
            ot = getattr(u, "candidates_token_count", 0) or (u.get("candidates_token_count", 0) if isinstance(u, dict) else 0)
            total_input_tokens = max(total_input_tokens, it)
            total_output_tokens = max(total_output_tokens, ot)

    response_text = "".join(response_parts)

    # --- Post-traitement métadonnées depuis Redis (robustesse) ---
    try:
        updated_session = await session_service.get_session(
            app_name="zenika_missions_assistant",
            user_id=user_id,
            session_id=ephemeral_session_id
        )
        if updated_session:
            from metadata import extract_metadata_from_session
            meta = extract_metadata_from_session(updated_session)
            steps = meta.get("steps", [])
            thoughts = [meta.get("thoughts", "")] if meta.get("thoughts") else []
            last_tool_data = meta.get("data")
            app_logger.info("[MISSIONS] Post-processed metadata: %d steps.", len(steps))
    except Exception as e:
        app_logger.error("[MISSIONS] Error in metadata post-processing: %s", e)

    # FinOps async logging — avec retry (tenacity) pour ne pas perdre les données de coûts
    if total_input_tokens > 0 or total_output_tokens > 0:
        try:
            user_email = session_id if "@" in str(session_id) else f"{session_id}@zenika.com"
            auth_header = auth_header_var.get()
            market_url = os.getenv("MARKET_MCP_URL", "http://api.internal.zenika/api/market/")
            _headers = {"Authorization": auth_header} if auth_header else {}
            inject(_headers)
            _payload = {
                "name": "log_ai_consumption",
                "arguments": {
                    "user_email": user_email,
                    "action": "missions_agent_execution",
                    "model": agent.model,
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                    "metadata": {"query": query[:100]}
                }
            }

            @retry(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, min=1, max=5),
                retry=retry_if_exception_type(Exception),
                reraise=False,
            )
            async def _log_finops_with_retry():
                async with httpx.AsyncClient(timeout=10.0, headers=_headers) as c:
                    await c.post(f"{market_url.rstrip('/')}/mcp/call", json=_payload)

            asyncio.create_task(_log_finops_with_retry())
        except Exception as finops_err:
            app_logger.warning("[MISSIONS] FinOps logging skipped: %s", finops_err)

    # --- Guardrail anti-hallucination ---
    tool_calls_made = [s for s in steps if s.get("type") == "call"]
    if response_text and not tool_calls_made:
        app_logger.warning(
            "[MISSIONS] ⚠️ HALLUCINATION RISK: Agent responded with ZERO tool calls. Response may be fabricated."
        )
        steps.insert(0, {
            "type": "warning",
            "tool": "GUARDRAIL",
            "args": {
                "message": (
                    "AUCUN OUTIL N'A ÉTÉ APPELÉ. La réponse provient de la mémoire du modèle, "
                    "PAS de la base Zenika. Les missions et consultants ci-dessous peuvent être inventés."
                )
            }
        })
        response_text = (
            "⚠️ ATTENTION : Cette réponse n'est pas fondée sur des données réelles (aucun outil MCP consulté).\n"
            "Les informations ci-dessous peuvent être inventées. Veuillez relancer la recherche.\n\n"
            + response_text
        )

    return {
        "response": response_text,
        "data": last_tool_data,
        "steps": steps,
        "thoughts": "\n".join(thoughts),
        "usage": {
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "estimated_cost_usd": round(
                total_input_tokens * 0.000000075 + total_output_tokens * 0.0000003, 6
            )
        }
    }
