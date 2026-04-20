import logging
import os
import re
import json
import inspect
import time
from typing import Optional
from contextlib import asynccontextmanager

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response, Depends, APIRouter
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from jose import jwt, JWTError

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.propagate import inject, extract
from opentelemetry.trace import SpanKind
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor

if os.getenv("TRACE_EXPORTER", "grpc") == "http":
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
elif os.getenv("TRACE_EXPORTER", "grpc") == "gcp":
    from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
else:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

import asyncio

from prometheus_fastapi_instrumentator import Instrumentator
from metrics import AGENT_QUERIES_TOTAL, AGENT_TOOL_CALLS_TOTAL
from agent import run_agent_query, get_session_service
from logger import setup_logging, LoggingMiddleware
from mcp_client import auth_header_var
from semantic_cache import SemanticCache

# SEC-F06 — Singleton du cache sémantique (instancié au démarrage)
_semantic_cache: SemanticCache = SemanticCache()

provider = TracerProvider(
    resource=Resource.create({
        ResourceAttributes.SERVICE_NAME: "agent-router-api",
        ResourceAttributes.SERVICE_VERSION: "1.0.0",
    })
)
if os.getenv("TRACE_EXPORTER", "grpc") == "gcp":
    provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))
else:
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter() if os.getenv("TRACE_EXPORTER", "grpc") == "http" else OTLPSpanExporter(insecure=True)))
trace.set_tracer_provider(provider)

tracer = trace.get_tracer(__name__)


setup_logging()
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting ADK Web Agent with Gemini...")
    yield

app = FastAPI(
    title="ADK Router Agent (A2A)",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
    root_path=os.getenv("ROOT_PATH", "")
)
app.add_middleware(LoggingMiddleware)
Instrumentator().instrument(app).expose(app)
FastAPIInstrumentor.instrument_app(app, excluded_urls="health,health/agents,metrics")
RedisInstrumentor().instrument()
HTTPXClientInstrumentor().instrument()




@app.get("/")
async def root():
    return {"message": "Router Agent API - Use /query for interactions"}


class QueryRequest(BaseModel):
    query: str
    session_id: Optional[str] = None


from mcp_client import auth_header_var
from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY must be set in environment variables")
# Purge the secret from environment to prevent Agent/LLM from reading it via os.environ dumps
os.environ.pop("SECRET_KEY", None)
ALGORITHM = "HS256"

from fastapi import APIRouter
protected_router = APIRouter(dependencies=[Depends(security)])

@protected_router.get("/spec")
async def get_spec():
    try:
        with open("spec.md", "r", encoding="utf-8") as f:
            return Response(content=f.read(), media_type="text/markdown")
    except Exception:
        return Response(content="# Specification introuvable", media_type="text/markdown")

@protected_router.post("/query")
async def query(request: QueryRequest, http_request: Request, auth: HTTPAuthorizationCredentials = Depends(security)):
    auth_header = f"{auth.scheme} {auth.credentials}"
    
    # Store the authorization header securely in the contextvar so mcp_client.py can read it
    auth_header_var.set(auth_header)
    
    try:
        from jose import jwt, JWTError
        payload = jwt.decode(auth.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        # Priorité au session_id du body (permet aux tests d'utiliser des sessions isolées)
        # Fallback sur le sub JWT pour les sessions utilisateurs normales
        body_session_id = request.session_id if request.session_id else None
        jwt_sub = payload.get("sub")
        computed_session_id = body_session_id if body_session_id else jwt_sub
        if not computed_session_id:
            raise HTTPException(status_code=401, detail="Token invalide")
    except Exception:
        raise HTTPException(status_code=401, detail="Token invalide")
        
    ctx = extract(http_request.headers)
    
    with tracer.start_as_current_span("query.process", context=ctx, kind=SpanKind.SERVER) as span:
        trace_id = format(span.get_span_context().trace_id, '032x')
        span.set_attribute("trace.id", trace_id)
        span.set_attribute("query.text", request.query)
        span.set_attribute("session.id", computed_session_id)
        
        try:
            AGENT_QUERIES_TOTAL.inc()
            # Propager le sub JWT comme user_id (FinOps tracing + session isolation)
            jwt_user_id = jwt_sub or "unknown@zenika.com"

            # SEC-F06 — Tentative de cache sémantique AVANT l'appel LLM
            cached_response = await _semantic_cache.get(request.query)
            if cached_response is not None:
                span.set_attribute("agent.source", "semantic_cache")
                span.set_attribute("semantic_cache.hit", True)
                # Log BigQuery en fire-and-forget (coût zéro pour l'utilisateur)
                async def _log_cache_hit_bq():
                    try:
                        market_url = os.getenv("MARKET_MCP_URL", "http://market_mcp:8080")
                        headers_bq = {"Authorization": auth_header}
                        inject(headers_bq)
                        async with httpx.AsyncClient(timeout=10.0) as bq_client:
                            await bq_client.post(f"{market_url.rstrip('/')}/mcp/call", json={
                                "name": "log_ai_consumption",
                                "arguments": {
                                    "user_email": jwt_user_id,
                                    "action": "semantic_cache_hit",
                                    "model": os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"),
                                    "input_tokens": 0,
                                    "output_tokens": 0,
                                    "metadata": {"query": request.query[:100], "cache_hit": True}
                                }
                            }, headers=headers_bq)
                    except Exception:
                        pass
                asyncio.create_task(_log_cache_hit_bq())
                return cached_response

            result = await run_agent_query(request.query, computed_session_id, auth_token=auth_header, user_id=jwt_user_id)
            span.set_attribute("agent.source", result.get("source", "unknown"))

            # SEC-F06 — Stockage du résultat en cache (fire-and-forget, ne bloque pas la réponse)
            asyncio.create_task(_semantic_cache.set(request.query, result))

            return result
            
        except Exception as e:
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(e))
            return {"response": f"Erreur: {str(e)}", "source": "error"}

