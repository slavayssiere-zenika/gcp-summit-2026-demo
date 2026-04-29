"""
analytics_router.py — Routes analytics, bulk-scoring global, stats et couverture.

Routes :
  POST   /evaluations/bulk-scoring-all
  GET    /bulk-scoring-all/status
  POST   /bulk-scoring-all/cancel
  POST   /bulk-scoring-all/resume        ← Cloud Scheduler keepalive (résilient au scale-to-zero)
  GET    /stats/coverage
  GET    /evaluations/scoring-stats
  GET    /analytics/agency-coverage
  GET    /analytics/skill-gaps
  GET    /analytics/similar-consultants/{user_id}
"""

import asyncio
import logging
import os
from collections import defaultdict
from typing import List, Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from opentelemetry.propagate import inject
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from starlette import status

from cache import get_cache, set_cache
from database import get_db
from src.auth import verify_jwt
from src.competencies.ai_scoring import _bulk_scoring_all_bg
from src.competencies.bulk_task_state import bulk_scoring_manager
from src.competencies.scheduler_control import set_scoring_scheduler_enabled
from src.competencies.scoring_service import (
    bg_bulk_scoring_vertex,
    _apply_scoring_results,
    _parse_scoring_results_gcs,
    BATCH_GCS_BUCKET,
    VERTEX_BATCH_MODEL,
    GCP_PROJECT_ID,
    VERTEX_LOCATION,
)
from src.competencies.models import Competency, CompetencyEvaluation, user_competency
from src.competencies.schemas import (
    AgencyCompetencyCoverage, AgencyCompetencyItem,
    SimilarConsultant, SimilarConsultantsResult,
    SkillGapItem, SkillGapResult,
)

logger = logging.getLogger(__name__)
USERS_API_URL = os.getenv("USERS_API_URL", "http://users_api:8000")

router = APIRouter(prefix="", tags=["analytics"], dependencies=[Depends(verify_jwt)])

# Router sans JWT applicatif — sécurisé par OIDC IAM (Cloud Scheduler avec SA competencies_sa).
scheduler_router = APIRouter(prefix="", tags=["analytics_scheduler"])



class BulkScoringStatus(BaseModel):
    triggered: int
    skipped: int
    total_users: int
    message: str


@router.post("/evaluations/bulk-scoring-all", response_model=BulkScoringStatus, status_code=202)
async def trigger_bulk_scoring_all(
    request: Request,
    background_tasks: BackgroundTasks,
    force: bool = Query(False, description="Si True, re-score TOUS les consultants avec compétences assignées"),
    semaphore_limit: int = Query(2, ge=1, le=5),
    min_scored_threshold: int = Query(10, ge=1),
    db: AsyncSession = Depends(get_db),
):
    """Déclenche le scoring IA pour les consultants sous le seuil (ou tous si force=True).

    Obtient un service token longue durée avant de lancer la background task (AGENTS.md §4).
    """
    auth_header = request.headers.get("Authorization", "")

    # Service token longue durée (AGENTS.md §4)
    bg_auth_header = auth_header
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            svc_res = await client.post(f"{USERS_API_URL.rstrip('/')}/internal/service-token", headers={"Authorization": auth_header})
            if svc_res.status_code == 200:
                svc_token = svc_res.json().get("access_token")
                if svc_token:
                    bg_auth_header = f"Bearer {svc_token}"
    except Exception as e:
        logger.warning(f"[bulk-scoring-all] Impossible d'obtenir service token: {e} — fallback JWT")

    headers = {"Authorization": bg_auth_header}
    inject(headers)

    if force:
        stmt = select(user_competency.c.user_id).distinct()
    else:
        scored_count_sub = (
            select(CompetencyEvaluation.user_id, func.count(CompetencyEvaluation.id).label("scored_count"))
            .where(CompetencyEvaluation.ai_score.isnot(None))
            .group_by(CompetencyEvaluation.user_id)
            .subquery()
        )
        stmt = (
            select(user_competency.c.user_id).distinct()
            .outerjoin(scored_count_sub, user_competency.c.user_id == scored_count_sub.c.user_id)
            .where(func.coalesce(scored_count_sub.c.scored_count, 0) < min_scored_threshold)
        )

    user_ids_to_score = (await db.execute(stmt)).scalars().all()
    total = len(user_ids_to_score)

    if not user_ids_to_score:
        return BulkScoringStatus(triggered=0, skipped=0, total_users=0,
                                 message=f"Aucun consultant à scorer — tous ont déjà ≥{min_scored_threshold} compétences scorées.")

    if await bulk_scoring_manager.is_running():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Un bulk scoring est déjà en cours.")

    await bulk_scoring_manager.initialize(total_users=total)

    # Choix du pipeline : Vertex AI Batch si configuré, sinon fallback séquentiel
    gcp_project = os.getenv("GCP_PROJECT_ID", "")
    gcs_bucket = os.getenv("BATCH_GCS_BUCKET", "")
    if gcp_project and gcs_bucket:
        logger.info(f"[bulk-scoring-all] → Pipeline Vertex AI Batch (project={gcp_project}, bucket={gcs_bucket})")
        background_tasks.add_task(bg_bulk_scoring_vertex, list(user_ids_to_score), dict(headers))
        # Active le Cloud Scheduler keepalive dès le déclenchement Vertex
        background_tasks.add_task(set_scoring_scheduler_enabled, True)
    else:
        logger.warning(
            "[bulk-scoring-all] GCP_PROJECT_ID ou BATCH_GCS_BUCKET absent — fallback pipeline séquentiel "
            f"(semaphore={semaphore_limit}). Configurez ces variables pour activer Vertex AI Batch."
        )
        background_tasks.add_task(_bulk_scoring_all_bg, list(user_ids_to_score), dict(headers), semaphore_limit)

    return BulkScoringStatus(triggered=total, skipped=0, total_users=total,
                             message=f"Scoring IA lancé pour {total} consultant(s) via {'Vertex AI Batch' if gcp_project and gcs_bucket else 'pipeline séquentiel'}.")



