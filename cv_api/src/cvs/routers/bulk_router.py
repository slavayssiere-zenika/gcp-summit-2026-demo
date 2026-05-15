"""bulk_router.py — Pipeline Bulk Reanalyse Vertex AI Batch."""
import asyncio
import logging
from datetime import datetime, timezone

import src.services.config as _svc_config  # _svc_config.client/_svc_config.vertex_batch_client via attribute access
from shared.database import get_db
from fastapi import (APIRouter, BackgroundTasks, Depends, HTTPException, Query,
                     Request)
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from shared.auth.jwt import verify_jwt
from src.cvs.bulk_task_state import bulk_reanalyse_manager
from src.cvs.models import CVProfile
from src.services.bulk_service import (_acquire_service_token,
                                       bg_bulk_reanalyse, bg_retry_apply)
from src.services.embedding_service import (
    reindex_mission_chunks_bg,
)
from src.services.taxonomy_service import (fetch_prompt,
                                           get_existing_competencies)

_fetch_prompt = fetch_prompt
_get_existing_competencies = get_existing_competencies
_bg_retry_apply = bg_retry_apply

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["Bulk Reanalyse"], dependencies=[Depends(verify_jwt)])


class BulkReanalyseRequest(BaseModel):
    cv_ids: list[int] | None = None
    """IDs de CVs à retraiter. Si None ou vide — tous les CVs sont traités."""


@router.post("/bulk-reanalyse/start", status_code=202)
async def start_bulk_reanalyse(
    request: Request,
    background_tasks: BackgroundTasks,
    body: BulkReanalyseRequest = BulkReanalyseRequest(),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(verify_jwt),
):
    """
    (Admin only) Lance la ré-analyse via Vertex AI Batch.

    Body JSON optionnel :
    - `cv_ids` (list[int]) : si fourni, seuls ces CVs sont traités.
      Utilisé pour récupérer les CVs sans résultat GCS après un batch partial.
      Si absent ou liste vide → tous les CVs sont traités (comportement par défaut).

    Retourne 202 immédiatement — traitement asynchrone.
    Suivre via GET /bulk-reanalyse/status.
    """
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Privilèges administrateur requis.")

    if await bulk_reanalyse_manager.is_running():
        raise HTTPException(
            status_code=409,
            detail="Une ré-analyse est déjà en cours. Utiliser /bulk-reanalyse/status pour suivre.",
        )

    # Si cv_ids fourni : total = nombre de CVs ciblés, sinon : tous les CVs
    cv_ids_filter = body.cv_ids if body.cv_ids else None
    if cv_ids_filter:
        total = len(cv_ids_filter)
    else:
        total = (await db.execute(select(func.count()).select_from(CVProfile))).scalar_one()

    # Service token longue durée (AGENTS.md §4 — jamais le JWT utilisateur pour tâche longue)
    auth_header = request.headers.get("Authorization", "")
    service_token = await _acquire_service_token(auth_header)

    await bulk_reanalyse_manager.initialize(total_cvs=total)
    background_tasks.add_task(bg_bulk_reanalyse, service_token, cv_ids_filter)

    scope = f"{total} CVs ciblés" if cv_ids_filter else f"{total} CVs (tous)"
    return {
        "success": True,
        "total_cvs": total,
        "cv_ids_filter": cv_ids_filter,
        "status": "building",
        "message": f"Ré-analyse de {scope} démarrée. Suivre via GET /bulk-reanalyse/status.",
    }