@protected_router.get("/history")
async def get_history(auth: HTTPAuthorizationCredentials = Depends(security)):
    try:
        from jose import jwt, JWTError
        payload = jwt.decode(auth.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        session_id = payload.get("sub")
        jwt_user_id = payload.get("sub", "user_1")
        if not session_id:
            raise Exception("No user")
    except Exception:
        raise HTTPException(status_code=401, detail="Token invalide")
        
    from agent import get_session_service
    session_service = get_session_service()
    session = await session_service.get_session(
        app_name="zenika_assistant", 
        user_id=jwt_user_id,
        session_id=session_id
    )
    if not session:
        return {"history": []}
        
    history = []
    current_assistant_msg = None
    
    for event in getattr(session, "events", []):
        author = getattr(event, "author", None)
        content = getattr(event, "content", "")
        role = getattr(content, "role", None) if content else None
        
        # Normalize role
        author_val = (author or "").lower()
        role_val = (role or "").lower()
        
        is_assistant = any(x in ["assistant", "model", "assistant_zenika"] for x in [author_val, role_val])
        is_tool = any(x in ["tool", "function"] for x in [author_val, role_val])
        is_user = any(x in ["user"] for x in [author_val, role_val]) and not is_tool and not is_assistant
        
        # Extract parts if available
        parts = []
        if hasattr(content, "parts"):
            parts = list(content.parts) if content.parts else []
            content_text = "".join((getattr(p, "text", "") or "") for p in parts if hasattr(p, "text"))
        else:
            content_text = str(content)
            
            
        # 1. Main turn logic (Grouping/Initialization)
        if is_user:
            # Avoid adding empty user messages that might come from system/tool noise
            if content_text.strip():
                history.append({
                    "role": "user",
                    "content": content_text
                })
                current_assistant_msg = None 
            
        elif is_assistant and current_assistant_msg is None:
            current_assistant_msg = {
                "role": "assistant",
                "content": "",
                "displayType": "text_only",
                "data": None,
                "parsedData": [],
                "steps": [],
                "thoughts": "",
                "rawResponse": "",
                "activeTab": "preview",
                "pagination": {"currentPage": 1, "itemsPerPage": 10}
            }
            current_assistant_seen_steps = set()
            history.append(current_assistant_msg)


        # 2. Process EVERY event exhaustively for metadata (Chain of Thought, Tool Calls, Results)
        if current_assistant_msg:
            # a) Scan Parts
            for part in parts:
                # Thoughts (Gemini 2.0 Thinking)
                thought_val = getattr(part, 'thought', None)
                if thought_val:
                    thought_text = ""
                    if isinstance(thought_val, bool) and thought_val:
                        thought_text = getattr(part, 'text', "")
                    else:
                        thought_text = str(thought_val)
                    
                    if thought_text:
                        if current_assistant_msg["thoughts"]:
                            current_assistant_msg["thoughts"] += "\n" + thought_text
                        else:
                            current_assistant_msg["thoughts"] = thought_text
                
                # Tool Calls
                tcall = getattr(part, 'tool_call', None) or getattr(part, 'function_call', None)
                if tcall:
                    calls = tcall if isinstance(tcall, list) else [tcall]
                    for call in calls:
                        name = getattr(call, 'name', 'unknown')
                        args = getattr(call, 'args', {})
                        sig = f"call:{name}:{json.dumps(args, sort_keys=True)}"
                        if sig not in current_assistant_seen_steps:
                            current_assistant_msg["steps"].append({
                                "type": "call",
                                "tool": name,
                                "args": args
                            })
                            current_assistant_seen_steps.add(sig)
                
                # Tool Results
                fres = getattr(part, 'function_response', None)
                raw_text = getattr(part, 'text', None)
                
                res_to_process = None
                if fres:
                    res_to_process = getattr(fres, 'response', fres)
                elif raw_text and role_val in ["tool", "user"]:
                    try: res_to_process = json.loads(raw_text)
                    except: pass
                
                if res_to_process is not None:
                    if hasattr(res_to_process, 'model_dump'): res_to_process = res_to_process.model_dump()
                    elif hasattr(res_to_process, 'dict'): res_to_process = res_to_process.dict()
                    
                    # Unwrap MCP 'result' JSON string (Crucial for sub-agent data access)
                    if isinstance(res_to_process, dict) and "result" in res_to_process and isinstance(res_to_process["result"], str) and res_to_process["result"].startswith("{"):
                        try: res_to_process = json.loads(res_to_process["result"])
                        except: pass

                    # A2A Unwrapping (Router Specific)
                    if isinstance(res_to_process, dict) and "response" in res_to_process:
                        if res_to_process.get("thoughts"):
                            if current_assistant_msg["thoughts"]:
                                current_assistant_msg["thoughts"] += f"\n[Sub-Agent] {res_to_process['thoughts']}"
                            else:
                                current_assistant_msg["thoughts"] = f"[Sub-Agent] {res_to_process['thoughts']}"
                        
                        for s in res_to_process.get("steps", []):
                            current_assistant_msg["steps"].append(s)
                            
                        # FinOps Aggregation
                        sub_use = res_to_process.get("usage", {})
                        if "usage" not in current_assistant_msg:
                            current_assistant_msg["usage"] = {"total_input_tokens": 0, "total_output_tokens": 0, "estimated_cost_usd": 0}
                        current_assistant_msg["usage"]["total_input_tokens"] += sub_use.get("total_input_tokens", 0)
                        current_assistant_msg["usage"]["total_output_tokens"] += sub_use.get("total_output_tokens", 0)
                        current_assistant_msg["data"] = res_to_process.get("data") or res_to_process
                    
                    # Unwrap MCP 'result' JSON string
                    if isinstance(res_to_process, dict) and "result" in res_to_process and isinstance(res_to_process["result"], str) and res_to_process["result"].startswith("{"):
                        try: res_to_process = json.loads(res_to_process["result"])
                        except: pass
                    
                    sig = f"result:{json.dumps(res_to_process, sort_keys=True)}"
                    if sig not in current_assistant_seen_steps:
                        if not current_assistant_msg["data"]:
                            current_assistant_msg["data"] = res_to_process
                        current_assistant_msg["steps"].append({"type": "result", "data": res_to_process})
                        current_assistant_seen_steps.add(sig)
            
            
            # c) Extract Usage/Tokens (FinOps)
            u = None
            if hasattr(event, 'response') and event.response and hasattr(event.response, 'usage_metadata'):
                u = event.response.usage_metadata
            elif hasattr(event, 'usage_metadata'):
                u = event.usage_metadata
                
            if u:
                if "usage" not in current_assistant_msg:
                    current_assistant_msg["usage"] = {"total_input_tokens": 0, "total_output_tokens": 0, "estimated_cost_usd": 0}
                
                # ADK usage_metadata can be cumulative or turn-based
                it = getattr(u, 'prompt_token_count', 0) or (u.get('prompt_token_count', 0) if isinstance(u, dict) else 0)
                ot = getattr(u, 'candidates_token_count', 0) or (u.get('candidates_token_count', 0) if isinstance(u, dict) else 0)
                
                # We track the max seen for the turn as it's typically cumulative in GenerateContentResponse
                current_assistant_msg["usage"]["total_input_tokens"] = max(current_assistant_msg["usage"]["total_input_tokens"], it)
                current_assistant_msg["usage"]["total_output_tokens"] = max(current_assistant_msg["usage"]["total_output_tokens"], ot)
                
                # Recalculate estimated cost
                ti = current_assistant_msg["usage"]["total_input_tokens"]
                to = current_assistant_msg["usage"]["total_output_tokens"]
                current_assistant_msg["usage"]["estimated_cost_usd"] = round(ti * 0.000000075 + to * 0.0000003, 6)

        # 3. Process Content Text
        if is_assistant and content_text:
            full_raw = current_assistant_msg.get("_full_text_progress", "") + content_text
            current_assistant_msg["_full_text_progress"] = full_raw
            current_assistant_msg["rawResponse"] = full_raw
            
            # Robust JSON Dashboard Extraction (Non-Destructive)
            try:
                json_match = re.search(r'\{[\s\S]*\}', full_raw)
                if json_match:
                    json_str = json_match.group(0)
                    json_obj = json.loads(json_str)
                    if "reply" in json_obj and "display_type" in json_obj:
                        # Replace the JSON block with its 'reply' text in the visible content
                        reply = json_obj.get("reply", "")
                        current_assistant_msg["content"] = full_raw.replace(json_str, reply).strip()
                        current_assistant_msg["displayType"] = json_obj["display_type"]
                        if current_assistant_msg["displayType"] == "profile":
                            current_assistant_msg["displayType"] = "cards"
                        
                        if "data" in json_obj:
                            current_assistant_msg["data"] = json_obj["data"]
                    else:
                        current_assistant_msg["content"] = full_raw
                else:
                    current_assistant_msg["content"] = full_raw
            except: 
                current_assistant_msg["content"] = full_raw

            # Re-evaluate parsedData and displayType fallback
            if current_assistant_msg.get("data"):
                d = current_assistant_msg["data"]
                
                # Competency detection
                if isinstance(d, dict) and d.get("dataType") == "competency":
                    current_assistant_msg["displayType"] = "tree"
                # Fallback to cards if we have data but no type
                elif current_assistant_msg["displayType"] == "text_only":
                    current_assistant_msg["displayType"] = "cards"

                # Update parsedData
                if isinstance(d, dict) and "items" in d:
                    current_assistant_msg["parsedData"] = d["items"]
                elif isinstance(d, list):
                    current_assistant_msg["parsedData"] = d
                else:
                    current_assistant_msg["parsedData"] = [d]

            
    # Clean up internal progress field and empty ghost messages
    final_history = []
    for msg in history:
        if isinstance(msg, dict):
            msg.pop("_full_text_progress", None)
            
            if msg.get("role") == "assistant" and not msg.get("content") and not msg.get("steps") and not msg.get("data"):
                continue # Skip completely empty ghost messages
                
            final_history.append(msg)
            
    return {"history": final_history}

@protected_router.delete("/history")
async def delete_history(auth: HTTPAuthorizationCredentials = Depends(security)):
    try:
        from jose import jwt, JWTError
        payload = jwt.decode(auth.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        session_id = payload.get("sub")
        jwt_user_id = payload.get("sub", "user_1")
        if not session_id:
            raise Exception("No user")
    except Exception:
        raise HTTPException(status_code=401, detail="Token invalide")
        
    from agent import get_session_service
    session_service = get_session_service()
    session = await session_service.get_session(
        app_name="zenika_assistant", 
        user_id=jwt_user_id,
        session_id=session_id
    )
    if session:
        session_service._delete_session_impl(app_name="zenika_assistant", user_id=jwt_user_id, session_id=session_id)
        return {"message": "Historique effacé"}
    else:
        return {"message": "Pas d'historique"}

def get_tool_metadata(tools_list):
    metadata = []
    for tool in tools_list:
        # If it's a function, get its details
        doc = inspect.getdoc(tool) or "No description available"
        sig = inspect.signature(tool)
        params = []
        for name, param in sig.parameters.items():
            params.append({
                "name": name,
                "type": str(param.annotation) if param.annotation != inspect.Parameter.empty else "any",
                "default": str(param.default) if param.default != inspect.Parameter.empty else None,
                "required": param.default == inspect.Parameter.empty
            })
        
        metadata.append({
            "name": tool.__name__,
            "description": doc,
            "parameters": params
        })
    return metadata


USERS_API_URL = os.getenv("USERS_API_URL", "http://users_api:8000")

@app.post("/login")
async def login(request: Request, response: Response):
    data = await request.json()
    headers = {}
    inject(headers)
    async with httpx.AsyncClient() as client:
        res = await client.post(f"{USERS_API_URL}/login", json=data, headers=headers)
        if res.status_code != 200:
            raise HTTPException(status_code=res.status_code, detail=res.json().get("detail", "Erreur de connexion"))
        
        # Forward the cookie from users_api to the client
        for name, value in res.cookies.items():
            response.set_cookie(key=name, value=value, httponly=True, samesite="lax")
        
        return res.json()

@app.post("/logout")
async def logout(response: Response):
    async with httpx.AsyncClient() as client:
        # res = await client.post(f"{USERS_API_URL}/logout")
        response.delete_cookie("access_token")
        return {"message": "Déconnecté"}

@app.get("/me")
async def get_me(request: Request):
    headers = {}
    inject(headers)
    async with httpx.AsyncClient() as client:
        # Forward the incoming cookie to users_api
        cookies = request.cookies
        res = await client.get(f"{USERS_API_URL}/me", cookies=cookies, headers=headers)
        if res.status_code != 200:
            raise HTTPException(status_code=res.status_code, detail="Non connecté")
        return res.json()


# Configuration centralisée des services MCP de l'écosystème
# Sert à la fois pour le registre (/mcp/registry) et pour le proxy (/mcp/proxy)
MCP_SERVICES_CONFIG = [
    {"id": "users",        "name": "Users API",           "env": "USERS_API_URL"},
    {"id": "items",        "name": "Items API",           "env": "ITEMS_API_URL"},
    {"id": "drive",        "name": "Drive API",           "env": "DRIVE_API_URL"},
    {"id": "competencies", "name": "Competencies API",    "env": "COMPETENCIES_API_URL"},
    {"id": "cv",           "name": "CV API",              "env": "CV_API_URL"},
    {"id": "missions",     "name": "Missions API",        "env": "MISSIONS_API_URL"},
    {"id": "market",       "name": "Market & FinOps MCP", "env": "MARKET_MCP_URL"},
]

@protected_router.get("/mcp/registry")
async def mcp_registry(auth: HTTPAuthorizationCredentials = Depends(security)):
    """
    Renvoie la liste consolidée de tous les tools MCP de l'écosystème.
    Chaque service MCP expose GET /mcp/tools. On les agrège en parallèle.
    """
    import asyncio
    from agent import ROUTER_TOOLS

    auth_header = f"{auth.scheme} {auth.credentials}"

    async def fetch_tools(svc_config: dict) -> dict:
        base_url = os.getenv(svc_config["env"], "")
        if not base_url:
            return {"id": svc_config["id"], "name": svc_config["name"], "tools": [], "error": "URL non configurée"}

        headers = {"Authorization": auth_header}
        inject(headers)
        url = f"{base_url.rstrip('/')}/mcp/tools"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    raw_tools = res.json()
                    # Normalise la structure: les tools peuvent avoir inputSchema ou parameters
                    tools = []
                    for t in raw_tools:
                        params = []
                        schema = t.get("inputSchema", {})
                        properties = schema.get("properties", {})
                        required_fields = schema.get("required", [])
                        for pname, pdef in properties.items():
                            params.append({
                                "name": pname,
                                "type": pdef.get("type", "any"),
                                "default": pdef.get("default", None),
                                "required": pname in required_fields,
                            })
                        tools.append({
                            "name": t.get("name", ""),
                            "description": t.get("description", ""),
                            "parameters": params,
                        })
                    return {"id": svc_config["id"], "name": svc_config["name"], "tools": tools}
                else:
                    return {"id": svc_config["id"], "name": svc_config["name"], "tools": [], "error": f"HTTP {res.status_code}"}
        except Exception as e:
            return {"id": svc_config["id"], "name": svc_config["name"], "tools": [], "error": str(e)}

    # Agrégation parallèle + router lui-même
    results = await asyncio.gather(*[fetch_tools(s) for s in MCP_SERVICES_CONFIG])

    # Ajouter le Router agent en premier (ses tools sont locaux, pas besoin d'appel HTTP)
    router_service = {
        "id": "router",
        "name": "Router Agent (Orchestrator)",
        "tools": get_tool_metadata(ROUTER_TOOLS)
    }

    all_services = [router_service] + list(results)
    return {"services": all_services}


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/version")
async def get_version():
    return {"version": os.getenv("APP_VERSION", "unknown")}


@app.get("/health/agents")
async def health_agents():
    """ADR12-5 — Agrège la santé des 3 sous-agents (HR, Ops, Missions).

    Public (pas de JWT). Appelé par le frontend au démarrage pour adapter l'UI.
    Sonde GET /health + GET /version de chaque sous-agent en parallèle (timeout 3s).

    Returns:
        200 + {status: "healthy"|"degraded"}  si au moins 1 agent répond
        503 + {status: "unhealthy"}             si tous les agents sont KO
    """
    from metrics import AGENT_HEALTH_PROBE_TOTAL

    _AGENTS = {
        "hr":       os.getenv("AGENT_HR_API_URL",       "http://agent_hr_api:8080"),
        "ops":      os.getenv("AGENT_OPS_API_URL",      "http://agent_ops_api:8080"),
        "missions": os.getenv("AGENT_MISSIONS_API_URL", "http://agent_missions_api:8080"),
    }

    async def _probe(agent_name: str, base_url: str) -> dict:
        start = time.monotonic()
        ok = False
        version = "unknown"
        try:
            async with httpx.AsyncClient(timeout=3.0) as c:
                # /health et /version en parallèle sur le même sous-agent
                h_res, v_res = await asyncio.gather(
                    c.get(f"{base_url.rstrip('/')}/health"),
                    c.get(f"{base_url.rstrip('/')}/version"),
                    return_exceptions=True,
                )
            if not isinstance(h_res, Exception) and h_res.status_code == 200:
                ok = True
            if not isinstance(v_res, Exception) and v_res.status_code == 200:
                version = v_res.json().get("version", "unknown")
        except Exception:
            ok = False
        finally:
            latency_ms = round((time.monotonic() - start) * 1000)
            status = "up" if ok else "down"
            AGENT_HEALTH_PROBE_TOTAL.labels(agent=agent_name, status=status).inc()
        return {
            "name": agent_name,
            "status": status,
            "version": version,
            "latency_ms": latency_ms,
        }

    results = await asyncio.gather(*[_probe(n, u) for n, u in _AGENTS.items()])
    agents_detail = {r["name"]: {k: v for k, v in r.items() if k != "name"} for r in results}

    up_count = sum(1 for r in results if r["status"] == "up")
    if up_count == len(_AGENTS):
        agg_status = "healthy"
    elif up_count > 0:
        agg_status = "degraded"
    else:
        agg_status = "unhealthy"

    http_code = 200 if up_count > 0 else 503
    return JSONResponse(
        content={"status": agg_status, "agents": agents_detail},
        status_code=http_code,
    )


@protected_router.api_route("/mcp/proxy/{server_name}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_mcp(server_name: str, path: str, request: Request, auth: HTTPAuthorizationCredentials = Depends(security)):
    # Normalisation du nom (market-mcp -> market, items_api -> items)
    normalized_name = server_name.lower().replace("-", "_").replace("_api", "").replace("_mcp", "")
    
    # Recherche du service dans la config globale
    svc = next((s for s in MCP_SERVICES_CONFIG if s["id"] == normalized_name or s["id"] == server_name), None)
    
    base_url = None
    if svc:
        base_url = os.getenv(svc["env"])
    
    # Fallback si non trouvé dans la liste statique (tente un mapping direct prédictible)
    if not base_url:
        env_var_name = f"{normalized_name.upper()}_API_URL"
        base_url = os.getenv(env_var_name)
    
    if not base_url:
        raise HTTPException(status_code=404, detail=f"MCP Server {server_name} (ID: {normalized_name}) introuvable ou variable d'env manquante")
        
    auth_header = f"{auth.scheme} {auth.credentials}"
    headers = {"Authorization": auth_header}
    inject(headers)
    
    body = await request.body()
    target_path = f"{base_url.rstrip('/')}/{path}"
    query_params = request.url.query
    if query_params:
        target_path += "?" + query_params
        
    async with httpx.AsyncClient() as client:
        try:
            res = await client.request(
                method=request.method,
                url=target_path,
                headers=headers,
                content=body,
                timeout=300.0
            )
            # Propagation de certains headers importants mais filtrage du content-length (httpx le regénère)
            resp_headers = {k: v for k, v in res.headers.items() if k.lower() not in ["content-length", "content-encoding", "transfer-encoding"]}
            return Response(content=res.content, status_code=res.status_code, headers=resp_headers)
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Erreur de communication avec {server_name}: {str(exc)}")



app.include_router(protected_router)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)
