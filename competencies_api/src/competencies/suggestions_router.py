"""
suggestions_router.py — Routes de gestion des suggestions de compétences.

Extrait de competencies_router.py (God module) — 2026-05-14.

Routes :
  POST   /suggestions
  GET    /suggestions
  PATCH  /suggestions/{suggestion_id}/review
"""

import difflib
import logging
from datetime import datetime, timezone

from shared.cache import clear_namespace
from shared.database import get_db
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy import func, delete
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


def clean_generic_suffixes(text: str) -> str:
    """Nettoie les suffixes technologiques très fréquents pour améliorer la déduplication."""
    t = text.lower().strip()
    for suffix in [" framework", " library", " api", " container", " cloud", " system", " tool", " js", " ts"]:
        if t.endswith(suffix):
            t = t[:-len(suffix)].strip()
    return t


@router.post(
    "/suggestions", response_model=CompetencySuggestionResponse, status_code=201
)
async def create_competency_suggestion(
    payload: CompetencySuggestionCreate, db: AsyncSession = Depends(get_db)
):
    """Soumet une suggestion de compétence (idempotente avec déduplication floue SequenceMatcher)."""
    name_clean = payload.name.strip()
    if not name_clean:
        raise HTTPException(
            status_code=422, detail="Le nom de la suggestion ne peut pas être vide."
        )

    # 1. Déduplication floue contre les compétences existantes et leurs aliases
    comp_result = await db.execute(select(Competency))
    existing_competencies = comp_result.scalars().all()

    cleaned_name = clean_generic_suffixes(name_clean)
    FUZZY_THRESHOLD = 0.6

    for comp in existing_competencies:
        cleaned_comp = clean_generic_suffixes(comp.name)
        # Correspondance floue avec le nom canonique
        ratio = difflib.SequenceMatcher(None, cleaned_name, cleaned_comp).ratio()
        if ratio >= FUZZY_THRESHOLD:
            logger.info(
                f"[Suggestions] Déduplication floue : '{name_clean}' est très proche "
                f"de la compétence '{comp.name}' (ratio={ratio:.2f}). Ignorée."
            )
            mock_suggestion = CompetencySuggestion(
                id=0,
                name=comp.name,
                source=payload.source,
                context=payload.context,
                status="ACCEPTED",
                occurrence_count=1,
            )
            return CompetencySuggestionResponse.model_validate(mock_suggestion)

        # Correspondance floue avec les aliases
        if comp.aliases:
            for alias in comp.aliases.split(','):
                alias_clean = alias.strip()
                if alias_clean:
                    cleaned_alias = clean_generic_suffixes(alias_clean)
                    ratio_alias = difflib.SequenceMatcher(None, cleaned_name, cleaned_alias).ratio()
                    if ratio_alias >= FUZZY_THRESHOLD:
                        logger.info(
                            f"[Suggestions] Déduplication floue : '{name_clean}' est très proche "
                            f"de l'alias '{alias_clean}' de '{comp.name}' (ratio={ratio_alias:.2f}). Ignorée."
                        )
                        mock_suggestion = CompetencySuggestion(
                            id=0,
                            name=comp.name,
                            source=payload.source,
                            context=payload.context,
                            status="ACCEPTED",
                            occurrence_count=1,
                        )
                        return CompetencySuggestionResponse.model_validate(mock_suggestion)

    # 2. Déduplication floue contre les suggestions en attente (PENDING_REVIEW)
    sug_result = await db.execute(
        select(CompetencySuggestion).where(CompetencySuggestion.status == "PENDING_REVIEW")
    )
    pending_suggestions = sug_result.scalars().all()

    for sug in pending_suggestions:
        cleaned_sug = clean_generic_suffixes(sug.name)
        ratio_sug = difflib.SequenceMatcher(None, cleaned_name, cleaned_sug).ratio()
        if ratio_sug >= FUZZY_THRESHOLD:
            logger.info(
                f"[Suggestions] Déduplication floue : '{name_clean}' fusionnée avec "
                f"la suggestion existante '{sug.name}' (ratio={ratio_sug:.2f})."
            )
            sug.occurrence_count += 1
            if payload.context and payload.context not in (sug.context or ""):
                if sug.context:
                    sug.context = f"{sug.context} | {payload.context}"[:2000]
                else:
                    sug.context = payload.context[:2000]
            sug.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            await db.commit()
            await db.refresh(sug)
            return CompetencySuggestionResponse.model_validate(sug)

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
                is_to_acquire=(suggestion.source == "mission"),
            )
            gen_aliases = await _generate_aliases_for_competency(suggestion.name)
            if gen_aliases:
                new_comp.aliases = gen_aliases
            db.add(new_comp)
            await db.flush()
            await clear_namespace("competencies:")
            trigger_taxonomy_cache_invalidation(bg_tasks, request)
        suggestion.status = "ACCEPTED"
    else:
        suggestion.status = "REJECTED"

    suggestion.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.commit()
    await db.refresh(suggestion)
    return CompetencySuggestionResponse.model_validate(suggestion)


@router.delete("/suggestions", status_code=204)
async def clear_all_competency_suggestions(
    db: AsyncSession = Depends(get_db),
    jwt_payload: dict = Depends(verify_jwt),
):
    """(Admin) Supprime définitivement toutes les suggestions de compétences de la base."""
    if jwt_payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Opération refusée : privilèges administrateur requis.")

    await db.execute(delete(CompetencySuggestion))
    await db.commit()
    logger.info("[Suggestions] Toutes les suggestions de compétences ont été purgées avec succès.")
    return None
