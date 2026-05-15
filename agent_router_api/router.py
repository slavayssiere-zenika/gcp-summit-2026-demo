import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from uuid import uuid4

import httpx
from agent import get_session_service, run_agent_query
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from mcp_client import auth_header_var
from metrics import AGENT_QUERIES_TOTAL
from opentelemetry.propagate import extract, inject
from opentelemetry.trace import SpanKind
from semantic_cache import SemanticCache
from telemetry import setup_telemetry

from shared.auth.jwt import verify_jwt_bearer as verify_jwt
from agent_commons.schemas import QueryRequest

tracer = setup_telemetry()
_semantic_cache = SemanticCache()
logger = logging.getLogger(__name__)

from shared.auth.jwt import ALGORITHM, SECRET_KEY, security  # noqa: E402

router = APIRouter(dependencies=[Depends(verify_jwt)])


@router.post("/query")
async def query(request: QueryRequest, http_request: Request,
                auth: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
                payload: dict = Depends(verify_jwt)):
    auth_header = f"{auth.scheme} {auth.credentials}"
    auth_header_var.set(auth_header)

    body_session_id = request.session_id if request.session_id else None
    jwt_sub = payload.get("sub")
    computed_session_id = body_session_id if body_session_id else jwt_sub
    if not computed_session_id:
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

            preferred_language = http_request.headers.get("x-preferred-language", "fr")
            result = await run_agent_query(
                request.query,
                computed_session_id,
                auth_token=auth_header,
                user_id=jwt_user_id,
                preferred_language=preferred_language,
            )
            span.set_attribute("agent.source", result.get("source", "unknown"))

            asyncio.create_task(_semantic_cache.set(request.query, result))

            return result
            
        except Exception as e:
            span.set_attribute("error", True)
            span.set_attribute("error.type", type(e).__name__)
            span.set_attribute("error.message", str(e))
            logger.error(
                "CRITICAL: Exception in /query — %s: %s",
                type(e).__name__,
                str(e) or repr(e),
                exc_info=True,
            )
            return {"response": f"Erreur: {str(e)}", "source": "error"}

@router.get("/history")
async def get_history(
    http_request: Request,
    auth: HTTPAuthorizationCredentials = Depends(security)
):
    try:
        import jwt as _jwt
        from jwt.exceptions import InvalidTokenError
        payload = _jwt.decode(
            auth.credentials, SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"leeway": 300},
        )
        jwt_user_id = payload.get("sub", "user_1")
        if not jwt_user_id:
            raise InvalidTokenError("No user")
    except InvalidTokenError as e:
        logger.warning("[history] JWT decode failed: %s", e)
        raise HTTPException(status_code=401, detail="Token invalide")

    # Accepte session_id en query param — fallback sur jwt_user_id (rétrocompatibilité)
    session_id = http_request.query_params.get("session_id") or jwt_user_id
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
                        # Propagation du hint UI depuis le sous-agent (render_ui_widgets → display_type → A2A)
                        sub_display_type = res_to_process.get("display_type")
                        if sub_display_type and current_assistant_msg.get("displayType") == "text_only":
                            current_assistant_msg["displayType"] = sub_display_type
                    
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
                
            actions = getattr(event, "actions", None)
            if actions:
                widgets = getattr(actions, "render_ui_widgets", None) or getattr(actions, "renderUiWidgets", [])
                for widget in widgets:
                    payload = getattr(widget, "payload", {})
                    if payload:
                        res_uri = payload.get("resource_uri", "")
                        if res_uri.startswith("ui://"):
                            # Pass the full semantic slug: consultant, mission, tree, candidate...
                            current_assistant_msg["displayType"] = res_uri[5:]

        if is_assistant and content_text:
            full_raw = current_assistant_msg.get("_full_text_progress", "") + content_text
            current_assistant_msg["_full_text_progress"] = full_raw
            current_assistant_msg["rawResponse"] = full_raw
            current_assistant_msg["content"] = full_raw

            if current_assistant_msg.get("data"):
                d = current_assistant_msg["data"]

                if isinstance(d, dict) and d.get("dataType") == "competency":
                    current_assistant_msg["displayType"] = "tree"
                elif current_assistant_msg["displayType"] == "text_only" and d:
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
        import jwt as _jwt
        from jwt.exceptions import InvalidTokenError
        payload = _jwt.decode(
            auth.credentials, SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"leeway": 300},
        )
        jwt_user_id = payload.get("sub", "user_1")
        if not jwt_user_id:
            raise InvalidTokenError("No user")
    except InvalidTokenError as e:
        logger.warning("[clear-history] JWT decode failed: %s", e)
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


