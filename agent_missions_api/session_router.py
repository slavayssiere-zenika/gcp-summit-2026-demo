"""
session_router.py — Endpoints de gestion de session pour agent_missions_api.

Expose :
  GET    /history  — retourne l'historique de session formaté
  DELETE /history  — efface la session Redis

Extrait de main.py pour respecter la limite de 400 lignes (Golden Rule §14).
"""
import json
import logging
import re

from agent_commons.metadata import extract_metadata_from_session
from fastapi import APIRouter, Depends, HTTPException

from shared.auth.jwt import verify_jwt_request as verify_jwt

logger = logging.getLogger(__name__)

session_router = APIRouter(dependencies=[Depends(verify_jwt)])


def _get_session_service():
    """Lazy singleton — importe get_session_service depuis main pour éviter les cycles."""
    from main import get_session_service
    return get_session_service()


@session_router.get("/history")
async def get_history(payload: dict = Depends(verify_jwt)):
    """Retourne l'historique de la session courante (par sub JWT)."""
    session_id = payload.get("sub")
    if not session_id:
        raise HTTPException(status_code=401, detail="Token invalide — sub manquant")
    user_id = session_id  # sub JWT = user_id pour la session ADK

    session_service = _get_session_service()
    session = await session_service.get_session(
        app_name="zenika_missions_assistant",
        user_id=user_id,
        session_id=session_id,
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

        is_assistant = any(
            x in ["assistant", "model", "assistant_zenika_missions"]
            for x in [author_val, role_val]
        )
        is_tool = any(x in ["tool", "function"] for x in [author_val, role_val])
        is_user = "user" in [author_val, role_val] and not is_tool and not is_assistant

        if hasattr(content, "parts"):
            content_text = "".join(
                getattr(p, "text", "") or ""
                for p in (content.parts or [])
                if hasattr(p, "text")
            )
        else:
            content_text = str(content)

        if is_user and content_text.strip():
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
            }
            history.append(current_assistant_msg)

        if is_assistant and content_text and current_assistant_msg:
            full_raw = current_assistant_msg.get("_full_text_progress", "") + content_text
            current_assistant_msg["_full_text_progress"] = full_raw
            current_assistant_msg["rawResponse"] = full_raw
            try:
                json_match = re.search(r'\{[\s\S]*\}', full_raw)
                if json_match:
                    json_obj = json.loads(json_match.group(0))
                    if "reply" in json_obj and "display_type" in json_obj:
                        reply = json_obj.get("reply", "")
                        current_assistant_msg["content"] = full_raw.replace(
                            json_match.group(0), reply
                        ).strip()
                        current_assistant_msg["displayType"] = json_obj["display_type"]
                        if json_obj.get("data"):
                            current_assistant_msg["data"] = json_obj["data"]
                    else:
                        current_assistant_msg["content"] = full_raw
                else:
                    current_assistant_msg["content"] = full_raw
            except Exception as e:
                logger.debug("[history] JSON parse error: %s: %s", type(e).__name__, e)
                current_assistant_msg["content"] = full_raw

            if current_assistant_msg.get("data"):
                d = current_assistant_msg["data"]
                if isinstance(d, dict) and d.get("dataType") == "mission":
                    current_assistant_msg["displayType"] = "cards"
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
            if (
                msg.get("role") == "assistant"
                and not msg.get("content")
                and not msg.get("steps")
                and not msg.get("data")
            ):
                continue
            final_history.append(msg)

    return {"history": final_history}


@session_router.delete("/history")
async def delete_history(payload: dict = Depends(verify_jwt)):
    """Efface la session Redis de l'utilisateur courant."""
    session_id = payload.get("sub")
    if not session_id:
        raise HTTPException(status_code=401, detail="Token invalide — sub manquant")
    user_id = session_id  # sub JWT = user_id pour la session ADK

    session_service = _get_session_service()
    session = await session_service.get_session(
        app_name="zenika_missions_assistant",
        user_id=user_id,
        session_id=session_id,
    )
    if session:
        session_service._delete_session_impl(
            app_name="zenika_missions_assistant",
            user_id=user_id,
            session_id=session_id,
        )
        return {"message": "Historique effacé"}
    return {"message": "Pas d'historique"}
