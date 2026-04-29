"""
evaluations_router.py — Routes de scoring et d'évaluation des compétences.

Routes :
  POST   /evaluations/batch/search
  POST   /evaluations/batch/users
  GET    /evaluations/user/{user_id}
  GET    /evaluations/user/{user_id}/competency/{competency_id}
  POST   /evaluations/user/{user_id}/competency/{competency_id}/user-score
  POST   /evaluations/user/{user_id}/competency/{competency_id}/ai-score
  POST   /evaluations/user/{user_id}/ai-score-all
"""

import logging
import os
from datetime import datetime
from typing import List

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Query
from opentelemetry.propagate import inject
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from cache import delete_cache_pattern
from database import get_db
from src.auth import verify_jwt
from src.competencies.ai_scoring import (
    _compute_ai_score, _score_all_bg,
    _get_or_create_evaluation, _serialize_evaluation,
)
from src.competencies.models import Competency, CompetencyEvaluation, user_competency
from src.competencies.schemas import (
    AiScoreAllResponse, BatchEvaluationRequest, BatchEvaluationResponse,
    BatchUsersEvaluationRequest, CompetencyEvaluationResponse, UserScoreRequest,
)

logger = logging.getLogger(__name__)
USERS_API_URL = os.getenv("USERS_API_URL", "http://users_api:8000")

router = APIRouter(prefix="", tags=["evaluations"], dependencies=[Depends(verify_jwt)])


@router.post("/evaluations/batch/search", response_model=BatchEvaluationResponse)
async def search_batch_evaluations(request: BatchEvaluationRequest, db: AsyncSession = Depends(get_db)):
    """Récupère en masse les évaluations pour un utilisateur et une liste de compétences."""
    if not request.competency_ids:
        return BatchEvaluationResponse(evaluations={})

    stmt = (
        select(CompetencyEvaluation, Competency.name.label("comp_name"))
        .join(Competency, CompetencyEvaluation.competency_id == Competency.id)
        .where(
            CompetencyEvaluation.user_id == request.user_id,
            CompetencyEvaluation.competency_id.in_(request.competency_ids),
        )
    )
    rows = (await db.execute(stmt)).all()
    eval_dict = {}
    evaluated_ids = set()

    for ev, comp_name in rows:
        eval_dict[ev.competency_id] = _serialize_evaluation(ev, comp_name)
        evaluated_ids.add(ev.competency_id)

    missing_ids = [cid for cid in request.competency_ids if cid not in evaluated_ids]
    if missing_ids:
        comps = (await db.execute(select(Competency).where(Competency.id.in_(missing_ids)))).scalars().all()
        for c in comps:
            eval_dict[c.id] = {
                "id": 0, "user_id": request.user_id, "competency_id": c.id, "competency_name": c.name,
                "ai_score": None, "ai_justification": None, "ai_scored_at": None,
                "user_score": None, "user_comment": None, "user_scored_at": None,
            }
    return BatchEvaluationResponse(evaluations=eval_dict)


@router.post("/evaluations/batch/users", response_model=BatchEvaluationResponse)
async def search_batch_users_evaluations(request: BatchUsersEvaluationRequest, db: AsyncSession = Depends(get_db)):
    """Récupère en masse les évaluations pour une compétence et une liste d'utilisateurs."""
    if not request.user_ids:
        return BatchEvaluationResponse(evaluations={})

    stmt = (
        select(CompetencyEvaluation, Competency.name.label("comp_name"))
        .join(Competency, CompetencyEvaluation.competency_id == Competency.id)
        .where(CompetencyEvaluation.competency_id == request.competency_id, CompetencyEvaluation.user_id.in_(request.user_ids))
    )
    rows = (await db.execute(stmt)).all()
    eval_dict = {}
    evaluated_users = set()
    comp_name = rows[0][1] if rows else ""
    if not comp_name:
        comp = (await db.execute(select(Competency).where(Competency.id == request.competency_id))).scalars().first()
        comp_name = comp.name if comp else ""

    for ev, c_name in rows:
        eval_dict[ev.user_id] = _serialize_evaluation(ev, c_name)
        evaluated_users.add(ev.user_id)

    for uid in [uid for uid in request.user_ids if uid not in evaluated_users]:
        eval_dict[uid] = {
            "id": 0, "user_id": uid, "competency_id": request.competency_id, "competency_name": comp_name,
            "ai_score": None, "ai_justification": None, "ai_scored_at": None,
            "user_score": None, "user_comment": None, "user_scored_at": None,
        }
    return BatchEvaluationResponse(evaluations=eval_dict)


