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

_session_service = None

def get_session_service():
    global _session_service
    if _session_service is None:
        from session import RedisSessionService
        _session_service = RedisSessionService()
    return _session_service


# --- MCP Clients Initialization for Ops ---
from mcp_client import MCPHttpClient, MCPSseClient

# Standard URLs, mapped to internal DNS or local
DRIVE_API_URL = os.getenv("DRIVE_MCP_URL", "http://drive_api:8006")
MARKET_MCP_URL = os.getenv("MARKET_MCP_URL", "http://market_mcp:8008")

# Note: Each of these clients uses auth_header_var from mcp_client.py seamlessly.
# Base URL only — MCPHttpClient.list_tools() appends /mcp/tools and call_tool() appends /mcp/call
drive_client = MCPHttpClient(DRIVE_API_URL)
market_client = MCPHttpClient(MARKET_MCP_URL)

# LOKI NOT AVAILABLE IN GCP (Uses standard GCP Logging)

OPS_TOOLS = []
# Tools will be fetched asynchronously in create_agent()

# --- MCP Tools Cache (avoids 3 HTTP calls per request) ---
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
    
    async def mcp_tool_proxy_func(**kwargs):
        # On délègue l'appel au client HTTP MCP
        return await client.call_tool(name, kwargs)
    
    # Configuration des métadonnées pour l'ADK
    mcp_tool_proxy_func.__name__ = name
    mcp_tool_proxy_func.__doc__ = desc
    
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
    
    mcp_tool_proxy_func.__signature__ = inspect.Signature(params)
    return mcp_tool_proxy_func


async def _get_cached_tools() -> list:
    global _tools_cache, _tools_cache_ts
    if _tools_cache and (time.time() - _tools_cache_ts) < _TOOLS_CACHE_TTL:
        app_logger.info("[Ops] Using cached MCP tool definitions (%d tools).", len(_tools_cache))
        return _tools_cache
    app_logger.info("[Ops] Fetching MCP tool definitions from all services...")

    NON_BUSINESS_TOOLS = {"health_check", "ping", "healthcheck", "health", "status"}

    raw_tools = []
    for name, client in [
        ("drive", drive_client),
        ("market", market_client),
    ]:
        try:
            service_tools = await client.list_tools()
            count = 0
            for t in service_tools:
                try:
                    proxy = create_mcp_tool_proxy(client, t)
                    raw_tools.append(proxy)
                    count += 1
                except Exception as te:
                    app_logger.error(f"[Ops] Failed to proxy tool {t.get('name')}: {te}")
            app_logger.info("[Ops] ✅ Loaded %d tools from %s.", count, name)
        except Exception as e:
            app_logger.warning("[Ops] ❌ Could not load tools from %s (degraded mode): %s", name, e)

    # Deduplicate by name + filter non-business tools
    seen_names: set = set()
    tools = []
    for proxy in raw_tools:
        fn_name = proxy.__name__
        if fn_name in NON_BUSINESS_TOOLS:
            continue
        if fn_name in seen_names:
            app_logger.warning("[Ops] Duplicate tool '%s' skipped.", fn_name)
            continue
        seen_names.add(fn_name)
        tools.append(proxy)

    _tools_cache = tools
    _tools_cache_ts = time.time()

    global OPS_TOOLS
    OPS_TOOLS = tools

    app_logger.info("[Ops] Cached %d unique business MCP tools (TTL=%ds).", len(tools), _TOOLS_CACHE_TTL)
    return tools


async def create_agent(session_id: str | None = None):
    prompts_api_url = os.getenv("PROMPTS_API_URL", "http://prompts_api:8000")
    instruction_text = "Tu es l'Agent Ops (Platform Engineering, FinOps & Sécurité) de la plateforme Zenika. Tu détiens l'expertise des logs et de l'infra."
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(f"{prompts_api_url}/prompts/agent_ops_api.system_instruction")
            if res.status_code == 200:
                instruction_text = res.json()["value"]
            else:
                instruction_text += "\n[Fallback Instruction]"
    except Exception as e:
        app_logger.warning(f"Error fetching system prompt for Ops: {e}")
            
    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    
    # Inject current UTC date so the agent can build correct BigQuery temporal filters
    from datetime import datetime as _dt
    current_datetime_utc = _dt.utcnow().strftime('%Y-%m-%d %H:%M UTC')
    instruction_text += (
        f"\n\n## Contexte Temporel\n"
        f"Date et heure actuelles (UTC) : **{current_datetime_utc}**.\n"
        f"Utilise cette date comme référence pour tous les filtrages temporels BigQuery.\n"
        f"Exemple : `DATE(timestamp) = '{_dt.utcnow().strftime('%Y-%m-%d')}'`"
    )
    
    OPS_TOOLS = await _get_cached_tools()
    
    app_logger.info("[Ops] Creating Agent with %d tools...", len(OPS_TOOLS))
    agent = Agent(
        name="assistant_zenika_ops",
        model=model,
        generate_content_config=types.GenerateContentConfig(
            http_options=types.HttpOptions(
                retry_options=types.HttpRetryOptions(initial_delay=1, attempts=2),
            )
        ),
        instruction=instruction_text,
        description="Le module spécialisé dans les Opérations, FinOps, Log Monitoring.",
        tools=OPS_TOOLS
    )
    app_logger.info("[Ops] Agent created successfully.")
    return agent


