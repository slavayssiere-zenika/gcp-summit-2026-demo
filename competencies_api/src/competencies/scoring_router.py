"""
scoring_router.py — Pipeline Vertex AI Batch scoring (bulk-scoring-all + résumption Cloud Scheduler).

Routes :
  POST   /evaluations/bulk-scoring-all
  GET    /bulk-scoring-all/status
  POST   /bulk-scoring-all/cancel
  POST   /bulk-scoring-all/resume        ← Cloud Scheduler keepalive (OIDC)
  POST   /bulk-scoring-all/resume/manual ← Résumption manuelle admin
"""
import asyncio
import logging
import os

import google.auth.transport.requests
import google.oauth2.id_token
import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from opentelemetry.propagate import inject
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

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
from src.competencies.models import Competency, user_competency

logger = logging.getLogger(__name__)

SCHEDULER_AUDIENCE = os.getenv("SCHEDULER_AUDIENCE", "")

router = APIRouter(prefix="", tags=["scoring"], dependencies=[Depends(verify_jwt)])

# Router Scheduler — sécurisé par validation OIDC Google (Cloud Scheduler SA)
scheduler_router = APIRouter(prefix="", tags=["analytics_scheduler"])


async def verify_scheduler_oidc(request: Request) -> None:
    """
    Valide le token OIDC Google émis par le Cloud Scheduler Service Account.
    L'audience doit correspondre à SCHEDULER_AUDIENCE (URL du service Cloud Run).
    Protège POST /bulk-scoring-all/resume contre les appels non authentifiés.
    """
    if not SCHEDULER_AUDIENCE:
        raise HTTPException(
            status_code=500,
            detail="[scheduler] SCHEDULER_AUDIENCE non configuré — appel refusé par sécurité."
        )
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="[scheduler] Token OIDC Bearer requis."
        )
    token = auth_header[7:]
    try:
        google_request = google.auth.transport.requests.Request()
        claims = google.oauth2.id_token.verify_oauth2_token(
            token, google_request, SCHEDULER_AUDIENCE
        )
        logger.debug("[scheduler] OIDC token valide — email=%s", claims.get("email"))
    except Exception as exc:
        logger.warning("[scheduler] Échec validation OIDC: %s", exc)
        raise HTTPException(
            status_code=401,
            detail=f"[scheduler] Token OIDC invalide ou expiré: {exc}"
        )


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
async def resume_bulk_scoring(
    background_tasks: BackgroundTasks,
    request: Request,
    _oidc: None = Depends(verify_scheduler_oidc),
):
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


