import logging
import os
import re
import json
import inspect
from typing import Optional
from contextlib import asynccontextmanager

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response, Depends, APIRouter
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

from prometheus_fastapi_instrumentator import Instrumentator
from metrics import AGENT_QUERIES_TOTAL, AGENT_TOOL_CALLS_TOTAL
from agent import run_agent_query, OPS_TOOLS, get_session_service
from metadata import extract_metadata_from_session
from logger import setup_logging, LoggingMiddleware
from mcp_client import auth_header_var

provider = TracerProvider(
    resource=Resource.create({
        ResourceAttributes.SERVICE_NAME: "agent-ops-api",
        ResourceAttributes.SERVICE_VERSION: "1.0.0",
    })
)
if os.getenv("TRACE_EXPORTER", "grpc") == "gcp":
    provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))
else:
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter() if os.getenv("TRACE_EXPORTER", "grpc") == "http" else OTLPSpanExporter(insecure=True)))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(__name__)
app_logger = logging.getLogger(__name__)


setup_logging()
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting ADK Web Agent with Gemini...")
    yield

app = FastAPI(
    title="ADK Ops Agent (A2A)",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
    root_path=os.getenv("ROOT_PATH", "")
)
app.add_middleware(LoggingMiddleware)
Instrumentator().instrument(app).expose(app)
FastAPIInstrumentor.instrument_app(app, excluded_urls="health,metrics")
RedisInstrumentor().instrument()
HTTPXClientInstrumentor().instrument()




@app.get("/")
async def root():
    return {"message": "Ops Agent API - Use /a2a/query for interactions"}


class QueryRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None  # Prb 7: propagated from Router JWT to isolate sessions


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
    auth_header_var.set(auth_header)
    
    try:
        from jose import jwt, JWTError
        payload = jwt.decode(auth.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        computed_session_id = payload.get("sub")
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
            # Propager le sub JWT comme user_id pour le tracking FinOps
            jwt_user_id = payload.get("sub") or "unknown@zenika.com"
            result = await run_agent_query(request.query, computed_session_id, user_id=jwt_user_id)
            span.set_attribute("agent.source", result.get("source", "unknown"))
            return result
            
        except Exception as e:
            app_logger.exception("CRITICAL: Exception in /query (Ops)")
            return {"response": f"Erreur: {str(e)}", "source": "error"}

@protected_router.post("/a2a/query")
async def a2a_query(request: QueryRequest, http_request: Request, auth: HTTPAuthorizationCredentials = Depends(security)):
    # Standard A2A Entrypoint
    auth_header = f"{auth.scheme} {auth.credentials}"
    auth_header_var.set(auth_header)
    
    try:
        from jose import jwt, JWTError
        payload = jwt.decode(auth.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        computed_session_id = payload.get("sub")
    except Exception:
        raise HTTPException(status_code=401, detail="Token invalide")
    
    # Prb 7: Use the user_id propagated from Router if available, else fall back to JWT sub
    effective_user_id = request.user_id or computed_session_id or "user_1"
        
    ctx = extract(http_request.headers)
    with tracer.start_as_current_span("a2a.query", context=ctx, kind=SpanKind.SERVER) as span:
        try:
            result = await run_agent_query(request.query, computed_session_id, user_id=effective_user_id)
            return {
                "response": result.get("response", ""),
                "data": result.get("data"),
                "steps": result.get("steps", []),
                "thoughts": result.get("thoughts", ""),
                "usage": result.get("usage", {})
            }
        except Exception as e:
            app_logger.exception("CRITICAL: Exception in /a2a/query (Ops)")
            raise HTTPException(status_code=500, detail=str(e))

@protected_router.get("/history")
async def get_history(auth: HTTPAuthorizationCredentials = Depends(security)):
    try:
        from jose import jwt, JWTError
        payload = jwt.decode(auth.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        session_id = payload.get("sub")
        if not session_id:
            raise Exception("No user")
    except Exception:
        raise HTTPException(status_code=401, detail="Token invalide")
        
    from agent import get_session_service
    session_service = get_session_service()
    session = await session_service.get_session(
        app_name="zenika_ops_assistant", 
        user_id=session_id,  # sub JWT = user_id
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
            # Reconstruct metadata using the shared foolproof utility
            from metadata import extract_metadata_from_session
            meta = extract_metadata_from_session(session)
            
            current_assistant_msg = {
                "role": "assistant",
                "content": content_text,
                "displayType": "text_only",
                "data": meta.get("data"),
                "parsedData": [],
                "steps": meta.get("steps", []),
                "thoughts": meta.get("thoughts", ""),
                "rawResponse": content_text,
                "activeTab": "preview",
                "pagination": {"currentPage": 1, "itemsPerPage": 10}
            }
            history.append(current_assistant_msg)


            # Metadata extraction is now handled once above via extract_metadata_from_session
            pass

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
        if not session_id:
            raise Exception("No user")
    except Exception:
        raise HTTPException(status_code=401, detail="Token invalide")
        
    from agent import get_session_service
    session_service = get_session_service()
    session = await session_service.get_session(
        app_name="zenika_ops_assistant", 
        user_id=session_id,  # sub JWT = user_id
        session_id=session_id
    )
    if session:
        session_service._delete_session_impl(app_name="zenika_ops_assistant", user_id=session_id, session_id=session_id)
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


@protected_router.get("/mcp/registry")
async def mcp_registry():
    return {
        "services": [
            {
                "id": "ops",
                "name": "Ops Agent (Platform & FinOps)",
                "tools": get_tool_metadata(OPS_TOOLS)
            }
        ]
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/version")
async def get_version():
    return {"version": os.getenv("APP_VERSION", "unknown")}


@protected_router.api_route("/mcp/proxy/{server_name}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_mcp(server_name: str, path: str, request: Request, auth: HTTPAuthorizationCredentials = Depends(security)):
    # Synchronisation avec les noms Terraform (market -> MARKET_MCP_URL, drive -> DRIVE_MCP_URL, etc.)
    target_url_env = f"{server_name.upper()}_URL"
    base_url = os.getenv(target_url_env)
    
    if not base_url:
        target_url_env_mcp = f"{server_name.upper()}_MCP_URL"
        base_url = os.getenv(target_url_env_mcp)
        
    if not base_url:
        raise HTTPException(status_code=404, detail=f"MCP Server {server_name} introuvable (Tried {target_url_env} and {target_url_env_mcp if 'target_url_env_mcp' in locals() else 'N/A'})")
        
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
            return Response(content=res.content, status_code=res.status_code, media_type=res.headers.get("content-type"))
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Erreur de communication avec {server_name}: {str(exc)}")



app.include_router(protected_router)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
