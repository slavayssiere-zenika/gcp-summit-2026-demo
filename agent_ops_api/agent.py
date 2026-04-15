import os
import json
import logging
from typing import Optional
from google.genai import types
from google.adk.agents import Agent
import httpx
from opentelemetry.propagate import inject

logger = logging.getLogger(__name__)

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
DRIVE_API_URL = os.getenv("DRIVE_MCP_URL", "http://drive_api:8000")
MARKET_MCP_URL = os.getenv("MARKET_MCP_URL", "http://market_mcp:8000")

# Note: Each of these clients uses auth_header_var from mcp_client.py seamlessly.
drive_client = MCPHttpClient(f"{DRIVE_API_URL.rstrip('/')}/mcp/query")
market_client = MCPHttpClient(f"{MARKET_MCP_URL.rstrip('/')}/mcp/query")

# LOKI Uses SSE Client
# Warning: The architecture rule strictly favors HTTP. But we keep it as SSE if it was designed so, or HTTP if we refactored it.
LOKI_MCP_URL = os.getenv("LOKI_MCP_URL", "http://loki_mcp:8080")
loki_client = MCPSseClient(LOKI_MCP_URL)

OPS_TOOLS = []
# Tools will be fetched asynchronously in create_agent()

# --- MCP Tools Cache (avoids 3 HTTP calls per request) ---
_tools_cache: list = []
_tools_cache_ts: float = 0.0
_TOOLS_CACHE_TTL = 300  # 5 minutes


async def _get_cached_tools() -> list:
    global _tools_cache, _tools_cache_ts
    import time
    if _tools_cache and (time.time() - _tools_cache_ts) < _TOOLS_CACHE_TTL:
        logger.info("[Ops] Using cached MCP tool definitions (%d tools).", len(_tools_cache))
        return _tools_cache
    logger.info("[Ops] Fetching MCP tool definitions from all services...")
    tools = (
        await drive_client.list_tools()
        + await market_client.list_tools()
        + await loki_client.list_tools()
    )
    _tools_cache = tools
    _tools_cache_ts = time.time()
    logger.info("[Ops] Cached %d MCP tools (TTL=%ds).", len(tools), _TOOLS_CACHE_TTL)
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
        logger.warning(f"Error fetching system prompt for Ops: {e}")
            
    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    
    OPS_TOOLS = await _get_cached_tools()
    
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
    
    return agent


async def run_agent_query(query: str, session_id: str | None = None) -> dict:
    from google.adk.runners import Runner
    import uuid
    import hashlib
    
    session_id = session_id or str(uuid.uuid4())
    session_service = get_session_service()

    # --- Semantic Cache Check (FinOps: évite les appels Gemini redondants) ---
    cache_key = f"semantic_cache:ops:{hashlib.sha256(query.encode('utf-8')).hexdigest()}"
    try:
        if getattr(session_service, 'r', None):
            cached = session_service.r.get(cache_key)
            if cached:
                import json as _json
                cached_data = _json.loads(cached)
                logger.info("FinOps: OPS Cache hit for query. Saved Gemini invocation.")
                return cached_data
    except Exception as e:
        logger.error(f"OPS Semantic Cache read error: {e}")

    agent = await create_agent(session_id)
    runner = Runner(app_name="zenika_ops_assistant", agent=agent, session_service=session_service)
    
    try:
        session = await session_service.get_session(app_name="zenika_ops_assistant", user_id="user_1", session_id=session_id)
        if session is None:
            raise KeyError("Session not found")
    except Exception:
        await session_service.create_session(app_name="zenika_ops_assistant", user_id="user_1", session_id=session_id)
    
    response_parts = []
    last_tool_data = None
    steps = []
    seen_steps = set()
    thoughts = []
    total_input_tokens = 0
    total_output_tokens = 0
    
    new_message = types.Content(role="user", parts=[types.Part(text=query)])
    
    async for event in runner.run_async(user_id="user_1", session_id=session_id, new_message=new_message):
        has_content = hasattr(event, 'content') and event.content is not None
        role_val = getattr(event.content, 'role', "").lower() if has_content else ""
        is_assistant = role_val in ["assistant", "model", "assistant_zenika_ops"]
        
        if has_content:
            for part in (list(event.content.parts) if hasattr(event.content, 'parts') else []):
                if getattr(part, 'thought', None):
                    thoughts.append(str(part.thought))
                
                # Track function calls (tool invocations) for observability
                tcall = getattr(part, 'tool_call', None) or getattr(part, 'function_call', None)
                if tcall:
                    for call in (tcall if isinstance(tcall, list) else [tcall]):
                        name = getattr(call, 'name', 'unknown')
                        args = getattr(call, 'args', {})
                        sig = f"call:{name}:{json.dumps(args, sort_keys=True)}"
                        if sig not in seen_steps:
                            steps.append({"type": "call", "tool": name, "args": args})
                            seen_steps.add(sig)
                
                fres = getattr(part, 'function_response', None)
                if fres:
                    res_data = getattr(fres, 'response', fres)
                    if hasattr(res_data, 'model_dump'): res_data = res_data.model_dump()
                    elif hasattr(res_data, 'dict'): res_data = res_data.dict()
                    
                    if isinstance(res_data, dict) and "result" in res_data and isinstance(res_data["result"], str) and res_data["result"].startswith("{"):
                        try: res_data = json.loads(res_data["result"])
                        except: pass
                    
                    sig = f"result:{json.dumps(res_data, sort_keys=True)}"
                    if sig not in seen_steps:
                        last_tool_data = res_data # Bubble up the last fetched data
                        steps.append({"type": "result", "data": res_data})
                        seen_steps.add(sig)
        
        if has_content and is_assistant:
            if isinstance(event.content, str):
                response_parts.append(event.content)
            elif hasattr(event.content, 'parts'):
                for part in event.content.parts:
                    if getattr(part, 'text', None) and not getattr(part, 'tool_call', None) and not getattr(part, 'thought', None):
                        response_parts.append(part.text)
        
        u = getattr(event.response, 'usage_metadata', None) if hasattr(event, 'response') else getattr(event, 'usage_metadata', None)
        if u:
            it = getattr(u, 'prompt_token_count', 0) or (u.get('prompt_token_count', 0) if isinstance(u, dict) else 0)
            ot = getattr(u, 'candidates_token_count', 0) or (u.get('candidates_token_count', 0) if isinstance(u, dict) else 0)
            total_input_tokens = max(total_input_tokens, it)
            total_output_tokens = max(total_output_tokens, ot)
    
    response_text = "".join(response_parts)
    
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

    # --- Cache Write (24h TTL) ---
    try:
        if getattr(session_service, 'r', None):
            session_service.r.set(cache_key, json.dumps(final_result), ex=86400)
    except Exception:
        pass

    return final_result
