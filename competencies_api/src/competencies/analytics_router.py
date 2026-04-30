"""
analytics_router.py — Routes analytics : couverture des compétences, skill-gaps, consultants similaires.

Routes :
  GET    /stats/coverage
  GET    /evaluations/scoring-stats
  GET    /analytics/agency-coverage
  GET    /analytics/skill-gaps
  GET    /analytics/similar-consultants/{user_id}
"""
import logging
import os
from collections import defaultdict
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from opentelemetry.propagate import inject
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from cache import get_cache, set_cache
from database import get_db
from src.auth import verify_jwt
from src.competencies.models import Competency, CompetencyEvaluation, user_competency
from src.competencies.schemas import (
    AgencyCompetencyCoverage, AgencyCompetencyItem,
    SimilarConsultant, SimilarConsultantsResult,
    SkillGapItem, SkillGapResult,
)

logger = logging.getLogger(__name__)
USERS_API_URL = os.getenv("USERS_API_URL", "http://users_api:8000")

router = APIRouter(prefix="", tags=["analytics"], dependencies=[Depends(verify_jwt)])

@router.get("/stats/coverage")
async def get_competency_coverage(_: dict = Depends(verify_jwt), db: AsyncSession = Depends(get_db)):
    """Retourne le nombre de consultants ayant au moins 1 compétence assignée (Data Quality Dashboard)."""
    users_with_competencies = (await db.execute(
        select(func.count(func.distinct(user_competency.c.user_id)))
    )).scalar_one() or 0
    return {"users_with_competencies": users_with_competencies, "total_users": users_with_competencies}


@router.get("/evaluations/scoring-stats")
async def get_scoring_stats(
    min_scored_count: int = Query(10, ge=1),
    _: dict = Depends(verify_jwt),
    db: AsyncSession = Depends(get_db),
):
    """Statistiques agrégées du scoring IA — utilisé par le Data Quality Dashboard."""
    total_with_comps = (await db.execute(select(func.count(func.distinct(user_competency.c.user_id))))).scalar_one() or 1

    scored_per_user_sub = (
        select(CompetencyEvaluation.user_id, func.count(CompetencyEvaluation.id).label("scored_count"))
        .where(CompetencyEvaluation.ai_score.isnot(None))
        .group_by(CompetencyEvaluation.user_id)
        .subquery()
    )
    users_ok = (await db.execute(
        select(func.count()).select_from(scored_per_user_sub).where(scored_per_user_sub.c.scored_count >= min_scored_count)
    )).scalar_one()
    avg_scored_row = (await db.execute(select(func.avg(scored_per_user_sub.c.scored_count)))).scalar_one()
    avg_scored = round(float(avg_scored_row), 1) if avg_scored_row else 0.0
    coverage_pct = min(100.0, round(100 * users_ok / max(1, total_with_comps), 1))
    st = "ok" if coverage_pct >= 80 else "warning" if coverage_pct >= 50 else "error"

    return {"total_users_with_competencies": total_with_comps, "users_with_min_scored": users_ok,
            "users_without_sufficient_score": total_with_comps - users_ok,
            "coverage_pct": coverage_pct, "avg_scored_per_user": avg_scored,
            "min_scored_count": min_scored_count, "status": st}


@router.get("/analytics/agency-coverage", response_model=AgencyCompetencyCoverage)
async def get_agency_competency_coverage(
    min_count: int = Query(1, ge=1), limit: int = Query(50, ge=1, le=200),
    request: Request = None, db: AsyncSession = Depends(get_db),
):
    """Heatmap compétences x agences — pour chaque paire (agence, compétence feuille), count + score IA moyen."""
    cache_key = f"competencies:analytics:agency-coverage:{min_count}:{limit}"
    cached = get_cache(cache_key)
    if cached:
        return AgencyCompetencyCoverage(**cached)

    auth_header = request.headers.get("Authorization") if request else None
    headers = {"Authorization": auth_header} if auth_header else {}
    inject(headers)

    agency_map: dict[int, str] = {}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(f"{USERS_API_URL.rstrip('/')}/users", params={"limit": 500}, headers=headers)
            if res.status_code == 200:
                data = res.json()
                users = data.get("items", data) if isinstance(data, dict) else data
                for u in users:
                    uid = u.get("id")
                    agency = next((tag.get("name", tag.get("value")) for tag in (u.get("tags") or [])
                                   if isinstance(tag, dict) and tag.get("category") in ("agence", "agency", "Agence")), None)
                    if uid and agency:
                        agency_map[uid] = agency
    except Exception as e:
        logger.warning(f"[analytics/agency-coverage] users_api indisponible: {e}")

    if not agency_map:
        return AgencyCompetencyCoverage(items=[], total_consultants=0, total_agencies=0)

    from sqlalchemy import case as sa_case
    stmt = (
        select(user_competency.c.user_id, user_competency.c.competency_id, Competency.name.label("competency_name"), CompetencyEvaluation.ai_score)
        .join(Competency, user_competency.c.competency_id == Competency.id)
        .outerjoin(CompetencyEvaluation,
                   (CompetencyEvaluation.user_id == user_competency.c.user_id) & (CompetencyEvaluation.competency_id == user_competency.c.competency_id))
        .where(user_competency.c.user_id.in_(list(agency_map.keys())))
        .where(~Competency.id.in_(select(Competency.parent_id).where(Competency.parent_id.isnot(None)).distinct()))
    )
    rows = (await db.execute(stmt)).all()

    agg: dict[tuple, dict] = defaultdict(lambda: {"count": 0, "scores": []})
    for row in rows:
        agency = agency_map.get(row.user_id)
        if not agency:
            continue
        key = (agency, row.competency_name)
        agg[key]["count"] += 1
        if row.ai_score is not None:
            agg[key]["scores"].append(row.ai_score)

    items = [
        AgencyCompetencyItem(agency=agency, competency=competency, count=vals["count"],
                             avg_ai_score=round(sum(vals["scores"]) / len(vals["scores"]), 2) if vals["scores"] else None)
        for (agency, competency), vals in agg.items() if vals["count"] >= min_count
    ]
    items.sort(key=lambda x: (-x.count, x.agency, x.competency))
    result = AgencyCompetencyCoverage(items=items[:limit], total_consultants=len(agency_map), total_agencies=len(set(agency_map.values())))
    set_cache(cache_key, result.model_dump(), 300)
    return result


