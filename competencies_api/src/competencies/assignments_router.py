"""
assignments_router.py — Routes d'assignation compétences/utilisateurs.
"""

import asyncio
import base64
import json
import logging
import os
from datetime import datetime, timezone

from shared.cache import clear_namespace, get_cache, set_cache
from shared.database import get_db
from shared.semaphore_utils import acquire_shielded
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import delete, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from shared.auth.jwt import verify_jwt
from src.competencies.helpers import get_user_from_api, serialize_competency
from src.competencies.models import Competency, CompetencyEvaluation, user_competency
from src.competencies.schemas import CompetencyResponse, PaginationResponse
from sqlalchemy import func

logger = logging.getLogger(__name__)
CACHE_TTL = 60

router = APIRouter(prefix="", tags=["assignments"], dependencies=[Depends(verify_jwt)])
public_router = APIRouter(prefix="", tags=["assignments_public"])

# ── Protection pool DB — semaphore pour /user/{id}/assign/bulk ────────────────
# Limite le nombre d'appels assign/bulk traités SIMULTANÉMENT par instance.
# Quand le semaphore est plein → HTTP 429, ce qui déclenche le retry
# exponentiel de l'appelant (cv_storage_service, bulk_service) au lieu de
# laisser SQLAlchemy lever une QueuePool Overflow (HTTP 500 non retriable).
#
# Valeur : DB_POOL_SIZE / ~2 connexions par assign/bulk = 10/2 = 5.
# Configurable via ASSIGN_BULK_SEMAPHORE pour ajuster sans redéploiement code.
# ⚠️ GLOBAL PERSISTANT : utiliser acquire_shielded(_ASSIGN_BULK_SEM) (shared.semaphore_utils).
_ASSIGN_BULK_SEM: asyncio.Semaphore | None = None


def _get_assign_sem() -> asyncio.Semaphore:
    global _ASSIGN_BULK_SEM
    if _ASSIGN_BULK_SEM is None:
        limit = int(os.getenv("ASSIGN_BULK_SEMAPHORE", "5"))
        _ASSIGN_BULK_SEM = asyncio.Semaphore(limit)
        logger.info("[assign/bulk] ASSIGN_BULK_SEMAPHORE=%d", limit)
    return _ASSIGN_BULK_SEM


class UserMergeRequest(BaseModel):
    source_id: int
    target_id: int


@router.post("/user/{user_id}/assign/bulk", status_code=200)
async def assign_competencies_bulk(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    jwt_payload: dict = Depends(verify_jwt),
):
    """Assigne en masse une liste de compétences à un utilisateur (idempotent via ON CONFLICT DO NOTHING).

    Protégé par ASSIGN_BULK_SEMAPHORE : retourne HTTP 429 si le pool est saturé,
    ce qui permet aux appelants (cv_storage_service, bulk_service) de retenter
    avec backoff exponentiel au lieu de récupérer un 500 pool overflow non retriable.
    Retourne 503 si un service aval (users_api) est temporairement injoignable.
    """
    is_privileged = jwt_payload.get("role") in ("admin", "rh", "service_account")
    is_self = str(user_id) == str(jwt_payload.get("sub"))
    if not is_privileged and not is_self:
        raise HTTPException(
            status_code=403,
            detail="Accès refusé : opération non autorisée pour cet utilisateur.",
        )
    sem = _get_assign_sem()
    if sem.locked():
        # Tous les slots occupés : signalé 429 AVANT d'acquérir une connexion DB
        raise HTTPException(
            status_code=429,
            detail="assign/bulk: service sous charge — réessayer dans quelques secondes.",
        )
    async with acquire_shielded(sem):
        body = await request.json()
        competency_ids = body.get("competency_ids", [])
        if not competency_ids:
            return {"assigned": 0, "skipped": 0, "message": "Aucune compétence fournie."}

        # Validation de l'utilisateur via users_api — peut échouer sous charge
        try:
            await get_user_from_api(user_id, request)
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning(
                "[assign/bulk] Impossible de valider user_id=%d via users_api : %s",
                user_id, exc,
            )
            raise HTTPException(
                status_code=503,
                detail="assign/bulk: users_api temporairement injoignable — réessayer dans quelques secondes.",
            )

        try:
            existing = (
                (
                    await db.execute(
                        select(Competency.id).where(Competency.id.in_(competency_ids))
                    )
                )
                .scalars()
                .all()
            )
            valid_ids = set(existing)
            invalid_ids = [cid for cid in competency_ids if cid not in valid_ids]

            # P2.3 — Batch INSERT : 1 roundtrip pour N competences au lieu de N roundtrips.
            # Reduction hold time connexion DB : ~33ms → ~4ms (-88%).
            # Semantique identique : ON CONFLICT DO NOTHING garantit l idempotence.
            if valid_ids:
                rows = [
                    {
                        "user_id": user_id,
                        "competency_id": cid,
                        "created_at": datetime.now(timezone.utc).replace(tzinfo=None),
                    }
                    for cid in valid_ids
                ]
                await db.execute(
                    pg_insert(user_competency)
                    .values(rows)
                    .on_conflict_do_nothing(index_elements=["user_id", "competency_id"])
                )

            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.error(
                "[assign/bulk] Erreur DB pour user_id=%d : %s",
                user_id, exc,
            )
            raise HTTPException(
                status_code=503,
                detail="assign/bulk: erreur base de données temporaire — réessayer dans quelques secondes.",
            )

        await clear_namespace(f"competencies:user:{user_id}:")
        return {
            "assigned": len(valid_ids),
            "skipped": len(invalid_ids),
            "invalid_ids": invalid_ids,
            "message": f"{len(valid_ids)} compétences assignées à l'utilisateur {user_id}.",
        }