@router.get("/bulk-scoring-all/status")
async def get_bulk_scoring_status(_: dict = Depends(verify_jwt)):
    """Retourne l'état courant du batch de scoring en arrière-plan."""
    st = await bulk_scoring_manager.get_status()
    return st if st else {"status": "idle"}


@router.post("/bulk-scoring-all/cancel")
async def cancel_bulk_scoring(_: dict = Depends(verify_jwt)):
    """Annule et réinitialise l'état Redis du scoring (ne kill pas le BG task en cours)."""
    await bulk_scoring_manager.reset()
    await set_scoring_scheduler_enabled(False)
    return {"success": True, "message": "Statut de scoring réinitialisé et scheduler mis en pause."}


async def _resume_apply_bg(batch_job_id: str, dest_uri: str) -> None:
    """
    Background task : lit les résultats GCS d'un job Vertex terminé et les écrit en DB.
    Appelé par /bulk-scoring-all/resume quand le Cloud Run redémarre après scale-to-zero.
    """
    from google.cloud import storage as gcs_storage

    await bulk_scoring_manager.update_progress(
        status="applying",
        new_log=f"[resume] Reprise post-scale-to-zero — lecture GCS ({dest_uri})..."
    )
    blob_output_prefix = dest_uri.replace(f"gs://{BATCH_GCS_BUCKET}/", "")
    raw_lines: list[str] = []
    try:
        gcs_client = gcs_storage.Client()
        bucket = gcs_client.bucket(BATCH_GCS_BUCKET)
        blobs = await asyncio.to_thread(list, bucket.list_blobs(prefix=blob_output_prefix))
        for out_blob in blobs:
            if not out_blob.name.endswith(".jsonl"):
                continue
            content = await asyncio.to_thread(out_blob.download_as_text)
            raw_lines.extend(content.splitlines())
    except Exception as e:
        await bulk_scoring_manager.update_progress(status="error", error=f"[resume] GCS read: {e}")
        return

    # Reconstruit un index minimal depuis les lignes GCS (pas de scoring_index disponible)
    # On parse directement les ids embedés dans les clés "score-{user_id}-{comp_id}"
    results = []
    import json, re
    for line in raw_lines:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            key = record.get("id") or record.get("key", "")
            m = re.match(r"score-(\d+)-(\d+)", key)
            if not m:
                continue
            user_id, comp_id = int(m.group(1)), int(m.group(2))
            candidates = record.get("response", {}).get("candidates", [])
            if not candidates:
                continue
            raw = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
            if not raw.startswith("{"):
                raw_m = re.search(r"\{.*\}", raw, re.DOTALL)
                raw = raw_m.group(0) if raw_m else raw
            data = json.loads(raw)
            score = max(0.0, min(5.0, float(data.get("score", 0.0))))
            score = round(score * 2) / 2
            justification = str(data.get("justification", ""))[:500]
            results.append((user_id, comp_id, "", score, justification))
        except Exception as parse_e:
            logger.warning(f"[resume] parse GCS ligne: {parse_e}")

    await bulk_scoring_manager.update_progress(
        new_log=f"[resume] {len(results)} scores parsés depuis GCS."
    )
    nb_success, nb_errors, sample_err = await _apply_scoring_results(results)
    final_status = "error" if nb_errors > 0 else "completed"
    
    log_msg = f"[resume] Terminé — {nb_success} scores appliqués, {nb_errors} erreurs."
    if sample_err:
        log_msg += f" Raison de l'erreur: {sample_err[:150]}..."
        
    await bulk_scoring_manager.update_progress(
        status=final_status,
        success_inc=nb_success,
        error_count_inc=nb_errors,
        new_log=log_msg
    )
    logger.info(f"[resume] Apply terminé — {nb_success} scores, {nb_errors} erreurs.")
    # Pipeline terminé — pause le Cloud Scheduler keepalive
    await set_scoring_scheduler_enabled(False)



