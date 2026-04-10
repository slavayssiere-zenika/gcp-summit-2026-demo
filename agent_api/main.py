import re
import json
from fastapi import FastAPI, HTTPException, Request, Response
import httpx
from pydantic import BaseModel
from typing import Optional
import uvicorn
import os
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes
import os
if os.getenv("TRACE_EXPORTER", "grpc") == "http":
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
elif os.getenv("TRACE_EXPORTER", "grpc") == "gcp":
    from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
else:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.propagate import inject, extract
from opentelemetry.trace import SpanKind
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_fastapi_instrumentator import Instrumentator

from agent import run_agent_query, USERS_TOOLS, ITEMS_TOOLS, COMPETENCIES_TOOLS, LOKI_TOOLS, CV_TOOLS, DRIVE_TOOLS
import inspect
from logger import setup_logging, LoggingMiddleware

provider = TracerProvider(
    resource=Resource.create({
        ResourceAttributes.SERVICE_NAME: "agent-api",
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
app = FastAPI(
    title="ADK Web Agent",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
    root_path=os.getenv("ROOT_PATH", "")
)
app.add_middleware(LoggingMiddleware)
Instrumentator().instrument(app).expose(app)
FastAPIInstrumentor.instrument_app(app, excluded_urls="metrics,health")


@app.on_event("startup")
async def startup_event():
    print("Starting ADK Web Agent with Gemini...")


@app.get("/")
async def root():
    return {"message": "ADK Agent API - Use /query for interactions"}


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
            result = await run_agent_query(request.query, computed_session_id)
            span.set_attribute("agent.source", result.get("source", "unknown"))
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
        if not session_id:
            raise Exception("No user")
    except Exception:
        raise HTTPException(status_code=401, detail="Token invalide")
        
    from agent import get_session_service
    session_service = get_session_service()
    session = await session_service.get_session(
        app_name="zenika_assistant", 
        user_id="user_1", 
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
        is_user = any(x in ["user"] for x in [author_val, role_val])
        
        # Extract parts if available
        parts = []
        if hasattr(content, "parts"):
            parts = list(content.parts) if content.parts else []
            content_text = "".join((getattr(p, "text", "") or "") for p in parts if hasattr(p, "text"))
        else:
            content_text = str(content)
            
            
        # 1. Process EVERY event exhaustively for metadata
        if current_assistant_msg:
            # a) Scan Parts
            for part in parts:
                # Thoughts
                thought_val = getattr(part, 'thought', None)
                if thought_val:
                    if current_assistant_msg["thoughts"]:
                        current_assistant_msg["thoughts"] += "\n" + str(thought_val)
                    else:
                        current_assistant_msg["thoughts"] = str(thought_val)
                
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
                    
                    # Unwrap MCP 'result' JSON string
                    if isinstance(res_to_process, dict) and "result" in res_to_process and isinstance(res_to_process["result"], str) and res_to_process["result"].startswith("{"):
                        try: res_to_process = json.loads(res_to_process["result"])
                        except: pass
                    
                    sig = f"result:{json.dumps(res_to_process, sort_keys=True)}"
                    if sig not in current_assistant_seen_steps:
                        current_assistant_msg["data"] = res_to_process
                        current_assistant_msg["steps"].append({"type": "result", "data": res_to_process})
                        current_assistant_seen_steps.add(sig)
            
            # b) Scan Event Methods
            if hasattr(event, 'actions') and event.actions:
                for action in event.actions:
                    tc = getattr(action, 'tool_call', None)
                    if tc:
                        name = getattr(tc, 'name', "unknown")
                        args = getattr(tc, 'args', {})
                        sig = f"call:{name}:{json.dumps(args, sort_keys=True)}"
                        if sig not in current_assistant_seen_steps:
                            current_assistant_msg["steps"].append({"type": "call", "tool": name, "args": args})
                            current_assistant_seen_steps.add(sig)
            
            if hasattr(event, 'get_function_calls'):
                for fc in (event.get_function_calls() or []):
                    name = getattr(fc, 'name', "unknown")
                    args = getattr(fc, 'args', {})
                    sig = f"call:{name}:{json.dumps(args, sort_keys=True)}"
                    if sig not in current_assistant_seen_steps:
                        current_assistant_msg["steps"].append({"type": "call", "tool": name, "args": args})
                        current_assistant_seen_steps.add(sig)

            if hasattr(event, 'get_function_responses'):
                for fr in (event.get_function_responses() or []):
                    res_data = getattr(fr, 'response', fr)
                    if hasattr(res_data, 'model_dump'): res_data = res_data.model_dump()
                    elif hasattr(res_data, 'dict'): res_data = res_data.dict()
                    
                    # Unwrap MCP 'result' JSON string
                    if isinstance(res_data, dict) and "result" in res_data and isinstance(res_data["result"], str) and res_data["result"].startswith("{"):
                        try: res_data = json.loads(res_data["result"])
                        except: pass
                    
                    sig = f"result:{json.dumps(res_data, sort_keys=True)}"
                    if sig not in current_assistant_seen_steps:
                        current_assistant_msg["data"] = res_data
                        current_assistant_msg["steps"].append({"type": "result", "data": res_data})
                        current_assistant_seen_steps.add(sig)
            


        # 2. Main turn logic
        if is_user:
            history.append({
                "role": "user",
                "content": content_text
            })
            current_assistant_msg = None 
            
        elif is_assistant:
            if current_assistant_msg is None:
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
            
            if content_text:
                current_assistant_msg["content"] += content_text
                # rawResponse should contain the full textual history of the turn for the expert mode
                current_assistant_msg["rawResponse"] += content_text
                
                # Try to extract dashboard JSON if present in the text
                try:
                    json_match = re.search(r'\{[\s\S]*\}', current_assistant_msg["content"])
                    if json_match:
                        json_obj = json.loads(json_match.group(0))
                        if "reply" in json_obj and "display_type" in json_obj:
                            current_assistant_msg["content"] = json_obj["reply"]
                            current_assistant_msg["displayType"] = json_obj["display_type"]
                            if current_assistant_msg["displayType"] == "profile":
                                current_assistant_msg["displayType"] = "cards"
                            
                            if "data" in json_obj:
                                current_assistant_msg["data"] = json_obj["data"]
                except: pass

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

            
    return {"history": history}

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
        app_name="zenika_assistant", 
        user_id="user_1", 
        session_id=session_id
    )
    if session:
        session_service._delete_session_impl(app_name="zenika_assistant", user_id="user_1", session_id=session_id)
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
                "id": "users",
                "name": "Users Service",
                "tools": get_tool_metadata(USERS_TOOLS)
            },
            {
                "id": "items",
                "name": "Items Service",
                "tools": get_tool_metadata(ITEMS_TOOLS)
            },
            {
                "id": "competencies",
                "name": "Competencies Service",
                "tools": get_tool_metadata(COMPETENCIES_TOOLS)
            },
            {
                "id": "loki",
                "name": "Loki Log Explorer",
                "status": "connected",
                "version": "1.0",
                "tools": get_tool_metadata(LOKI_TOOLS)
            },
            {
                "id": "cv",
                "name": "CV Parsing Agent",
                "status": "connected",
                "version": "1.0",
                "tools": get_tool_metadata(CV_TOOLS)
            },
            {
                "id": "drive",
                "name": "Google Drive Sync Agent",
                "status": "connected",
                "version": "1.0",
                "tools": get_tool_metadata(DRIVE_TOOLS)
            }
        ]
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


app.include_router(protected_router)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)
