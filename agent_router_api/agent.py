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


# --- A2A Protocol Tools ---

async def ask_hr_agent(query: str) -> dict:
    """
    Délègue une requête à l'Agent RH (Talent Acquisition & Staffing).
    Utiliser cet outil si l'utilisateur pose une question concernant:
    - La recherche de candidats ou profils.
    - L'analyse ou la lecture de CVs (notamment via un lien Google Drive).
    - La création ou la gestion de missions (staffing, sélection d'équipe).
    - Les utilisateurs internes ou les compétences (Tree).
    
    Args:
        query (str): La requête détaillée, claire et complète à transmettre à l'Agent RH. Reformule bien pour qu'il ait tout le contexte sans ambiguïté.
    """
    from mcp_client import auth_header_var
    
    hr_url = os.getenv("AGENT_HR_API_URL", "http://agent_hr_api:8080")
    
    headers = {}
    inject(headers) # Inject OTel traces
    auth = auth_header_var.get(None)
    if auth:
        headers["Authorization"] = auth
        
    try:
        logger.info(f"[A2A] Dispatching query to HR Agent: {query[:50]}...")
        async with httpx.AsyncClient(timeout=60.0, headers=headers) as client:
            res = await client.post(f"{hr_url.rstrip('/')}/a2a/query", json={"query": query})
            res.raise_for_status()
            data = res.json()
            return {"result": json.dumps({
                "agent": "hr_agent",
                "response": data.get("response"),
                "data": data.get("data"),
                "steps": data.get("steps", []),
                "thoughts": data.get("thoughts", ""),
                "usage": data.get("usage", {})
            })}
    except Exception as e:
        logger.error(f"[A2A] HR Agent error: {e}")
        return {"result": f"Échec de communication avec l'Agent RH: {str(e)}"}


async def ask_ops_agent(query: str) -> dict:
    """
    Délègue une requête à l'Agent Ops (FinOps, Système & Drive Integration).
    Utiliser cet outil UNIQUEMENT si l'utilisateur pose une question concernant:
    - La santé du système, la topologie ou l'architecture technique GCP.
    - Le FinOps, la facture IA, l'estimation des coûts, le marché.
    - La modification de la configuration système de parsing Google Drive (dossiers synchronisés).
    - L'exploration technique de logs bruts Applicatifs avec Grafana/Loki.
    
    Args:
        query (str): La requête ou la commande technique à envoyer à l'Agent Ops.
    """
    from mcp_client import auth_header_var
    
    ops_url = os.getenv("AGENT_OPS_API_URL", "http://agent_ops_api:8080")
    
    headers = {}
    inject(headers)
    auth = auth_header_var.get(None)
    if auth:
        headers["Authorization"] = auth
        
    try:
        logger.info(f"[A2A] Dispatching query to Ops Agent: {query[:50]}...")
        async with httpx.AsyncClient(timeout=60.0, headers=headers) as client:
            res = await client.post(f"{ops_url.rstrip('/')}/a2a/query", json={"query": query})
            res.raise_for_status()
            data = res.json()
            return {"result": json.dumps({
                "agent": "ops_agent",
                "response": data.get("response"),
                "data": data.get("data"),
                "steps": data.get("steps", []),
                "thoughts": data.get("thoughts", ""),
                "usage": data.get("usage", {})
            })}
    except Exception as e:
        logger.error(f"[A2A] Ops Agent error: {e}")
        return {"result": f"Échec de communication avec l'Agent Ops: {str(e)}"}


ROUTER_TOOLS = [ask_hr_agent, ask_ops_agent]


async def create_agent(session_id: str | None = None):
    prompts_api_url = os.getenv("PROMPTS_API_URL", "http://prompts_api:8000")
    instruction_text = "Tu es l'Orchestrateur Principal de la plateforme Zenika, le 'Front-Desk'. Ton rôle est de diriger la demande vers le hub approprié en utilisant tes outils de délégation (A2A). Ne dis pas 'je vais interroger mon collègue', sois direct."
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(f"{prompts_api_url}/prompts/agent_router_api.system_instruction")
            if res.status_code == 200:
                instruction_text = res.json()["value"]
            else:
                # Fallback to the old one before seed_data is re-run
                res_fallback = await client.get(f"{prompts_api_url}/prompts/agent_api.assistant_system_instruction")
                if res_fallback.status_code == 200:
                    instruction_text = res_fallback.json()["value"] + "\n\nCRITICAL DIRECTIVE: Use ONLY A2A tools (ask_hr_agent, ask_ops_agent) as you do not have direct tools."
    except Exception as e:
        logger.warning(f"Error fetching system prompt: {e}")
        
    if session_id and session_id != "anon":
        try:
            from mcp_client import auth_header_var
            auth_header = auth_header_var.get()
            headers = {"Authorization": auth_header} if auth_header else {}
            async with httpx.AsyncClient() as client:
                res = await client.get(f"{prompts_api_url}/prompts/user_{session_id}", headers=headers, timeout=5.0)
                if res.status_code == 200:
                    user_prompt = res.json().get("value", "")
                    if user_prompt:
                        instruction_text += f"\n\n--- INSTRUCTIONS UTILISATEUR ({session_id}) ---\n{user_prompt}\n------------------------------------------------------------"
        except Exception:
            pass
            
    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    
    agent = Agent(
        name="assistant_zenika_router",
        model=model,
        generate_content_config=types.GenerateContentConfig(
            http_options=types.HttpOptions(
                retry_options=types.HttpRetryOptions(initial_delay=1, attempts=2),
            )
        ),
        instruction=instruction_text,
        description="Le point d'entrée Frontend de Zenika qui délègue le travail via le protocole A2A.",
        tools=ROUTER_TOOLS
    )
    
    return agent