@router.post("/user/{user_id}/assign/{competency_id}", status_code=201)
async def assign_competency_to_user(
    user_id: int,
    competency_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    jwt_payload: dict = Depends(verify_jwt),
):
    """Assigne une compétence unique à un utilisateur (idempotent)."""
    is_privileged = jwt_payload.get("role") in ("admin", "rh", "service_account")
    is_self = str(user_id) == str(jwt_payload.get("sub"))
    if not is_privileged and not is_self:
        raise HTTPException(
            status_code=403,
            detail="Accès refusé : opération non autorisée pour cet utilisateur.",
        )
    await get_user_from_api(user_id, request)
    comp = (
        (await db.execute(select(Competency).where(Competency.id == competency_id)))
        .scalars()
        .first()
    )
    if not comp:
        raise HTTPException(status_code=404, detail="Competency not found")
    await db.execute(
        pg_insert(user_competency)
        .values(
            user_id=user_id,
            competency_id=competency_id,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        .on_conflict_do_nothing(index_elements=["user_id", "competency_id"])
    )
    await db.commit()
    await clear_namespace(f"competencies:user:{user_id}:")
    return {"user_id": user_id, "competency_id": competency_id, "status": "assigned"}


@router.delete("/user/{user_id}/evaluations", status_code=204)
async def clear_user_evaluations(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    jwt_payload: dict = Depends(verify_jwt),
):
    """(Admin Only) Supprime toutes les CompetencyEvaluation pour un utilisateur."""
    if jwt_payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Privilèges administrateur requis.")
    await db.execute(
        delete(CompetencyEvaluation).where(CompetencyEvaluation.user_id == user_id)
    )
    await db.commit()
    await clear_namespace(f"competencies:evaluations:user:{user_id}:")
    return Response(status_code=204)


@router.delete("/user/{user_id}/remove/{competency_id}", status_code=204)
async def remove_competency_from_user(
    user_id: int,
    competency_id: int,
    db: AsyncSession = Depends(get_db),
    jwt_payload: dict = Depends(verify_jwt),
):
    """Supprime l'assignation d'une compétence pour un utilisateur."""
    is_privileged = jwt_payload.get("role") in ("admin", "rh", "service_account")
    is_self = str(user_id) == str(jwt_payload.get("sub"))
    if not is_privileged and not is_self:
        raise HTTPException(
            status_code=403,
            detail="Accès refusé : opération non autorisée pour cet utilisateur.",
        )
    await db.execute(
        user_competency.delete().where(
            user_competency.c.user_id == user_id,
            user_competency.c.competency_id == competency_id,
        )
    )
    await db.commit()
    await clear_namespace(f"competencies:user:{user_id}:")
    return Response(status_code=204)


@router.get("/user/{user_id}", response_model=PaginationResponse[CompetencyResponse])
async def list_user_competencies(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    jwt_payload: dict = Depends(verify_jwt),
):
    """Retourne toutes les compétences assignées à un utilisateur."""
    is_privileged = jwt_payload.get("role") in ("admin", "rh", "service_account")
    is_self = str(user_id) == str(jwt_payload.get("sub"))
    if not is_privileged and not is_self:
        raise HTTPException(
            status_code=403,
            detail="Accès refusé : opération non autorisée pour cet utilisateur.",
        )
    cache_key = f"competencies:user:{user_id}:list:skip:{skip}:limit:{limit}"
    cached = await get_cache(cache_key)
    if cached:
        return PaginationResponse(**cached)

    total = (
        await db.execute(
            select(func.count())
            .select_from(user_competency)
            .filter(user_competency.c.user_id == user_id)
        )
    ).scalar()

    results = (
        (
            await db.execute(
                select(Competency)
                .join(user_competency, Competency.id == user_competency.c.competency_id)
                .filter(user_competency.c.user_id == user_id)
                .offset(skip)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    items = [CompetencyResponse(**serialize_competency(c)) for c in results]

    resp = PaginationResponse(
        items=[i.model_dump() for i in items], total=total, skip=skip, limit=limit
    )
    await set_cache(cache_key, resp.model_dump(), CACHE_TTL)
    return resp


@router.post("/internal/users/merge")
async def merge_users(
    req: UserMergeRequest, request: Request, db: AsyncSession = Depends(get_db)
):
    """Endpoint interne : fusionne les compétences de source_id vers target_id."""
    if not request.headers.get("Authorization"):
        raise HTTPException(status_code=401, detail="Missing authorization")
    source_comps = (
        (
            await db.execute(
                select(user_competency.c.competency_id).where(
                    user_competency.c.user_id == req.source_id
                )
            )
        )
        .scalars()
        .all()
    )
    target_comps = (
        (
            await db.execute(
                select(user_competency.c.competency_id).where(
                    user_competency.c.user_id == req.target_id
                )
            )
        )
        .scalars()
        .all()
    )
    for cid in set(source_comps) - set(target_comps):
        await db.execute(
            pg_insert(user_competency)
            .values(
                user_id=req.target_id,
                competency_id=cid,
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
            .on_conflict_do_nothing(index_elements=["user_id", "competency_id"])
        )
    await db.execute(
        user_competency.delete().where(user_competency.c.user_id == req.source_id)
    )
    await db.commit()
    await clear_namespace(f"competencies:user:{req.source_id}:")
    await clear_namespace(f"competencies:user:{req.target_id}:")
    return {
        "message": f"Successfully migrated competencies from user {req.source_id} to {req.target_id}"
    }


@router.delete("/user/{user_id}/clear", status_code=204)
async def clear_user_competencies(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    jwt_payload: dict = Depends(verify_jwt),
):
    """(Admin Only) Supprime toutes les assignations de compétences pour un utilisateur."""
    if jwt_payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Privilèges administrateur requis.")
    await db.execute(
        user_competency.delete().where(user_competency.c.user_id == user_id)
    )
    await db.commit()
    await clear_namespace(f"competencies:user:{user_id}:")
    return Response(status_code=204)


@public_router.post("/pubsub/user-events")
async def handle_user_pubsub_events(
    request: Request, db: AsyncSession = Depends(get_db)
):
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
                await db.execute(
                    update(user_competency)
                    .where(user_competency.c.user_id == src)
                    .values(user_id=tgt)
                )
                await db.execute(
                    update(CompetencyEvaluation)
                    .where(CompetencyEvaluation.user_id == src)
                    .values(user_id=tgt)
                )
                await db.commit()
                await clear_namespace(f"competencies:user:{src}:")
                await clear_namespace(f"competencies:user:{tgt}:")
                await clear_namespace("competencies:evaluation:")
        return {"status": "processed"}
    except Exception as e:
        logger.error(f"Error processing Pub/Sub event: {e}")
        return {"status": "error", "detail": str(e)}