@router.get("/bulk-reanalyse/status")
async def get_bulk_reanalyse_status(_: dict = Depends(verify_jwt)):
    """
    Retourne le statut courant du pipeline de ré-analyse globale.
    Si status='batch_running', interroge Vertex pour les completion_stats.
    """
    status = await bulk_reanalyse_manager.get_status()
    if not status:
        return {"status": "idle"}

    # Enrichissement Vertex en temps réel
    if (
        status.get("status") == "batch_running"
        and status.get("batch_job_id")
        and _svc_config.vertex_batch_client
    ):
        try:
            job = await asyncio.to_thread(
                _svc_config.vertex_batch_client.batches.get,
                name=status["batch_job_id"],
            )
            status["vertex_state"] = job.state.name if hasattr(job.state, "name") else str(job.state)
            if hasattr(job, "completion_stats") and job.completion_stats:
                cs = job.completion_stats
                ok   = int(getattr(cs, "success_count",    None) or getattr(cs, "successful_count", None) or 0)
                fail = int(getattr(cs, "failed_count",     None) or getattr(cs, "error_count",      None) or 0)
                inc  = int(getattr(cs, "incomplete_count", None) or 0)
                total_raw = getattr(cs, "total_count", None)
                total = int(total_raw) if total_raw is not None else (ok + fail + inc)
                status["completion_stats"] = {
                    "total": total,
                    "completed": ok,
                    "failed": fail,
                    "percent": int(ok * 100 / max(total, 1)),
                }

        except Exception as e:
            status["vertex_poll_error"] = str(e)

    return status



@router.post("/bulk-reanalyse/cancel", status_code=200)
async def cancel_bulk_reanalyse(user: dict = Depends(verify_jwt)):
    """
    (Admin only) Annule le job Vertex AI Batch en cours.
    Utilise un 'cancel doux' : l'état passe à 'cancelled' mais dest_uri est
    préservé en Redis — le bouton 'Retry Apply' pourra rejouer la phase apply
    depuis les résultats GCS sans relancer Vertex AI.
    Pour un reset complet (suppression de l'état), appeler /bulk-reanalyse/reset.
    """
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Privilèges administrateur requis.")

    current = await bulk_reanalyse_manager.get_status()
    if current and current.get("batch_job_id") and _svc_config.vertex_batch_client:
        try:
            await asyncio.to_thread(
                _svc_config.vertex_batch_client.batches.cancel,
                name=current["batch_job_id"],
            )
            logger.info(f"[bulk_reanalyse] Job Vertex annulé : {current['batch_job_id']}")
        except Exception as e:
            logger.warning(f"[bulk_reanalyse] Cancel Vertex échoué (job peut-être déjà terminé) : {e}")

    result = await bulk_reanalyse_manager.cancel_soft(
        reason="Pipeline annulé par l'administrateur — résultats GCS préservés pour retry-apply."
    )
    dest_uri = result.get("dest_uri")
    return {
        "success": True,
        "message": "Pipeline annulé. Les résultats GCS sont préservés.",
        "can_retry_apply": bool(dest_uri),
        "dest_uri": dest_uri,
    }



@router.post("/bulk-reanalyse/reset", status_code=200)
async def reset_bulk_reanalyse(user: dict = Depends(verify_jwt)):
    """
    (Admin only) Réinitialisation complète de l'état Redis — supprime aussi dest_uri.
    Le retry-apply ne sera plus possible après cette action.
    Utiliser uniquement pour débloquer un pipeline corrompu.
    """
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Privilèges administrateur requis.")
    await bulk_reanalyse_manager.reset()
    return {"success": True, "message": "État Redis réinitialisé complètement."}



# ── Data Quality Gate ─────────────────────────────────────────────────────────


@router.get("/bulk-reanalyse/data-quality")
async def get_data_quality_report(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(verify_jwt),
):
    """
    Rapport de qualité des données peuplées par le pipeline bulk.
    Vérifie : missions, embeddings, compétences, summary, current_role,
              competency_assignment et ai_scoring (≥10 évaluations IA).
    Retourne un score 0-100 et un grade A-D.
    Cache in-process 30s (aligné sur le polling frontend).
    """
    from datetime import timedelta

    from src.services.config import _CV_CACHE
    from src.services.data_quality_service import (CACHE_TTL_SECONDS,
                                                   compute_data_quality_report)

    try:
        now = datetime.now(timezone.utc)
        cached = _CV_CACHE["data_quality"]
        if cached["value"] is not None and now < cached["expires"]:
            return cached["value"]

        report = await compute_data_quality_report(
            db=db,
            auth_header=request.headers.get("Authorization", ""),
        )

        _CV_CACHE["data_quality"]["value"] = report
        _CV_CACHE["data_quality"]["expires"] = now + timedelta(seconds=CACHE_TTL_SECONDS)

        return report

    except Exception as e:
        logger.error(f"[data-quality] Erreur calcul rapport: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur calcul data quality: {e}")





