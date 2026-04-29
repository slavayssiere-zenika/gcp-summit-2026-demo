"""
assignments_router.py — Routes d'assignation compétences/utilisateurs.
"""

import base64
import json
import logging
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import delete, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from cache import delete_cache_pattern, get_cache, set_cache
from database import get_db
from src.auth import verify_jwt
from src.competencies.helpers import get_user_from_api, serialize_competency
from src.competencies.models import Competency, CompetencyEvaluation, user_competency
from src.competencies.schemas import CompetencyResponse

logger = logging.getLogger(__name__)
CACHE_TTL = 60

router = APIRouter(prefix="", tags=["assignments"], dependencies=[Depends(verify_jwt)])
public_router = APIRouter(prefix="", tags=["assignments_public"])


class UserMergeRequest(BaseModel):
    source_id: int
    target_id: int


@router.post("/user/{user_id}/assign/bulk", status_code=200)
async def assign_competencies_bulk(user_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """Assigne en masse une liste de compétences à un utilisateur (idempotent via ON CONFLICT DO NOTHING)."""
    body = await request.json()
    competency_ids = body.get("competency_ids", [])
    if not competency_ids:
        return {"assigned": 0, "skipped": 0, "message": "Aucune compétence fournie."}

    await get_user_from_api(user_id, request)
    existing = (await db.execute(select(Competency.id).where(Competency.id.in_(competency_ids)))).scalars().all()
    valid_ids = set(existing)
    invalid_ids = [cid for cid in competency_ids if cid not in valid_ids]

    for cid in valid_ids:
        await db.execute(
            pg_insert(user_competency).values(user_id=user_id, competency_id=cid, created_at=datetime.utcnow())
            .on_conflict_do_nothing(index_elements=["user_id", "competency_id"])
        )

    await db.commit()
    delete_cache_pattern(f"competencies:user:{user_id}:*")
    return {"assigned": len(valid_ids), "skipped": len(invalid_ids), "invalid_ids": invalid_ids,
            "message": f"{len(valid_ids)} compétences assignées à l'utilisateur {user_id}."}


@router.post("/user/{user_id}/assign/{competency_id}", status_code=201)
async def assign_competency_to_user(user_id: int, competency_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """Assigne une compétence unique à un utilisateur (idempotent)."""
    await get_user_from_api(user_id, request)
    comp = (await db.execute(select(Competency).where(Competency.id == competency_id))).scalars().first()
    if not comp:
        raise HTTPException(status_code=404, detail="Competency not found")
    await db.execute(
        pg_insert(user_competency).values(user_id=user_id, competency_id=competency_id, created_at=datetime.utcnow())
        .on_conflict_do_nothing(index_elements=["user_id", "competency_id"])
    )
    await db.commit()
    delete_cache_pattern(f"competencies:user:{user_id}:*")
    return {"user_id": user_id, "competency_id": competency_id, "status": "assigned"}


@router.delete("/user/{user_id}/evaluations", status_code=204)
async def clear_user_evaluations(user_id: int, db: AsyncSession = Depends(get_db), jwt_payload: dict = Depends(verify_jwt)):
    """(Admin Only) Supprime toutes les CompetencyEvaluation pour un utilisateur."""
    if jwt_payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Privilèges administrateur requis.")
    await db.execute(delete(CompetencyEvaluation).where(CompetencyEvaluation.user_id == user_id))
    await db.commit()
    delete_cache_pattern(f"competencies:evaluations:user:{user_id}:*")
    return Response(status_code=204)


@router.delete("/user/{user_id}/remove/{competency_id}", status_code=204)
async def remove_competency_from_user(user_id: int, competency_id: int, db: AsyncSession = Depends(get_db)):
    """Supprime l'assignation d'une compétence pour un utilisateur."""
    await db.execute(user_competency.delete().where(
        user_competency.c.user_id == user_id, user_competency.c.competency_id == competency_id
    ))
    await db.commit()
    delete_cache_pattern(f"competencies:user:{user_id}:*")
    return Response(status_code=204)


@router.get("/user/{user_id}", response_model=List[CompetencyResponse])
async def list_user_competencies(user_id: int, db: AsyncSession = Depends(get_db)):
    """Retourne toutes les compétences assignées à un utilisateur."""
    cache_key = f"competencies:user:{user_id}:list"
    cached = get_cache(cache_key)
    if cached:
        return [CompetencyResponse(**c) for c in cached]
    results = (await db.execute(
        select(Competency).join(user_competency, Competency.id == user_competency.c.competency_id)
        .filter(user_competency.c.user_id == user_id)
    )).scalars().all()
    items = [CompetencyResponse(**serialize_competency(c)) for c in results]
    set_cache(cache_key, [i.model_dump() for i in items], CACHE_TTL)
    return items


@router.post("/internal/users/merge")
async def merge_users(req: UserMergeRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Endpoint interne : fusionne les compétences de source_id vers target_id."""
    if not request.headers.get("Authorization"):
        raise HTTPException(status_code=401, detail="Missing authorization")
    source_comps = (await db.execute(select(user_competency.c.competency_id).where(user_competency.c.user_id == req.source_id))).scalars().all()
    target_comps = (await db.execute(select(user_competency.c.competency_id).where(user_competency.c.user_id == req.target_id))).scalars().all()
    for cid in set(source_comps) - set(target_comps):
        await db.execute(
            pg_insert(user_competency).values(user_id=req.target_id, competency_id=cid, created_at=datetime.utcnow())
            .on_conflict_do_nothing(index_elements=["user_id", "competency_id"])
        )
    await db.execute(user_competency.delete().where(user_competency.c.user_id == req.source_id))
    await db.commit()
    delete_cache_pattern(f"competencies:user:{req.source_id}:*")
    delete_cache_pattern(f"competencies:user:{req.target_id}:*")
    return {"message": f"Successfully migrated competencies from user {req.source_id} to {req.target_id}"}


@router.delete("/user/{user_id}/clear", status_code=204)
async def clear_user_competencies(user_id: int, db: AsyncSession = Depends(get_db), jwt_payload: dict = Depends(verify_jwt)):
    """(Admin Only) Supprime toutes les assignations de compétences pour un utilisateur."""
    if jwt_payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Privilèges administrateur requis.")
    await db.execute(user_competency.delete().where(user_competency.c.user_id == user_id))
    await db.commit()
    delete_cache_pattern(f"competencies:user:{user_id}:*")
    return Response(status_code=204)


@public_router.post("/pubsub/user-events")
async def handle_user_pubsub_events(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle GCP Pub/Sub Push Notifications pour les événements utilisateurs."""
    payload = await request.json()
    message = payload.get("message")
    if not message or "data" not in message:
        return {"status": "ignored"}
    try:
        event_data = json.loads(base64.b64decode(message["data"]).decode("utf-8"))
        if event_data.get("event") == "user.merged":
            src = event_data.get("data", {}).get("source_id")
            tgt = event_data.get("data", {}).get("target_id")
            if src and tgt:
                await db.execute(update(user_competency).where(user_competency.c.user_id == src).values(user_id=tgt))
                await db.execute(update(CompetencyEvaluation).where(CompetencyEvaluation.user_id == src).values(user_id=tgt))
                await db.commit()
                delete_cache_pattern(f"competencies:user:{src}:*")
                delete_cache_pattern(f"competencies:user:{tgt}:*")
                delete_cache_pattern("competencies:evaluation:*")
        return {"status": "processed"}
    except Exception as e:
        logger.error(f"Error processing Pub/Sub event: {e}")
        return {"status": "error", "detail": str(e)}
