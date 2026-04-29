import os
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete as sa_delete
from pydantic import BaseModel

from cache import delete_cache_pattern
from database import get_db
from src.auth import verify_jwt
from src.items.models import Item

router = APIRouter(prefix="", tags=["items_admin"], dependencies=[Depends(verify_jwt)])
public_router = APIRouter(prefix="", tags=["items_public"])


@router.delete("/user/{user_id}/items", status_code=204)
async def delete_user_items(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    auth_payload: dict = Depends(verify_jwt),
):
    """
    (Admin / Service Account only) Supprime tous les items (missions) d'un utilisateur.
    Utilisé par le pipeline de ré-analyse globale (Vertex AI Batch) avant la
    ré-indexation complète des missions extraites du nouveau prompt.
    """
    user_role = auth_payload.get("role", "")
    if user_role not in ("admin", "service_account"):
        raise HTTPException(
            status_code=403,
            detail="Privilèges admin ou service_account requis."
        )

    await db.execute(sa_delete(Item).where(Item.user_id == user_id))
    await db.commit()

    delete_cache_pattern(f"items:user:{user_id}:*")
    delete_cache_pattern("items:list:*")
    delete_cache_pattern("items:search:*")
    return None

class UserMergeRequest(BaseModel):
    source_id: int
    target_id: int

@public_router.post("/pubsub/user-events")
async def handle_user_pubsub_events(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Handle GCP Pub/Sub Push Notifications.
    """
    import base64
    import json
    payload = await request.json()
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
                from sqlalchemy import update
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
    from sqlalchemy import update
    stmt = update(Item).where(Item.user_id == req.source_id).values(user_id=req.target_id)
    await db.execute(stmt)
    await db.commit()
    delete_cache_pattern(f"items:user:{req.source_id}:*")
    delete_cache_pattern(f"items:user:{req.target_id}:*")
    return {"message": f"Successfully migrated items from user {req.source_id} to {req.target_id}"}