# ---------------------------------------------------------------------------
# Helpers Redis pour les métadonnées de sessions
# ---------------------------------------------------------------------------

SESSIONS_TTL = 30 * 24 * 60 * 60  # 1 mois
SESSIONS_MAX = 10


def _get_redis():
    import redis
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/2")
    return redis.from_url(redis_url)


def _sessions_key(user_id: str) -> str:
    return f"chat:sessions:{user_id}"


def _load_sessions(user_id: str) -> list:
    """Charge la liste des métadonnées de sessions depuis Redis."""
    try:
        r = _get_redis()
        raw = r.get(_sessions_key(user_id))
        if raw:
            return json.loads(raw)
    except Exception as e:
        logger.error("[sessions] Redis load failed: %s", e)
    return []


def _save_sessions(user_id: str, sessions: list):
    """Persiste la liste des sessions dans Redis avec TTL 1 mois."""
    try:
        r = _get_redis()
        r.set(_sessions_key(user_id), json.dumps(sessions), ex=SESSIONS_TTL)
    except Exception as e:
        logger.error("[sessions] Redis save failed: %s", e)


def _migrate_legacy_session(user_id: str, sessions: list) -> list:
    """
    Migration : si un historique ADK existe sous la clé jwt_sub (ancien format
    mono-session), on l'importe automatiquement en session nommée 'Défaut'.
    Appelé uniquement quand la liste des sessions est vide.
    """
    try:
        r = _get_redis()
        legacy_key = f"adk:sessions:{user_id}"
        if r.exists(legacy_key):
            default_session = {
                "id": user_id,
                "name": "Défaut",
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            sessions = [default_session]
            logger.info("[sessions] Migrated legacy session for user %s", user_id)
    except Exception as e:
        logger.error("[sessions] Legacy migration failed: %s", e)
    return sessions


# ---------------------------------------------------------------------------
# Routes /sessions
# ---------------------------------------------------------------------------


@router.get("/sessions")
async def list_sessions(auth: HTTPAuthorizationCredentials = Depends(security)):
    """Liste les sessions de travail de l'utilisateur."""
    try:
        import jwt as _jwt
        from jwt.exceptions import InvalidTokenError
        payload = _jwt.decode(
            auth.credentials, SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"leeway": 300},
        )
        jwt_user_id = payload.get("sub")
        if not jwt_user_id:
            raise InvalidTokenError("No user")
    except InvalidTokenError as e:
        logger.warning("[sessions] JWT decode failed: %s", e)
        raise HTTPException(status_code=401, detail="Token invalide")

    sessions = _load_sessions(jwt_user_id)

    if not sessions:
        sessions = _migrate_legacy_session(jwt_user_id, sessions)
        if not sessions:
            # Aucun historique existant — créer la session "Défaut" vierge
            sessions = [{
                "id": jwt_user_id,
                "name": "Défaut",
                "created_at": datetime.now(timezone.utc).isoformat()
            }]
        _save_sessions(jwt_user_id, sessions)

    return {"sessions": sessions}


