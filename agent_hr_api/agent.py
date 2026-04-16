import os
import json
import logging
from typing import Optional
from google.genai import types
from google.adk.agents import Agent
import httpx
from opentelemetry.propagate import inject

import logging
import inspect
import time
from typing import Optional

app_logger = logging.getLogger(__name__)

# Outils de recherche de candidats dont les résultats vides doivent déclencher le guardrail anti-hallucination.
# Si l'un de ces outils est appelé et retourne une liste vide (ou 0 résultats), l'agent NE DOIT PAS
# compléter avec des profils inventés. Le guardrail COM-006 intercepte ce cas.
CANDIDATE_SEARCH_TOOLS = {
    "search_best_candidates",
    "search_users",
    "list_users",
    "get_users_by_tag",
}


def _is_empty_candidate_result(result_data: object) -> bool:
    """Retourne True si le résultat d'un outil de recherche de candidats est vide.

    Détecte les formats courants retournés par les MCPs :
    - Liste vide : []
    - Dict avec clé connue vide : {"results": [], "total": 0}
    - Dict avec count/total à 0
    - None

    Utilisé par le guardrail COM-006 pour prévenir les hallucinations post-outil.
    """
    if result_data is None:
        return True
    if isinstance(result_data, list) and len(result_data) == 0:
        return True
    if isinstance(result_data, dict):
        # Formats courants : {"results": [], "total": 0} ou {"users": [], "count": 0}
        for key in ("results", "candidates", "users", "items", "data"):
            if key in result_data:
                val = result_data[key]
                if isinstance(val, list) and len(val) == 0:
                    return True
        # Champ générique "total" ou "count" à 0
        if result_data.get("total", -1) == 0 or result_data.get("count", -1) == 0:
            return True
    return False

_session_service = None

def get_session_service():
    global _session_service
    if _session_service is None:
        from session import RedisSessionService
        _session_service = RedisSessionService()
    return _session_service


# --- MCP Clients Initialization for HR ---
from mcp_client import MCPHttpClient, MCPSseClient

# IMPORTANT: For list_tools() and call_tool(), we target the MCP sidecars directly.
# The MCP sidecars expose /mcp/tools and /mcp/call WITHOUT JWT (internal traffic).
# The main APIs (users_api:8000) proxy /mcp/* through their protected_router which
# requires a JWT — but list_tools() is called at agent init time before any request context.
# Using env vars: *_MCP_URL (sidecar) vs *_API_URL (main API with JWT).
USERS_MCP_URL = os.getenv("USERS_MCP_URL", "http://users_mcp:8000")
ITEMS_MCP_URL = os.getenv("ITEMS_MCP_URL", "http://items_mcp:8000")
COMPETENCIES_MCP_URL = os.getenv("COMPETENCIES_MCP_URL", "http://competencies_mcp:8000")
CV_MCP_URL = os.getenv("CV_MCP_URL", "http://cv_mcp:8000")
MISSIONS_MCP_URL = os.getenv("MISSIONS_MCP_URL", "http://missions_mcp:8000")

# Note: Each of these clients uses auth_header_var from mcp_client.py seamlessly.
# Base URL only — MCPHttpClient.list_tools() appends /mcp/tools and call_tool() appends /mcp/call
users_client = MCPHttpClient(USERS_MCP_URL)
items_client = MCPHttpClient(ITEMS_MCP_URL)
comp_client = MCPHttpClient(COMPETENCIES_MCP_URL)
cv_client = MCPHttpClient(CV_MCP_URL)
missions_client = MCPHttpClient(MISSIONS_MCP_URL)

HR_TOOLS = []
# Tools will be fetched asynchronously in create_agent()

# --- MCP Tools Cache (avoids 5 HTTP calls per request) ---
_tools_cache: list = []
_tools_cache_ts: float = 0.0
_TOOLS_CACHE_TTL = 300  # 5 minutes


