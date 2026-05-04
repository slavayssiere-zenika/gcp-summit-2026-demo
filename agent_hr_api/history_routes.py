"""
history_routes.py — Routes /history (GET + DELETE) pour agent_hr_api.

Extrait de main.py pour respecter la contrainte de modularité 400 lignes.
Ce module crée un APIRouter protégé par JWT à enregistrer dans main.py.

Usage dans main.py :
    from history_routes import history_router
    app.include_router(history_router)
"""
import json
import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt

from agent_commons.jwt_middleware import verify_jwt_bearer as verify_jwt, ALGORITHM
from agent_commons.metadata import extract_metadata_from_session
from agent import get_session_service

logger = logging.getLogger(__name__)

security = HTTPBearer()


# APIRouter protégé — identique au pattern protected_router de main.py
history_router = APIRouter(dependencies=[Depends(verify_jwt)])

APP_NAME = "zenika_hr_assistant"


def _parse_session_history(session) -> list[dict]:
    """Reconstruit l'historique de conversation depuis les events ADK.

    Retourne la liste de messages finaux (user + assistant).
    Lit les render_ui_widgets pour le dispatch sémantique (ui://consultants, etc.)
    et les usage tokens pour le badge FinOps.
    """
    history: list[dict] = []
    current_assistant_msg: dict | None = None

    for event in getattr(session, "events", []):
        author = getattr(event, "author", None)
        content = getattr(event, "content", "")
        role = getattr(content, "role", None) if content else None

        author_val = (author or "").lower()
        role_val = (role or "").lower()

        is_assistant = any(x in ["assistant", "model", "assistant_zenika"] for x in [author_val, role_val])
        is_tool = any(x in ["tool", "function"] for x in [author_val, role_val])
        is_user = any(x in ["user"] for x in [author_val, role_val]) and not is_tool and not is_assistant

        if hasattr(content, "parts"):
            parts = list(content.parts) if content.parts else []
            content_text = "".join((getattr(p, "text", "") or "") for p in parts if hasattr(p, "text"))
        else:
            content_text = str(content)

        if is_user:
            if content_text.strip():
                history.append({"role": "user", "content": content_text})
                current_assistant_msg = None

        elif is_assistant and current_assistant_msg is None:
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
                "pagination": {"currentPage": 1, "itemsPerPage": 10},
                "usage": {
                    "total_input_tokens": 0,
                    "total_output_tokens": 0,
                    "estimated_cost_usd": 0.0,
                },
            }
            history.append(current_assistant_msg)

        if is_assistant and current_assistant_msg is not None:
            # ── Texte ──────────────────────────────────────────────────────
            if content_text:
                full_raw = current_assistant_msg.get("_full_text_progress", "") + content_text
                current_assistant_msg["_full_text_progress"] = full_raw
                current_assistant_msg["rawResponse"] = full_raw
                current_assistant_msg["content"] = full_raw

            # ── Usage tokens (FinopsBadge) ─────────────────────────────────
            usage_meta = getattr(event, "usage_metadata", None)
            if usage_meta:
                it = getattr(usage_meta, "prompt_token_count", 0) or 0
                ot = getattr(usage_meta, "candidates_token_count", 0) or 0
                u = current_assistant_msg["usage"]
                u["total_input_tokens"] = max(u["total_input_tokens"], it)
                u["total_output_tokens"] = max(u["total_output_tokens"], ot)
                u["estimated_cost_usd"] = round(
                    u["total_input_tokens"] * 0.000000075 + u["total_output_tokens"] * 0.0000003, 6
                )

            # ── UiWidgets sémantiques (dispatch natif ADK) ─────────────────
            actions = getattr(event, "actions", None)
            if actions:
                widgets = getattr(actions, "render_ui_widgets", None) or getattr(actions, "renderUiWidgets", [])
                for widget in (widgets or []):
                    payload = getattr(widget, "payload", {})
                    if payload:
                        res_uri = payload.get("resource_uri", "")
                        if res_uri.startswith("ui://"):
                            current_assistant_msg["displayType"] = res_uri[5:]

            # ── Fallback parsedData depuis meta.data ───────────────────────
            if current_assistant_msg.get("data") and current_assistant_msg["displayType"] == "text_only":
                d = current_assistant_msg["data"]
                # Fallback heuristique uniquement si aucun UiWidget n'a été émis
                current_assistant_msg["displayType"] = "cards"
                if isinstance(d, dict) and "items" in d:
                    current_assistant_msg["parsedData"] = d["items"]
                elif isinstance(d, list):
                    current_assistant_msg["parsedData"] = d
                else:
                    current_assistant_msg["parsedData"] = [d]

    # Clean up internal progress field and skip empty ghost messages
    final: list[dict] = []
    for msg in history:
        if isinstance(msg, dict):
            msg.pop("_full_text_progress", None)
            if msg.get("role") == "assistant" and not msg.get("content") and not msg.get("steps") and not msg.get("data"):
                continue
            final.append(msg)

    return final


@history_router.get("/history")
async def get_history(auth: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.get_unverified_claims(auth.credentials)
        session_id = payload.get("sub")
        if not session_id:
            raise ValueError("No sub claim")
    except Exception:
        raise HTTPException(status_code=401, detail="Token invalide")

    try:
        session_service = get_session_service()
        session = await session_service.get_session(
            app_name=APP_NAME,
            user_id=session_id,
            session_id=session_id,
        )
    except Exception as e:
        logger.warning("[history] Impossible de récupérer la session (Redis?) : %s", e)
        return {"history": []}

    if not session:
        return {"history": []}

    return {"history": _parse_session_history(session)}


@history_router.delete("/history")
async def delete_history(auth: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.get_unverified_claims(auth.credentials)
        session_id = payload.get("sub")
        if not session_id:
            raise ValueError("No sub claim")
    except Exception:
        raise HTTPException(status_code=401, detail="Token invalide")

    session_service = get_session_service()
    session = await session_service.get_session(
        app_name=APP_NAME,
        user_id=session_id,
        session_id=session_id,
    )
    if session:
        session_service._delete_session_impl(app_name=APP_NAME, user_id=session_id, session_id=session_id)
        return {"message": "Historique effacé"}
    return {"message": "Pas d'historique"}
