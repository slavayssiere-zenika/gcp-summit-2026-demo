import base64
import json
import logging

from cache import delete_cache_pattern
from shared.database import get_db
from fastapi import APIRouter, Depends, HTTPException, Request, Path
from pydantic import BaseModel, Field
from sqlalchemy import delete as sa_delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from shared.auth.jwt import verify_jwt
from src.items.models import Item, item_category

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["items_admin"], dependencies=[Depends(verify_jwt)])
public_router = APIRouter(prefix="", tags=["items_public"])


@router.delete("/user/{user_id}/items", status_code=204)
async def delete_user_items(
    user_id: int = Path(..., gt=0, le=2_147_483_647),
    db: AsyncSession = Depends(get_db),
    auth_payload: dict = Depends(verify_jwt),
):
    """
    (Admin / Service Account only) Supprime tous les items (missions) d'un utilisateur.
    Utilisé par le pipeline de ré-analyse globale (Vertex AI Batch) avant la
    ré-indexation complète des missions extraites du nouveau prompt.

    Ordre de suppression obligatoire :
    1. item_category (FK item_id → items.id) — doit être supprimé EN PREMIER
    2. items — peut être supprimé une fois les FK levées
    Sans cette séquence, PostgreSQL lève ForeignKeyViolationError (HTTP 500).
    """
    user_role = auth_payload.get("role", "")
    if user_role not in ("admin", "service_account"):
        raise HTTPException(
            status_code=403,
            detail="Privilèges admin ou service_account requis."
        )

    # ── Étape 1 : récupérer les IDs des items de l'utilisateur ──────────────
    result = await db.execute(select(Item.id).where(Item.user_id == user_id))
    item_ids = result.scalars().all()

    if item_ids:
        # ── Étape 2 : supprimer item_category AVANT items (contrainte FK) ───
        await db.execute(
            sa_delete(item_category).where(
                item_category.c.item_id.in_(item_ids)
            )
        )
        # ── Étape 3 : supprimer les items ────────────────────────────────────
        await db.execute(sa_delete(Item).where(Item.user_id == user_id))
        logger.info(
            "[items] Purge user_id=%s : %d items + associations item_category supprimés.",
            user_id, len(item_ids),
        )

    await db.commit()

    delete_cache_pattern(f"items:user:{user_id}:*")
    delete_cache_pattern("items:list:*")
    delete_cache_pattern("items:search:*")
    return None

# Borne maximale pour les colonnes INT4
_INT4_MAX = 2_147_483_647


class UserMergeRequest(BaseModel):
    source_id: int = Field(gt=0, le=_INT4_MAX, description="ID source (INT4)")
    target_id: int = Field(gt=0, le=_INT4_MAX, description="ID cible (INT4)")


@public_router.post("/pubsub/user-events")
async def handle_user_pubsub_events(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Handle GCP Pub/Sub Push Notifications.
    """
    try:
        body = await request.body()
        if not body:
            return {"status": "ignored"}
        payload = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    message = payload.get("message")
    if not message or "data" not in message:
        return {"status": "ignored"}

    try:
        data_str = base64.b64decode(message["data"]).decode("utf-8")
        event_data = json.loads(data_str)
        event_type = event_data.get("event")
        data = event_data.get("data", {})

        if event_type == "user.merged":
            source_id = data.get("source_id")
            target_id = data.get("target_id")
            if source_id and target_id:
                stmt = update(Item).where(Item.user_id == source_id).values(user_id=target_id)
                await db.execute(stmt)
                await db.commit()
                # Invalidate cache
                delete_cache_pattern(f"items:user:{source_id}:*")
                delete_cache_pattern(f"items:user:{target_id}:*")

        return {"status": "processed"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@router.post("/internal/users/merge")
async def merge_users(req: UserMergeRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """
    Internal endpoint to merge user data (Legacy).
    """
    stmt = update(Item).where(Item.user_id == req.source_id).values(user_id=req.target_id)
    await db.execute(stmt)
    await db.commit()
    delete_cache_pattern(f"items:user:{req.source_id}:*")
    delete_cache_pattern(f"items:user:{req.target_id}:*")
    return {"message": f"Successfully migrated items from user {req.source_id} to {req.target_id}"}