@router.get("/evaluations/user/{user_id}", response_model=List[CompetencyEvaluationResponse])
async def list_user_evaluations(user_id: int, db: AsyncSession = Depends(get_db)):
    """Liste toutes les evaluations (feuilles uniquement) pour un utilisateur."""
    leaf_ids = (await db.execute(
        select(user_competency.c.competency_id)
        .where(user_competency.c.user_id == user_id)
        .where(
            ~select(Competency.id)
            .where(Competency.parent_id == user_competency.c.competency_id)
            .correlate(user_competency)
            .exists()
        )
    )).scalars().all()

    if not leaf_ids:
        return []

    rows = (await db.execute(
        select(CompetencyEvaluation, Competency.name.label("comp_name"))
        .join(Competency, CompetencyEvaluation.competency_id == Competency.id)
        .where(CompetencyEvaluation.user_id == user_id, CompetencyEvaluation.competency_id.in_(leaf_ids))
    )).all()

    evaluated_ids = {ev.competency_id for ev, _ in rows}
    result = [_serialize_evaluation(ev, comp_name) for ev, comp_name in rows]

    missing_ids = [cid for cid in leaf_ids if cid not in evaluated_ids]
    if missing_ids:
        comps = (await db.execute(select(Competency).where(Competency.id.in_(missing_ids)))).scalars().all()
        for c in comps:
            result.append({"id": 0, "user_id": user_id, "competency_id": c.id, "competency_name": c.name,
                           "ai_score": None, "ai_justification": None, "ai_scored_at": None,
                           "user_score": None, "user_comment": None, "user_scored_at": None})
    return result


@router.get("/evaluations/user/{user_id}/competency/{competency_id}", response_model=CompetencyEvaluationResponse)
async def get_user_competency_evaluation(user_id: int, competency_id: int, db: AsyncSession = Depends(get_db)):
    """Evaluation d'une competence specifique pour un utilisateur."""
    comp = (await db.execute(select(Competency).where(Competency.id == competency_id))).scalars().first()
    if not comp:
        raise HTTPException(status_code=404, detail="Competency not found")
    ev = (await db.execute(
        select(CompetencyEvaluation).where(
            CompetencyEvaluation.user_id == user_id, CompetencyEvaluation.competency_id == competency_id
        )
    )).scalars().first()
    if not ev:
        return CompetencyEvaluationResponse(id=0, user_id=user_id, competency_id=competency_id, competency_name=comp.name)
    return CompetencyEvaluationResponse(**_serialize_evaluation(ev, comp.name))


@router.post("/evaluations/user/{user_id}/competency/{competency_id}/user-score", response_model=CompetencyEvaluationResponse)
async def set_user_competency_score(user_id: int, competency_id: int, body: UserScoreRequest, db: AsyncSession = Depends(get_db)):
    """Saisie de la note manuelle du consultant pour une competence."""
    comp = (await db.execute(select(Competency).where(Competency.id == competency_id))).scalars().first()
    if not comp:
        raise HTTPException(status_code=404, detail="Competency not found")
    ev = await _get_or_create_evaluation(db, user_id, competency_id)
    ev.user_score = body.score
    ev.user_comment = body.comment
    ev.user_scored_at = datetime.utcnow()
    ev.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(ev)
    delete_cache_pattern(f"competencies:evaluations:user:{user_id}:*")
    return CompetencyEvaluationResponse(**_serialize_evaluation(ev, comp.name))


