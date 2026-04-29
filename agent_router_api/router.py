import json
import logging
import os
import re
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from opentelemetry.propagate import extract, inject
from opentelemetry.trace import SpanKind
import httpx

from agent import run_agent_query, get_session_service
from mcp_client import auth_header_var
from semantic_cache import SemanticCache
from agent_commons.schemas import QueryRequest
from agent_commons.jwt_middleware import verify_jwt_bearer as verify_jwt, ALGORITHM
from metrics import AGENT_QUERIES_TOTAL
from telemetry import setup_telemetry

import asyncio

tracer = setup_telemetry()
_semantic_cache = SemanticCache()

router = APIRouter(dependencies=[Depends(verify_jwt)])
security = HTTPBearer()
SECRET_KEY = os.getenv("SECRET_KEY", "dummy")

@router.get("/spec")
async def get_spec():
    try:
        with open("spec.md", "r", encoding="utf-8") as f:
            return Response(content=f.read(), media_type="text/markdown")
    except Exception:
        return Response(content="# Specification introuvable", media_type="text/markdown")

@router.post("/query")
async def query(request: QueryRequest, http_request: Request, auth: HTTPAuthorizationCredentials = Depends(security)):
    auth_header = f"{auth.scheme} {auth.credentials}"
    auth_header_var.set(auth_header)
    
    try:
        from jose import jwt, JWTError
        payload = jwt.decode(auth.credentials, SECRET_KEY, algorithms=[ALGORITHM])
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
            jwt_user_id = jwt_sub or "unknown@zenika.com"

            cached_response = await _semantic_cache.get(request.query)
            if cached_response is not None:
                span.set_attribute("agent.source", "semantic_cache")
                span.set_attribute("semantic_cache.hit", True)
                async def _log_cache_hit_bq():
                    try:
                        analytics_url = os.getenv("ANALYTICS_MCP_URL", "http://analytics_mcp:8080")
                        headers_bq = {"Authorization": auth_header}
                        inject(headers_bq)
                        async with httpx.AsyncClient(timeout=10.0) as bq_client:
                            await bq_client.post(f"{analytics_url.rstrip('/')}/mcp/call", json={
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
                    except Exception: raise
                asyncio.create_task(_log_cache_hit_bq())
                return cached_response

            result = await run_agent_query(request.query, computed_session_id, auth_token=auth_header, user_id=jwt_user_id)
            span.set_attribute("agent.source", result.get("source", "unknown"))

            asyncio.create_task(_semantic_cache.set(request.query, result))

            return result
            
        except Exception as e:
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(e))
            return {"response": f"Erreur: {str(e)}", "source": "error"}

@router.get("/history")
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
        
        author_val = (author or "").lower()
        role_val = (role or "").lower()
        
        is_assistant = any(x in ["assistant", "model", "assistant_zenika"] for x in [author_val, role_val])
        is_tool = any(x in ["tool", "function"] for x in [author_val, role_val])
        is_user = any(x in ["user"] for x in [author_val, role_val]) and not is_tool and not is_assistant
        
        parts = []
        if hasattr(content, "parts"):
            parts = list(content.parts) if content.parts else []
            content_text = "".join((getattr(p, "text", "") or "") for p in parts if hasattr(p, "text"))
        else:
            content_text = str(content)
            
        if is_user:
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


        if current_assistant_msg:
            for part in parts:
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
                
                fres = getattr(part, 'function_response', None)
                raw_text = getattr(part, 'text', None)
                
                res_to_process = None
                if fres:
                    res_to_process = getattr(fres, 'response', fres)
                elif raw_text and role_val in ["tool", "user"]:
                    try: res_to_process = json.loads(raw_text)
                    except Exception as e: logging.warning(f"Parse error: {e}")
                
                if res_to_process is not None:
                    if hasattr(res_to_process, 'model_dump'): res_to_process = res_to_process.model_dump()
                    elif hasattr(res_to_process, 'dict'): res_to_process = res_to_process.dict()
                    
                    if isinstance(res_to_process, dict) and "result" in res_to_process and isinstance(res_to_process["result"], str) and res_to_process["result"].startswith("{"):
                        try: res_to_process = json.loads(res_to_process["result"])
                        except Exception as e: logging.warning(f"Parse error: {e}")

                    if isinstance(res_to_process, dict) and "response" in res_to_process:
                        if res_to_process.get("thoughts"):
                            if current_assistant_msg["thoughts"]:
                                current_assistant_msg["thoughts"] += f"\n[Sub-Agent] {res_to_process['thoughts']}"
                            else:
                                current_assistant_msg["thoughts"] = f"[Sub-Agent] {res_to_process['thoughts']}"
                        
                        for s in res_to_process.get("steps", []):
                            current_assistant_msg["steps"].append(s)
                            
                        sub_use = res_to_process.get("usage", {})
                        if "usage" not in current_assistant_msg:
                            current_assistant_msg["usage"] = {"total_input_tokens": 0, "total_output_tokens": 0, "estimated_cost_usd": 0}
                        current_assistant_msg["usage"]["total_input_tokens"] += sub_use.get("total_input_tokens", 0)
                        current_assistant_msg["usage"]["total_output_tokens"] += sub_use.get("total_output_tokens", 0)
                        current_assistant_msg["data"] = res_to_process.get("data") or res_to_process
                    
                    if isinstance(res_to_process, dict) and "result" in res_to_process and isinstance(res_to_process["result"], str) and res_to_process["result"].startswith("{"):
                        try: res_to_process = json.loads(res_to_process["result"])
                        except Exception as e: logging.warning(f"Parse error: {e}")
                    
                    sig = f"result:{json.dumps(res_to_process, sort_keys=True)}"
                    if sig not in current_assistant_seen_steps:
                        if not current_assistant_msg["data"]:
                            current_assistant_msg["data"] = res_to_process
                        current_assistant_msg["steps"].append({"type": "result", "data": res_to_process})
                        current_assistant_seen_steps.add(sig)
            
            u = None
            if hasattr(event, 'response') and event.response and hasattr(event.response, 'usage_metadata'):
                u = event.response.usage_metadata
            elif hasattr(event, 'usage_metadata'):
                u = event.usage_metadata
                
            if u:
                if "usage" not in current_assistant_msg:
                    current_assistant_msg["usage"] = {"total_input_tokens": 0, "total_output_tokens": 0, "estimated_cost_usd": 0}
                
                it = getattr(u, 'prompt_token_count', 0) or (u.get('prompt_token_count', 0) if isinstance(u, dict) else 0)
                ot = getattr(u, 'candidates_token_count', 0) or (u.get('candidates_token_count', 0) if isinstance(u, dict) else 0)
                
                current_assistant_msg["usage"]["total_input_tokens"] = max(current_assistant_msg["usage"]["total_input_tokens"], it)
                current_assistant_msg["usage"]["total_output_tokens"] = max(current_assistant_msg["usage"]["total_output_tokens"], ot)
                
                ti = current_assistant_msg["usage"]["total_input_tokens"]
                to = current_assistant_msg["usage"]["total_output_tokens"]
                current_assistant_msg["usage"]["estimated_cost_usd"] = round(ti * 0.000000075 + to * 0.0000003, 6)

        if is_assistant and content_text:
            full_raw = current_assistant_msg.get("_full_text_progress", "") + content_text
            current_assistant_msg["_full_text_progress"] = full_raw
            current_assistant_msg["rawResponse"] = full_raw
            
            try:
                json_match = re.search(r'\{[\s\S]*\}', full_raw)
                if json_match:
                    json_str = json_match.group(0)
                    json_obj = json.loads(json_str)
                    if "reply" in json_obj and "display_type" in json_obj:
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

            if current_assistant_msg.get("data"):
                d = current_assistant_msg["data"]
                
                if isinstance(d, dict) and d.get("dataType") == "competency":
                    current_assistant_msg["displayType"] = "tree"
                elif current_assistant_msg["displayType"] == "text_only":
                    current_assistant_msg["displayType"] = "cards"

                if isinstance(d, dict) and "items" in d:
                    current_assistant_msg["parsedData"] = d["items"]
                elif isinstance(d, list):
                    current_assistant_msg["parsedData"] = d
                else:
                    current_assistant_msg["parsedData"] = [d]

            
    final_history = []
    for msg in history:
        if isinstance(msg, dict):
            msg.pop("_full_text_progress", None)
            
            if msg.get("role") == "assistant" and not msg.get("content") and not msg.get("steps") and not msg.get("data"):
                continue
                
            final_history.append(msg)
            
    return {"history": final_history}

@router.delete("/history")
async def delete_history(request: Request, auth: HTTPAuthorizationCredentials = Depends(security)):
    try:
        from jose import jwt, JWTError
        payload = jwt.decode(auth.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        jwt_user_id = payload.get("sub", "user_1")
        if not jwt_user_id:
            raise Exception("No user")
    except Exception:
        raise HTTPException(status_code=401, detail="Token invalide")

    session_id = request.query_params.get("session_id") or jwt_user_id
        
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