@router.post("/bulk-reanalyse/retry-apply", status_code=202)
async def retry_bulk_apply(
    request: Request,
    background_tasks: BackgroundTasks,
    user: dict = Depends(verify_jwt),
):
    """
    (Admin only) Rejoue la phase apply depuis les résultats GCS du dernier batch Vertex.
    Ne relance pas Vertex — économise temps (~35 min) et coût.
    Prérequis : un job précédent doit avoir stocké dest_uri en Redis.
    """
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Privilèges administrateur requis.")
    if await bulk_reanalyse_manager.is_running():
        raise HTTPException(status_code=409, detail="Un pipeline est déjà en cours.")

    state = await bulk_reanalyse_manager.get_status()
    if not state:
        raise HTTPException(status_code=404, detail="Aucun état Redis trouvé. Lancez d'abord un pipeline complet.")
    dest_uri = state.get("dest_uri")
    if not dest_uri:
        raise HTTPException(status_code=400, detail="dest_uri absent — impossible de retrouver les résultats GCS.")

    auth_header = request.headers.get("Authorization", "")
    service_token = await _acquire_service_token(auth_header)

    await bulk_reanalyse_manager.reset_apply_counters()
    await bulk_reanalyse_manager.update_progress(
        status="applying",
        new_log="Retry apply démarré — reprise depuis les résultats GCS existants.",
    )

    background_tasks.add_task(_bg_retry_apply, service_token, dest_uri)

    return {
        "success": True,
        "dest_uri": dest_uri,
        "message": "Retry apply démarré en arrière-plan. Suivre via GET /bulk-reanalyse/status.",
    }





@router.post("/bulk-reanalyse/reindex-mission-chunks", status_code=202)
async def reindex_mission_chunks(
    request: Request,
    background_tasks: BackgroundTasks,
    tag: str = Query(None, description="Filtre optionnel par agence (source_tag)"),
    user_id: int = Query(None, description="Filtre optionnel par user_id"),
    force: bool = Query(
        False,
        description="Si true, supprime et recrée tous les chunks (défaut: false = skip déjà indexés)",
    ),
    user: dict = Depends(verify_jwt),
):
    """(Admin only) R7 — Lance la ré-indexation des chunks de missions en arrière-plan.

    Pour chaque CVProfile :
    - 1 chunk 'profile_summary' (ROLE + SUMMARY + COMPETENCIES, sans missions)
    - N chunks 'mission' (1 par mission, toutes missions sans limite)

    force=false (défaut) : skip les profils déjà indexés (reprise sûr après restart).
    force=true : supprime et recrée tous les chunks (re-indexation complète).

    Durée estimée : 30-90 min selon la taille du corpus.
    Activer le mode chunked avec RAG_CHUNKED_SEARCH=true après indexation complète.
    """
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Privilèges administrateur requis.")

    auth_header = request.headers.get("Authorization", "")
    service_token = await _acquire_service_token(auth_header)

    background_tasks.add_task(
        reindex_mission_chunks_bg,
        tag,
        user_id,
        f"Bearer {service_token}",
        _svc_config.client,
        5,      # semaphore_count
        force,
    )

    return {
        "success": True,
        "message": (
            "Ré-indexation des chunks de missions démarrée. "
            "Suivre via les logs Cloud Run [CHUNK_REINDEX]."
        ),
        "tag_filter": tag,
        "user_id_filter": user_id,
        "force": force,
    }