def create_mcp_tool_proxy(client, tool_def):
    """
    Crée dynamiquement une fonction Python asynchrone qui encapsule un outil MCP.
    Cela permet à l'ADK Google de valider et d'utiliser l'outil comme une fonction native.
    """
    name = tool_def["name"]
    desc = tool_def.get("description", "No description")
    schema = tool_def.get("parameters", tool_def.get("inputSchema", {}))
    
    async def mcp_tool_wrapper(**kwargs):
        # On délègue l'appel au client HTTP MCP
        return await client.call_tool(name, kwargs)
    
    # Configuration des métadonnées pour l'ADK
    mcp_tool_wrapper.__name__ = name
    mcp_tool_wrapper.__doc__ = desc
    
    # Reconstruction de la signature pour l'inspection (Gemini Parameters)
    params = []
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    
    for p_name, p_def in properties.items():
        # Mapping des types JSON Schema vers Python pour l'inspection ADK
        # IMPORTANT: Use `object` (not `Any`) as the fallback type.
        # ADK calls isinstance(default_value, annotation) to validate optional params.
        # isinstance(None, typing.Any) raises TypeError — isinstance(None, object) returns True.
        p_type = object  # safe fallback: base class of everything in Python
        js_type = p_def.get("type")
        if js_type == "string": p_type = str
        elif js_type == "integer": p_type = int
        elif js_type == "number": p_type = float
        elif js_type == "boolean": p_type = bool
        # IMPORTANT: arrays and objects MUST NOT map to `list`.
        # Mapping array -> list generates {"type": "array"} WITHOUT an "items" field,
        # which Gemini rejects with 400 INVALID_ARGUMENT (items: missing field).
        # Falls through to `object` fallback above.
        
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
        app_logger.info("[HR] Using cached MCP tool definitions (%d tools).", len(_tools_cache))
        return _tools_cache
    app_logger.info("[HR] Fetching MCP tool definitions from all MCP sidecars...")
    
    # Tools that are infrastructure-level, not business tools — excluded from LLM context
    # to avoid wasting tokens and causing confusion in the agent.
    NON_BUSINESS_TOOLS = {"health_check", "ping", "healthcheck", "health", "status"}
    
    raw_tools = []
    for name, client in [
        ("users_mcp", users_client),
        ("items_mcp", items_client),
        ("competencies_mcp", comp_client),
        ("cv_mcp", cv_client),
        ("missions_mcp", missions_client),
    ]:
        app_logger.info("[HR] Connecting to %s at %s ...", name, client.url)
        try:
            service_tools = await client.list_tools()
            count = 0
            for t in service_tools:
                try:
                    proxy = create_mcp_tool_proxy(client, t)
                    raw_tools.append(proxy)
                    count += 1
                except Exception as te:
                    app_logger.error(f"[HR] Failed to proxy tool {t.get('name')}: {te}")
            app_logger.info("[HR] ✅ Loaded %d tools from %s.", count, name)
        except Exception as e:
            app_logger.error("[HR] ❌ Could NOT load tools from %s (%s): %s — agent will have REDUCED capabilities", name, client.url, e)
    
    # Deduplicate by function name (Gemini rejects duplicate function declarations with 400)
    # and filter out non-business infrastructure tools (health_check etc.)
    seen_names: set = set()
    tools = []
    for proxy in raw_tools:
        fn_name = proxy.__name__
        if fn_name in NON_BUSINESS_TOOLS:
            app_logger.debug("[HR] Skipping non-business tool: %s", fn_name)
            continue
        if fn_name in seen_names:
            app_logger.warning("[HR] Duplicate tool name '%s' skipped (kept first occurrence).", fn_name)
            continue
        seen_names.add(fn_name)
        tools.append(proxy)
    
    _tools_cache = tools
    _tools_cache_ts = time.time()
    
    global HR_TOOLS
    HR_TOOLS = tools
    
    app_logger.info("[HR] Cached %d unique business MCP tools (TTL=%ds).", len(tools), _TOOLS_CACHE_TTL)
    return tools