@router.post("/evaluations/user/{user_id}/competency/{competency_id}/ai-score", response_model=CompetencyEvaluationResponse)
async def trigger_ai_score_single(user_id: int, competency_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """Declenche le calcul IA pour une competence specifique."""
    comp = (await db.execute(select(Competency).where(Competency.id == competency_id))).scalars().first()
    if not comp:
        raise HTTPException(status_code=404, detail="Competency not found")
    auth_header = request.headers.get("Authorization", "")
    headers = {"Authorization": auth_header}
    inject(headers)
    score, justification = await _compute_ai_score(user_id, comp.name, headers)
    ev = await _get_or_create_evaluation(db, user_id, competency_id)
    ev.ai_score = score
    ev.ai_justification = justification
    ev.ai_scored_at = datetime.utcnow()
    ev.scoring_version = "v2"
    ev.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(ev)
    delete_cache_pattern(f"competencies:evaluations:user:{user_id}:*")
    return CompetencyEvaluationResponse(**_serialize_evaluation(ev, comp.name))



@router.post("/evaluations/user/{user_id}/ai-score-all", response_model=AiScoreAllResponse)
async def trigger_ai_score_all(user_id: int, request: Request, background_tasks: BackgroundTasks, only_missing: bool = Query(False), db: AsyncSession = Depends(get_db)):
    """Declenche le calcul IA pour toutes les competences feuilles d'un utilisateur (BackgroundTask).

    Obtient un service token longue durée via /internal/service-token avant de lancer la tâche
    pour éviter l'expiration du JWT en mid-flight (règle AGENTS.md §4).
    """
    auth_header = request.headers.get("Authorization", "")
    user_comp_subq = select(user_competency.c.competency_id).where(user_competency.c.user_id == user_id).subquery()
    
    leaf_ids_stmt = (
        select(user_competency.c.competency_id)
        .where(user_competency.c.user_id == user_id)
        .where(
            ~select(Competency.id)
            .where(Competency.parent_id == user_competency.c.competency_id)
            .where(Competency.id.in_(user_comp_subq))
            .correlate(user_competency)
            .exists()
        )
    )
    
    if only_missing:
        leaf_ids_stmt = leaf_ids_stmt.where(
            ~select(CompetencyEvaluation.id)
            .where(CompetencyEvaluation.user_id == user_id)
            .where(CompetencyEvaluation.competency_id == user_competency.c.competency_id)
            .correlate(user_competency)
            .exists()
        )

    leaf_ids = (await db.execute(leaf_ids_stmt)).scalars().all()

    comp_tuples = [(row[0], row[1]) for row in (await db.execute(
        select(Competency.id, Competency.name).where(Competency.id.in_(leaf_ids))
    )).all()]

    # Obtenir service token longue durée (AGENTS.md §4)
    bg_auth_header = auth_header
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            svc_res = await client.post(f"{USERS_API_URL.rstrip('/')}/internal/service-token", headers={"Authorization": auth_header})
            if svc_res.status_code == 200:
                service_token = svc_res.json().get("access_token")
                if service_token:
                    bg_auth_header = f"Bearer {service_token}"
    except Exception as e:
        logger.warning(f"[ai-score-all] Impossible d'obtenir un service token: {e} — fallback JWT")

    headers = {"Authorization": bg_auth_header}
    inject(headers)
    background_tasks.add_task(_score_all_bg, user_id, comp_tuples, dict(headers))
    return AiScoreAllResponse(user_id=user_id, triggered=len(comp_tuples),
                              message=f"Scoring IA lance en arriere-plan pour {len(comp_tuples)} competences.")
