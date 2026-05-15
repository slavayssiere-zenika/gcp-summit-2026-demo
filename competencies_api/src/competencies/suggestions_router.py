"""
suggestions_router.py — Routes de gestion des suggestions de compétences.

Extrait de competencies_router.py (God module) — 2026-05-14.

Routes :
  POST   /suggestions
  GET    /suggestions
  PATCH  /suggestions/{suggestion_id}/review
"""

import logging
from datetime import datetime, timezone

from cache import delete_cache_pattern
from shared.database import get_db
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from shared.auth.jwt import verify_jwt
from src.competencies.helpers import _generate_aliases_for_competency, trigger_taxonomy_cache_invalidation
from src.competencies.models import Competency, CompetencySuggestion
from src.competencies.schemas import (
    CompetencySuggestionCreate,
    CompetencySuggestionResponse,
    SuggestionReviewRequest,
)

logger = logging.getLogger(__name__)
CACHE_TTL = 60

router = APIRouter(prefix="", tags=["competency-suggestions"], dependencies=[Depends(verify_jwt)])


@router.post(
    "/suggestions", response_model=CompetencySuggestionResponse, status_code=201
)
async def create_competency_suggestion(
    payload: CompetencySuggestionCreate, db: AsyncSession = Depends(get_db)
):
    """Soumet une suggestion de compétence (idempotente — incrémente occurrence_count si PENDING_REVIEW existant)."""
    name_clean = payload.name.strip()
    if not name_clean:
        raise HTTPException(
            status_code=422, detail="Le nom de la suggestion ne peut pas être vide."
        )

    existing = (
        (
            await db.execute(
                select(CompetencySuggestion)
                .where(func.lower(CompetencySuggestion.name) == name_clean.lower())
                .where(CompetencySuggestion.status == "PENDING_REVIEW")
            )
        )
        .scalars()
        .first()
    )

    if existing:
        existing.occurrence_count += 1
        existing.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await db.commit()
        await db.refresh(existing)
        return CompetencySuggestionResponse.model_validate(existing)

    new_suggestion = CompetencySuggestion(
        name=name_clean,
        source=payload.source,
        context=payload.context[:2000] if payload.context else None,
        status="PENDING_REVIEW",
        occurrence_count=1,
    )
    db.add(new_suggestion)
    await db.commit()
    await db.refresh(new_suggestion)
    logger.info(
        f"[Suggestions] Nouvelle suggestion créée : '{name_clean}' (source={payload.source})"
    )
    return CompetencySuggestionResponse.model_validate(new_suggestion)


@router.get("/suggestions", response_model=list[CompetencySuggestionResponse])
async def list_competency_suggestions(
    status: str = Query("PENDING_REVIEW"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Liste les suggestions triées par occurrence décroissante (signal marché)."""
    rows = (
        (
            await db.execute(
                select(CompetencySuggestion)
                .where(CompetencySuggestion.status == status)
                .order_by(CompetencySuggestion.occurrence_count.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [CompetencySuggestionResponse.model_validate(r) for r in rows]


@router.patch(
    "/suggestions/{suggestion_id}/review", response_model=CompetencySuggestionResponse
)
async def review_competency_suggestion(
    suggestion_id: int,
    payload: SuggestionReviewRequest,
    bg_tasks: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_db),
    jwt_payload: dict = Depends(verify_jwt),
):
    """(Admin) Accepte ou rejette une suggestion. Si ACCEPT : crée la compétence dans la taxonomie."""
    if jwt_payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Privilèges administrateur requis.")
    if payload.action not in ("ACCEPT", "REJECT"):
        raise HTTPException(
            status_code=422, detail="action doit être 'ACCEPT' ou 'REJECT'."
        )

    suggestion = (
        (
            await db.execute(
                select(CompetencySuggestion).where(
                    CompetencySuggestion.id == suggestion_id
                )
            )
        )
        .scalars()
        .first()
    )
    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggestion introuvable.")
    if suggestion.status != "PENDING_REVIEW":
        raise HTTPException(
            status_code=409,
            detail=f"La suggestion est déjà en statut '{suggestion.status}'.",
        )

    if payload.action == "ACCEPT":
        existing_comp = (
            (
                await db.execute(
                    select(Competency).where(
                        func.lower(Competency.name) == suggestion.name.lower()
                    )
                )
            )
            .scalars()
            .first()
        )
        if not existing_comp:
            new_comp = Competency(
                name=suggestion.name,
                description=payload.description
                or f"Importé depuis les suggestions (source: {suggestion.source})",
                parent_id=payload.parent_id,
            )
            gen_aliases = await _generate_aliases_for_competency(suggestion.name)
            if gen_aliases:
                new_comp.aliases = gen_aliases
            db.add(new_comp)
            await db.flush()
            delete_cache_pattern("competencies:*")
            trigger_taxonomy_cache_invalidation(bg_tasks, request)
        suggestion.status = "ACCEPTED"
    else:
        suggestion.status = "REJECTED"

    suggestion.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.commit()
    await db.refresh(suggestion)
    return CompetencySuggestionResponse.model_validate(suggestion)