async def create_agent(session_id: str | None = None):
    global HR_TOOLS  # Fix critique: sans ce 'global', HR_TOOLS dans create_agent() est une variable locale
    prompts_api_url = os.getenv("PROMPTS_API_URL", "http://prompts_api:8000")
    instruction_text = "Tu es l'Agent RH (Staffing & Compétences) de la plateforme Zenika. Tu détiens l'expertise des utilisateurs, des items et missions."
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(f"{prompts_api_url}/prompts/agent_hr_api.system_instruction")
            if res.status_code == 200:
                instruction_text = res.json()["value"]
            else:
                instruction_text += "\n[Fallback Instruction]" # Safe fallback
    except Exception as e:
        app_logger.warning(f"Error fetching system prompt for HR: {e}")
            
    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    
    tools_loaded = await _get_cached_tools()
    HR_TOOLS = tools_loaded  # Update module-level HR_TOOLS for /mcp/registry
    
    if not HR_TOOLS:
        app_logger.error("[HR] 🚨 CRITICAL: 0 MCP tools loaded! Agent will have no tools and will HALLUCINATE. Check MCP service connectivity.")
    else:
        app_logger.info("[HR] Creating Agent with %d tools...", len(HR_TOOLS))

    agent = Agent(
        name="assistant_zenika_hr",
        model=model,
        generate_content_config=types.GenerateContentConfig(
            http_options=types.HttpOptions(
                retry_options=types.HttpRetryOptions(initial_delay=1, attempts=2),
            ),
            # Encourage tool usage — without this Gemini prefers to answer from memory
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode="AUTO"
                )
            )
        ),
        instruction=instruction_text,
        description="Le module spécialisé dans les ressources humaines et le staffing.",
        tools=HR_TOOLS
    )
    app_logger.info("[HR] Agent created successfully with %d tools.", len(HR_TOOLS))
    return agent


