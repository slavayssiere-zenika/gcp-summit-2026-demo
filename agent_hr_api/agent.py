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


# --- MCP Clients Initialization for HR ---
from mcp_client import MCPHttpClient, MCPSseClient

USERS_API_URL = os.getenv("USERS_API_URL", "http://users_api:8000")
ITEMS_API_URL = os.getenv("ITEMS_API_URL", "http://items_api:8000")
COMPETENCIES_API_URL = os.getenv("COMPETENCIES_API_URL", "http://comp-api:8000")
CV_API_URL = os.getenv("CV_API_URL", "http://cv_api:8000")
MISSIONS_API_URL = os.getenv("MISSIONS_API_URL", "http://missions_api:8000")

# Note: Each of these clients uses auth_header_var from mcp_client.py seamlessly.
users_client = MCPHttpClient(f"{USERS_API_URL}/mcp/query")
items_client = MCPHttpClient(f"{ITEMS_API_URL}/mcp/query")
comp_client = MCPHttpClient(f"{COMPETENCIES_API_URL}/mcp/query")
cv_client = MCPHttpClient(f"{CV_API_URL}/mcp/query")
missions_client = MCPHttpClient(f"{MISSIONS_API_URL}/mcp/query")

HR_TOOLS = []
# Tools will be fetched asynchronously in create_agent()

async def create_agent(session_id: str | None = None):
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
        logger.warning(f"Error fetching system prompt for HR: {e}")
            
    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    
    USERS_TOOLS = await users_client.list_tools()
    ITEMS_TOOLS = await items_client.list_tools()
    COMPETENCIES_TOOLS = await comp_client.list_tools()
    CV_TOOLS = await cv_client.list_tools()
    MISSIONS_TOOLS = await missions_client.list_tools()
    
    HR_TOOLS = USERS_TOOLS + ITEMS_TOOLS + COMPETENCIES_TOOLS + CV_TOOLS + MISSIONS_TOOLS
    
    agent = Agent(
        name="assistant_zenika_hr",
        model=model,
        generate_content_config=types.GenerateContentConfig(
            http_options=types.HttpOptions(
                retry_options=types.HttpRetryOptions(initial_delay=1, attempts=2),
            ) # Remove tool_config strictly forcing functions, HR might just respond text
        ),
        instruction=instruction_text,
        description="Le module spécialisé dans les ressources humaines et le staffing.",
        tools=HR_TOOLS
    )
    
    return agent


async def run_agent_query(query: str, session_id: str | None = None) -> dict:
    from google.adk.runners import Runner
    import uuid
    import hashlib
    
    session_id = session_id or str(uuid.uuid4())
    session_service = get_session_service()

    agent = await create_agent(session_id)
    runner = Runner(app_name="zenika_hr_assistant", agent=agent, session_service=session_service)
    
    try:
        session = await session_service.get_session(app_name="zenika_hr_assistant", user_id="user_1", session_id=session_id)
        if session is None:
            raise KeyError("Session not found")
    except Exception:
        await session_service.create_session(app_name="zenika_hr_assistant", user_id="user_1", session_id=session_id)
    
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
        is_assistant = role_val in ["assistant", "model", "assistant_zenika_hr"]
        
        if has_content:
            for part in (list(event.content.parts) if hasattr(event.content, 'parts') else []):
                if getattr(part, 'thought', None):
                    thoughts.append(str(part.thought))
                
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

    return {
        "response": response_text,
        "data": last_tool_data
    }