@router.get("/analytics/skill-gaps", response_model=SkillGapResult)
async def get_skill_gaps(
    user_ids: List[int] = Query(...), competency_ids: Optional[List[int]] = Query(None),
    min_coverage: float = Query(0.0, ge=0.0, le=1.0), db: AsyncSession = Depends(get_db),
):
    """Gap de compétences dans un pool d'utilisateurs (score Jaccard / taux de couverture)."""
    if not user_ids:
        return SkillGapResult(gaps=[], pool_size=0)
    pool_size = len(user_ids)
    comps_stmt = (select(Competency).where(Competency.id.in_(competency_ids)) if competency_ids
                  else select(Competency).where(~Competency.id.in_(select(Competency.parent_id).where(Competency.parent_id.isnot(None)).distinct())))
    target_comps = (await db.execute(comps_stmt)).scalars().all()
    if not target_comps:
        return SkillGapResult(gaps=[], pool_size=pool_size)

    count_rows = {r.competency_id: r.n for r in (await db.execute(
        select(user_competency.c.competency_id, func.count(user_competency.c.user_id).label("n"))
        .where(user_competency.c.user_id.in_(user_ids))
        .where(user_competency.c.competency_id.in_([c.id for c in target_comps]))
        .group_by(user_competency.c.competency_id)
    )).all()}

    gaps = sorted([
        SkillGapItem(competency_id=c.id, competency_name=c.name,
                     consultants_with_skill=count_rows.get(c.id, 0), consultants_in_pool=pool_size,
                     coverage_pct=min(100.0, round(count_rows.get(c.id, 0) / max(1, pool_size) * 100, 1)))
        for c in target_comps if count_rows.get(c.id, 0) / pool_size <= min_coverage
    ], key=lambda x: x.coverage_pct)
    return SkillGapResult(gaps=gaps, pool_size=pool_size)


@router.get("/analytics/similar-consultants/{user_id}", response_model=SimilarConsultantsResult)
async def get_similar_consultants(user_id: int, top_n: int = Query(5, ge=1, le=20), db: AsyncSession = Depends(get_db)):
    """Trouve les consultants les plus similaires via similarité de Jaccard sur les compétences feuilles."""
    leaf_filter = ~Competency.id.in_(select(Competency.parent_id).where(Competency.parent_id.isnot(None)).distinct())
    ref_rows = (await db.execute(
        select(user_competency.c.competency_id, Competency.name)
        .join(Competency, user_competency.c.competency_id == Competency.id)
        .where(user_competency.c.user_id == user_id).where(leaf_filter)
    )).all()
    ref_set: set[int] = {r.competency_id for r in ref_rows}
    ref_names: dict[int, str] = {r.competency_id: r.name for r in ref_rows}

    if not ref_set:
        return SimilarConsultantsResult(reference_user_id=user_id, reference_competency_count=0, similar_consultants=[])

    other_rows = (await db.execute(
        select(user_competency.c.user_id, user_competency.c.competency_id, Competency.name)
        .join(Competency, user_competency.c.competency_id == Competency.id)
        .where(user_competency.c.user_id != user_id)
        .where(user_competency.c.competency_id.in_(ref_set)).where(leaf_filter)
    )).all()

    user_comp_sets: dict[int, set[int]] = defaultdict(set)
    user_comp_names: dict[int, dict[int, str]] = defaultdict(dict)
    for row in other_rows:
        user_comp_sets[row.user_id].add(row.competency_id)
        user_comp_names[row.user_id][row.competency_id] = row.name

    results = sorted([
        SimilarConsultant(user_id=uid, common_competencies=len(ref_set & other_set),
                          jaccard_score=round(len(ref_set & other_set) / len(ref_set | other_set), 3),
                          shared_competency_names=sorted([ref_names.get(cid, user_comp_names[uid].get(cid, "")) for cid in ref_set & other_set]))
        for uid, other_set in user_comp_sets.items()
    ], key=lambda x: -x.jaccard_score)[:top_n]

    return SimilarConsultantsResult(reference_user_id=user_id, reference_competency_count=len(ref_set), similar_consultants=results)