async def run_agent_query(query: str, session_id: str | None = None, user_id: str = "user_1") -> dict:
    from google.adk.runners import Runner
    import uuid
    
    # Axe 1 — Session éphémère : TOUJOURS générer un UUID frais par requête.
    # Le session_id transmis par le Router (ex: "sebastien.lavayssiere") est
    # intentionnellement ignoré pour la session ADK interne afin d'éviter la
    # contamination de contexte entre requêtes successives (le LLM rejoue sinon
    # l'historique complet du user, causant des dérives de stratégie).
    # La persistance conversationnelle est gérée par Redis côté Router.
    ephemeral_session_id = str(uuid.uuid4())
    session_service = get_session_service()

    app_logger.info("[HR] Initializing Agent and Runner for query (session: %s)...", ephemeral_session_id[:8])
    agent = await create_agent(ephemeral_session_id)
    runner = Runner(app_name="zenika_hr_assistant", agent=agent, session_service=session_service)
    app_logger.info("[HR] Runner initialized.")
    
    await session_service.create_session(app_name="zenika_hr_assistant", user_id=user_id, session_id=ephemeral_session_id)
    
    response_parts = []
    last_tool_data = None
    steps = []
    seen_steps = set()
    thoughts = []
    total_input_tokens = 0
    total_output_tokens = 0
    # COM-006 : Accumule les résultats des outils de recherche de candidats
    # pour détecter les cas où tous les outils retournent des listes vides.
    candidate_search_results: list = []
    
    new_message = types.Content(role="user", parts=[types.Part(text=query)])
    
    app_logger.info("[HR] Starting runner.run_async...")
    async for event in runner.run_async(user_id=user_id, session_id=ephemeral_session_id, new_message=new_message):
        has_content = hasattr(event, 'content') and event.content is not None
        
        if has_content:
            # 1. Exhaustive metadata extraction from parts
            for part in (list(event.content.parts) if hasattr(event.content, 'parts') else []):
                # a) Thoughts (Gemini 2.0 Thinking support)
                thought_val = getattr(part, 'thought', None)
                if thought_val:
                    thoughts.append(str(thought_val))
                
                # b) Tool Calls (Observe orchestration)
                tcall = getattr(part, 'tool_call', None) or getattr(part, 'function_call', None)
                if tcall:
                    calls = tcall if isinstance(tcall, list) else [tcall]
                    for call in calls:
                        name = getattr(call, 'name', 'unknown')
                        args = getattr(call, 'args', {})
                        sig = f"call:{name}:{json.dumps(args, sort_keys=True)}"
                        if sig not in seen_steps:
                            app_logger.info(f"[HR] Captured Tool Call: {name}")
                            steps.append({"type": "call", "tool": name, "args": args})
                            seen_steps.add(sig)

                # c) Tool Results
                fres = getattr(part, 'function_response', None)
                if fres:
                    res_data = getattr(fres, 'response', fres)
                    if hasattr(res_data, 'model_dump'): res_data = res_data.model_dump()
                    elif hasattr(res_data, 'dict'): res_data = res_data.dict()
                    
                    # Unwrap MCP 'result' JSON string
                    if isinstance(res_data, dict) and "result" in res_data and isinstance(res_data["result"], str) and res_data["result"].startswith("{"):
                        try: res_data = json.loads(res_data["result"])
                        except: pass
                    
                    sig = f"result:{json.dumps(res_data, sort_keys=True)}"
                    if sig not in seen_steps:
                        last_tool_data = res_data # Propagate data to sub-agent output
                        steps.append({"type": "result", "data": res_data})
                        seen_steps.add(sig)
                    
                    # COM-006 : Associer le résultat à l'outil appelé pour le guardrail post-run
                    # On cherche le dernier tool_call qui correspond à un outil de recherche de candidats
                    tool_name_for_result = None
                    for s in reversed(steps):
                        if s.get("type") == "call" and s.get("tool") in CANDIDATE_SEARCH_TOOLS:
                            tool_name_for_result = s["tool"]
                            break
                    if tool_name_for_result:
                        candidate_search_results.append({
                            "tool": tool_name_for_result,
                            "result": res_data
                        })

        # 1.1 Alternative extraction for some ADK event structures (actions/helpers)
        if hasattr(event, 'actions') and event.actions:
            for action in event.actions:
                tc = getattr(action, 'tool_call', None)
                if tc:
                    name = getattr(tc, 'name', "unknown")
                    args = getattr(tc, 'args', {})
                    sig = f"call:{name}:{json.dumps(args, sort_keys=True)}"
                    if sig not in seen_steps:
                        app_logger.info(f"[HR] Captured Tool Call (actions): {name}")
                        steps.append({"type": "call", "tool": name, "args": args})
                        seen_steps.add(sig)
        
        if hasattr(event, 'get_function_calls'):
            for fc in (event.get_function_calls() or []):
                name = getattr(fc, 'name', "unknown")
                args = getattr(fc, 'args', {})
                sig = f"call:{name}:{json.dumps(args, sort_keys=True)}"
                if sig not in seen_steps:
                    app_logger.info(f"[HR] Captured Tool Call (get_fc): {name}")
                    steps.append({"type": "call", "tool": name, "args": args})
                    seen_steps.add(sig)

        # 2. Text response aggregation
        # We only aggregate text from model role, excluding tool calls and thoughts
        role_val = getattr(event.content, 'role', "").lower() if has_content else ""
        is_assistant = role_val in ["assistant", "model", "assistant_zenika_hr"]
        
        if has_content and is_assistant:
            if isinstance(event.content, str):
                response_parts.append(event.content)
            elif hasattr(event.content, 'parts'):
                for part in event.content.parts:
                    if getattr(part, 'text', None) and not getattr(part, 'tool_call', None) and not getattr(part, 'thought', None):
                        response_parts.append(part.text)
        
        # 3. Usage tracking (FinOps)
        u = getattr(event.response, 'usage_metadata', None) if hasattr(event, 'response') else getattr(event, 'usage_metadata', None)
        if u:
            it = getattr(u, 'prompt_token_count', 0) or (u.get('prompt_token_count', 0) if isinstance(u, dict) else 0)
            ot = getattr(u, 'candidates_token_count', 0) or (u.get('candidates_token_count', 0) if isinstance(u, dict) else 0)
            total_input_tokens = max(total_input_tokens, it)
            total_output_tokens = max(total_output_tokens, ot)
    
    response_text = "".join(response_parts)
    
    # --- FOOLPROOF METADATA RECONSTRUCTION ---
    # We fetch the session again after the run is complete to extract metadata from ALL events.
    # This solves issues where stream events might have been processed inconsistently.
    try:
        updated_session = await session_service.get_session(app_name="zenika_hr_assistant", user_id=user_id, session_id=ephemeral_session_id)
        if updated_session:
            from metadata import extract_metadata_from_session
            meta = extract_metadata_from_session(updated_session)
            steps = meta.get("steps", [])
            thoughts = [meta.get("thoughts", "")] if meta.get("thoughts") else []
            last_tool_data = meta.get("data")
            app_logger.info(f"[HR] Post-processed metadata: {len(steps)} steps captured.")
    except Exception as e:
        app_logger.error(f"[HR] Error in metadata post-processing: {e}")

    if total_input_tokens > 0 or total_output_tokens > 0:
        try:
            user_email = session_id if "@" in str(session_id) else f"{session_id}@zenika.com"
            from mcp_client import auth_header_var
            auth_header = auth_header_var.get()
            market_url = os.getenv("MARKET_MCP_URL", "http://api.internal.zenika/market-mcp/")
            headers = {"Authorization": auth_header} if auth_header else {}
            inject(headers)
            import asyncio
            async def log_bq():
                try:
                    async with httpx.AsyncClient(timeout=10.0, headers=headers) as c:
                        await c.post(f"{market_url.rstrip('/')}/mcp/call", json={
                            "name": "log_ai_consumption",
                            "arguments": {
                                "user_email": user_email,
                                "action": "hr_agent_execution",
                                "model": agent.model,
                                "input_tokens": total_input_tokens, "output_tokens": total_output_tokens,
                                "metadata": {"query": query[:100]}
                            }
                        })
                except Exception: pass
            asyncio.create_task(log_bq())
        except Exception:
            pass

    # --- GUARDRAIL 1 : Zéro appel d'outil ---
    # Si l'agent produit une réponse sans avoir appelé aucun outil, c'est une hallucination certaine.
    tool_calls_made = [s for s in steps if s.get("type") == "call"]
    if response_text and not tool_calls_made:
        app_logger.warning("[HR] ⚠️ HALLUCINATION RISK: Agent produced a response with ZERO tool calls. The response may be fabricated.")
        steps.insert(0, {
            "type": "warning",
            "tool": "GUARDRAIL",
            "args": {
                "message": "AUCUN OUTIL N'A ÉTÉ APPELÉ. La réponse ci-dessus provient de la mémoire du modèle, PAS de la base Zenika. Elle est potentiellement hallucinée."
            }
        })
        response_text = (
            "⚠️ ATTENTION : Cette réponse n'est pas fondée sur des données réelles (aucun outil MCP consulté).\n"
            "Les profils ci-dessous peuvent être inventés. Veuillez relancer la recherche.\n\n"
            + response_text
        )

    # --- GUARDRAIL 2 : COM-006 — Résultats de recherche vides (search_best_candidates / search_users) ---
    # Si tous les outils de recherche de candidats ont été appelés et ont tous retourné des listes vides,
    # l'agent NE DOIT PAS produire de profils. On remplace la réponse par un message d'absence de résultat.
    # Note: _is_empty_candidate_result est définie au niveau module pour être testable par import.
    if candidate_search_results:
        all_searches_empty = all(
            _is_empty_candidate_result(r["result"]) for r in candidate_search_results
        )
        searched_tools = list({r["tool"] for r in candidate_search_results})
        if all_searches_empty and response_text:
            app_logger.warning(
                "[HR] 🚨 COM-006 GUARDRAIL TRIGGERED: %d candidate search tool(s) (%s) returned EMPTY results, "
                "but agent still produced a candidate list. Overriding response to prevent hallucination.",
                len(candidate_search_results),
                ", ".join(searched_tools)
            )
            steps.insert(0, {
                "type": "warning",
                "tool": "GUARDRAIL_COM006",
                "args": {
                    "message": (
                        f"COM-006 DÉCLENCHÉ : Les outils {searched_tools} ont retourné 0 résultat. "
                        "La réponse originale de l'agent a été remplacée pour éviter l'hallucination de profils fictifs."
                    )
                }
            })
            response_text = (
                "Aucun profil trouvé dans la base Zenika pour cette recherche.\n"
                "Les outils de recherche consultés n'ont retourné aucun consultant correspondant à vos critères.\n"
                "Souhaitez-vous élargir la recherche (modifier les critères, retirer un filtre géographique) ?"
            )
            last_tool_data = None

    final_result = {
        "response": response_text,
        "data": last_tool_data,
        "steps": steps,
        "thoughts": "\n".join(thoughts),
        "usage": {
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "estimated_cost_usd": round(total_input_tokens * 0.000000075 + total_output_tokens * 0.0000003, 6)
        }
    }

    return final_result