@scheduler_router.post("/bulk-scoring-all/resume")
@router.post("/bulk-scoring-all/resume/manual")
async def resume_bulk_scoring(background_tasks: BackgroundTasks):
    """
    Endpoint de résilient keepalive — deux points d'entrée :
    - /resume        : Cloud Scheduler OIDC (toutes les 15 min, sans JWT applicatif)
    - /resume/manual : bouton frontend (JWT applicatif, router protégé)

    Comportement :
    - Si aucun job batch en cours → retourne immédiatement (no-op).
    - Si status=batch_running et batch_job_id présent → poll Vertex :
        * SUCCEEDED → déclenche _resume_apply_bg en background
        * RUNNING/QUEUED/PENDING → log l'état et retourne
          si mort, ce même endpoint sera rappelé dans 2 min)
        * FAILED/CANCELLED → marque error en Redis
    - Si status=applying → ne fait rien (apply déjà en cours via BG ou résumé)
    """
    st = await bulk_scoring_manager.get_status()
    if not st or st.get("status") not in ("batch_running", "running", "error", "completed"):
        return {"action": "noop", "reason": f"status={st.get('status') if st else 'idle'}"}

    batch_job_id = st.get("batch_job_id")
    dest_uri = st.get("dest_uri")
    if not batch_job_id or not dest_uri:
        return {"action": "noop", "reason": "batch_job_id ou dest_uri absent"}

    if not GCP_PROJECT_ID or not BATCH_GCS_BUCKET:
        return {"action": "noop", "reason": "GCP_PROJECT_ID ou BATCH_GCS_BUCKET absent"}

    # Poll Vertex AI
    try:
        from google import genai
        vertex_client = genai.Client(vertexai=True, project=GCP_PROJECT_ID, location=VERTEX_LOCATION)
        job = await asyncio.to_thread(vertex_client.batches.get, name=batch_job_id)
        state_name = job.state.name if hasattr(job.state, "name") else str(job.state)
    except Exception as e:
        await bulk_scoring_manager.update_progress(
            new_log=f"[resume] poll Vertex erreur: {e}"
        )
        return {"action": "poll_error", "error": str(e)}

    state_labels = {
        "JOB_STATE_QUEUED": "En file d'attente",
        "JOB_STATE_PENDING": "Démarrage",
        "JOB_STATE_RUNNING": "Traitement en cours",
    }

    if state_name == "JOB_STATE_SUCCEEDED":
        await bulk_scoring_manager.update_progress(
            new_log="[resume] Vertex SUCCEEDED détecté — lancement apply..."
        )
        background_tasks.add_task(_resume_apply_bg, batch_job_id, dest_uri)
        return {"action": "apply_triggered", "batch_job_id": batch_job_id}

    if state_name in ("JOB_STATE_FAILED", "JOB_STATE_CANCELLED"):
        await bulk_scoring_manager.update_progress(
            status="error", error=f"[resume] Vertex job {state_name}."
        )
        return {"action": "error", "state": state_name}

    # Job encore en cours
    label = state_labels.get(state_name, state_name)
    await bulk_scoring_manager.update_progress(
        new_log=f"[resume keepalive] {label} (state={state_name})"
    )
    return {"action": "polling", "state": state_name}


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