async def run_agent_query(query: str, session_id: str | None = None) -> dict:
    from google.adk.runners import Runner
    import uuid
    import hashlib
    
    session_id = session_id or str(uuid.uuid4())
    session_service = get_session_service()
    
    # --- Semantic Cache Check ---
    cache_key = f"semantic_cache:{hashlib.sha256(query.encode('utf-8')).hexdigest()}"
    try:
        if getattr(session_service, 'r', None):
            cached = session_service.r.get(cache_key)
            if cached:
                cached_data = json.loads(cached)
                logger.info(f"FinOps: Cache hit for query. Saved Gemini invocation.")
                return cached_data
    except Exception as e:
        logger.error(f"Semantic Cache read error: {e}")

    agent = await create_agent(session_id)
    runner = Runner(app_name="zenika_assistant", agent=agent, session_service=session_service)
    
    try:
        session = await session_service.get_session(app_name="zenika_assistant", user_id="user_1", session_id=session_id)
        if session is None:
            raise KeyError("Session not found")
    except Exception:
        await session_service.create_session(app_name="zenika_assistant", user_id="user_1", session_id=session_id)
    
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
        is_assistant = role_val in ["assistant", "model", "assistant_zenika_router"]
        
        if has_content:
            for part in (list(event.content.parts) if hasattr(event.content, 'parts') else []):
                if getattr(part, 'thought', None):
                    thoughts.append(str(part.thought))
                
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
                    
                    # Unpack the A2A response wrapped inside the A2A tool
                    if isinstance(res_data, dict) and "agent" in res_data and "data" in res_data:
                        last_tool_data = res_data.get("data") # Propagate inner tool data
                        # Merge sub-agent steps for full observability in the Router's history
                        if res_data.get("steps"):
                            steps.extend(res_data["steps"])
                        # Aggregate sub-agent token usage into the Router's total for accurate FinOps
                        sub_usage = res_data.get("usage") or {}
                        total_input_tokens += sub_usage.get("total_input_tokens", 0)
                        total_output_tokens += sub_usage.get("total_output_tokens", 0)
                        # Prepend sub-agent thoughts for Chain-of-Thought transparency
                        if res_data.get("thoughts"):
                            thoughts.insert(0, f"[{res_data.get('agent', 'sub-agent')}] {res_data['thoughts']}")
                        res_data = {"type": "a2a_delegation", "agent": res_data.get("agent"), "agent_response": res_data.get("response")}
                    
                    sig = f"result:{json.dumps(res_data, sort_keys=True)}"
                    if sig not in seen_steps:
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
    
    # As an orchestrator, we only log our own routing tokens to BigQuery
    # The sub-agents log their own token consumption (which fulfills FinOps perfectly!)
    if total_input_tokens > 0 or total_output_tokens > 0:
        try:
            user_email = session_id if "@" in str(session_id) else f"{session_id}@zenika.com"
            from mcp_client import auth_header_var
            auth_header = auth_header_var.get()
            # Market logging for Orchestrator...
            market_url = os.getenv("MARKET_MCP_URL", "http://api.internal.zenika/market-mcp/")
            headers = {"Authorization": auth_header} if auth_header else {}
            inject(headers)
            # Use lightweight fire-and-forget for orchestrator logging or direct HTTP
            import asyncio
            async def log_bq():
                try:
                    async with httpx.AsyncClient(timeout=10.0, headers=headers) as c:
                        await c.post(f"{market_url.rstrip('/')}/mcp/call", json={
                            "name": "log_ai_consumption",
                            "arguments": {
                                "user_email": user_email,
                                "action": "orchestrator_routing",
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
        "thoughts": "\n".join(thoughts),
        "data": last_tool_data,
        "steps": steps,
        "source": "adk_agent",
        "session_id": session_id,
        "usage": {
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "estimated_cost_usd": round(total_input_tokens * 0.000000075 + total_output_tokens * 0.0000003, 6)
        }
    }

    try:
        if getattr(session_service, 'r', None):
            session_service.r.set(cache_key, json.dumps(final_result), ex=86400)
    except Exception:
        pass
        
    return final_result