@router.post("/sessions")
async def create_session(
    request: Request,
    auth: HTTPAuthorizationCredentials = Depends(security)
):
    """Crée une nouvelle session de travail (max 10 par utilisateur)."""
    try:
        import jwt as _jwt
        from jwt.exceptions import InvalidTokenError
        payload = _jwt.decode(
            auth.credentials, SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"leeway": 300},
        )
        jwt_user_id = payload.get("sub")
        if not jwt_user_id:
            raise InvalidTokenError("No user")
    except InvalidTokenError as e:
        logger.warning("[sessions] JWT decode failed: %s", e)
        raise HTTPException(status_code=401, detail="Token invalide")

    body = await request.json()
    name = body.get("name", "").strip() or "Nouvelle session"

    sessions = _load_sessions(jwt_user_id)
    if not sessions:
        sessions = _migrate_legacy_session(jwt_user_id, sessions)

    if len(sessions) >= SESSIONS_MAX:
        raise HTTPException(
            status_code=400,
            detail=f"Limite de {SESSIONS_MAX} sessions atteinte. Supprimez une session pour continuer."
        )

    new_session = {
        "id": f"{jwt_user_id}:{uuid4().hex[:8]}",
        "name": name,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    sessions.append(new_session)
    _save_sessions(jwt_user_id, sessions)

    return new_session


@router.patch("/sessions/{session_id:path}")
async def rename_session(
    session_id: str,
    request: Request,
    auth: HTTPAuthorizationCredentials = Depends(security)
):
    """Renomme une session de travail existante."""
    try:
        import jwt as _jwt
        from jwt.exceptions import InvalidTokenError
        payload = _jwt.decode(
            auth.credentials, SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"leeway": 300},
        )
        jwt_user_id = payload.get("sub")
        if not jwt_user_id:
            raise InvalidTokenError("No user")
    except InvalidTokenError as e:
        logger.warning("[sessions] JWT decode failed: %s", e)
        raise HTTPException(status_code=401, detail="Token invalide")

    body = await request.json()
    new_name = body.get("name", "").strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="Le nom de session ne peut pas être vide.")

    sessions = _load_sessions(jwt_user_id)
    updated = False
    for s in sessions:
        if s["id"] == session_id:
            s["name"] = new_name
            updated = True
            break

    if not updated:
        raise HTTPException(status_code=404, detail="Session introuvable.")

    _save_sessions(jwt_user_id, sessions)
    return {"success": True, "id": session_id, "name": new_name}


@router.delete("/sessions/{session_id:path}")
async def delete_session(
    session_id: str,
    auth: HTTPAuthorizationCredentials = Depends(security)
):
    """Supprime une session et son historique ADK associé."""
    try:
        import jwt as _jwt
        from jwt.exceptions import InvalidTokenError
        payload = _jwt.decode(
            auth.credentials, SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"leeway": 300},
        )
        jwt_user_id = payload.get("sub")
        if not jwt_user_id:
            raise InvalidTokenError("No user")
    except InvalidTokenError as e:
        logger.warning("[sessions] JWT decode failed: %s", e)
        raise HTTPException(status_code=401, detail="Token invalide")

    sessions = _load_sessions(jwt_user_id)
    if len(sessions) <= 1:
        raise HTTPException(
            status_code=400,
            detail="Impossible de supprimer la dernière session."
        )

    original_len = len(sessions)
    sessions = [s for s in sessions if s["id"] != session_id]
    if len(sessions) == original_len:
        raise HTTPException(status_code=404, detail="Session introuvable.")

    _save_sessions(jwt_user_id, sessions)

    # Supprimer l'historique ADK
    session_service = get_session_service()
    try:
        session = await session_service.get_session(
            app_name="zenika_assistant",
            user_id=jwt_user_id,
            session_id=session_id
        )
        if session:
            session_service._delete_session_impl(
                app_name="zenika_assistant",
                user_id=jwt_user_id,
                session_id=session_id
            )
    except Exception as e:
        logger.warning("[sessions] Could not delete ADK session %s: %s", session_id, e)

    return {"success": True, "deleted_id": session_id}