async def run_agent_query(query: str, session_id: str | None = None, user_id: str = "user_1") -> dict:
    from google.adk.runners import Runner
    import uuid
    
    # Axe 1 — Session éphémère : TOUJOURS générer un UUID frais par requête.
    # Voir commentaire équivalent dans agent_hr_api/agent.py.
    ephemeral_session_id = str(uuid.uuid4())
    session_service = get_session_service()

    app_logger.info("[Ops] Initializing Agent and Runner for query (session: %s)...", ephemeral_session_id[:8])
    agent = await create_agent(ephemeral_session_id)
    runner = Runner(app_name="zenika_ops_assistant", agent=agent, session_service=session_service)
    app_logger.info("[Ops] Runner initialized.")
    
    await session_service.create_session(app_name="zenika_ops_assistant", user_id=user_id, session_id=ephemeral_session_id)
    
    response_parts = []
    last_tool_data = None
    steps = []
    seen_steps = set()
    thoughts = []
    total_input_tokens = 0
    total_output_tokens = 0
    
    new_message = types.Content(role="user", parts=[types.Part(text=query)])
    
    app_logger.info("[Ops] Starting runner.run_async...")
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
                            app_logger.info(f"[Ops] Captured Tool Call: {name}")
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

        # 1.1 Alternative extraction for some ADK event structures (actions/helpers)
        if hasattr(event, 'actions') and event.actions:
            for action in event.actions:
                tc = getattr(action, 'tool_call', None)
                if tc:
                    name = getattr(tc, 'name', "unknown")
                    args = getattr(tc, 'args', {})
                    sig = f"call:{name}:{json.dumps(args, sort_keys=True)}"
                    if sig not in seen_steps:
                        app_logger.info(f"[Ops] Captured Tool Call (actions): {name}")
                        steps.append({"type": "call", "tool": name, "args": args})
                        seen_steps.add(sig)
        
        if hasattr(event, 'get_function_calls'):
            for fc in (event.get_function_calls() or []):
                name = getattr(fc, 'name', "unknown")
                args = getattr(fc, 'args', {})
                sig = f"call:{name}:{json.dumps(args, sort_keys=True)}"
                if sig not in seen_steps:
                    app_logger.info(f"[Ops] Captured Tool Call (get_fc): {name}")
                    steps.append({"type": "call", "tool": name, "args": args})
                    seen_steps.add(sig)

        # 2. Text response aggregation
        # We only aggregate text from model role, excluding tool calls and thoughts
        role_val = getattr(event.content, 'role', "").lower() if has_content else ""
        is_assistant = role_val in ["assistant", "model", "assistant_zenika_ops"]
        
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
    try:
        updated_session = await session_service.get_session(app_name="zenika_ops_assistant", user_id=user_id, session_id=ephemeral_session_id)
        if updated_session:
            from metadata import extract_metadata_from_session
            meta = extract_metadata_from_session(updated_session)
            steps = meta.get("steps", [])
            thoughts = [meta.get("thoughts", "")] if meta.get("thoughts") else []
            last_tool_data = meta.get("data")
            app_logger.info(f"[Ops] Post-processed metadata: {len(steps)} steps captured.")
    except Exception as e:
        app_logger.error(f"[Ops] Error in metadata post-processing: {e}")

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
                                "action": "ops_agent_execution",
                                "model": agent.model,
                                "input_tokens": total_input_tokens, "output_tokens": total_output_tokens,
                                "metadata": {"query": query[:100]}
                            }
                        })
                except Exception: pass
            asyncio.create_task(log_bq())
        except Exception:
            pass

    # --- HALLUCINATION GUARDRAIL ---
    tool_calls_made = [s for s in steps if s.get("type") == "call"]
    if response_text and not tool_calls_made:
        app_logger.warning("[Ops] ⚠️ HALLUCINATION RISK: Agent produced a response with ZERO tool calls.")
        steps.insert(0, {
            "type": "warning",
            "tool": "GUARDRAIL",
            "args": {
                "message": "AUCUN OUTIL N'A ÉTÉ APPELÉ. La réponse provient de la mémoire du modèle, PAS des données de la plateforme. Elle est potentiellement inexacte."
            }
        })
        response_text = (
            "⚠️ ATTENTION : Réponse non fondée sur des données réelles (aucun outil consulté).\n\n"
            + response_text
        )

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
