"""bulk_router.py — Pipeline Bulk Reanalyse Vertex AI Batch."""
import asyncio
import logging
import math
import os
import re
import base64
import json
import traceback
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, List

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from fastapi.security import HTTPAuthorizationCredentials
from google import genai
from google.cloud import storage as gcs_storage
from google.cloud import run_v2 as cloudrun_v2
from opentelemetry.propagate import inject
from pydantic import BaseModel
from sqlalchemy import func, delete as sa_delete, text as sa_text, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from database import get_db
from src.auth import verify_jwt, security, SECRET_KEY as _AUTH_SECRET_KEY
from src.cvs.models import CVProfile
from src.cvs.schemas import (CVImportRequest, CVImportStep, CVResponse,
    SearchCandidateResponse, SearchCandidateRequest, CVProfileResponse,
    CVFullProfileResponse, UserMergeRequest, RankedExperienceResponse)
from src.cvs.task_state import task_state_manager, tree_task_manager
from src.cvs.bulk_task_state import bulk_reanalyse_manager
from src.cvs.routers._shared import (
    USERS_API_URL, COMPETENCIES_API_URL, PROMPTS_API_URL, DRIVE_API_URL,
    ITEMS_API_URL, MISSIONS_API_URL, ANALYTICS_MCP_URL, GCP_PROJECT_ID,
    VERTEX_LOCATION, BATCH_GCS_BUCKET, CLOUDRUN_WORKSPACE, BULK_SCALE_SERVICES,
    ADMIN_SERVICE_USERNAME, ADMIN_SERVICE_PASSWORD,
    BULK_APPLY_SEMAPHORE, BULK_EMBED_SEMAPHORE, BULK_SCALE_MIN_INSTANCES,
    CV_RESPONSE_SCHEMA as _CV_RESPONSE_SCHEMA,
    RecalculateStepRequest, MultiCriteriaSearchRequest,
)
from metrics import CV_PROCESSING_TOTAL, CV_MISSING_EMBEDDINGS
from src.gemini_retry import generate_content_with_retry, embed_content_with_retry
from src.services.cv_import_service import process_cv_core
from src.services.search_service import execute_search, scale_bulk_dependencies
import src.services.config as _svc_config  # _svc_config.client/_svc_config.vertex_batch_client via attribute access
from src.services.taxonomy_service import run_taxonomy_step, fetch_prompt, get_existing_competencies
from src.services.finops import log_finops
from src.services.embedding_service import reindex_embeddings_bg
from src.services.bulk_service import bg_bulk_reanalyse, _acquire_service_token, bg_retry_apply
from src.services.utils import _build_distilled_content, _clean_llm_json, _chunk_text

_fetch_prompt = fetch_prompt
_get_existing_competencies = get_existing_competencies
_bg_retry_apply = bg_retry_apply

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["Bulk Reanalyse"], dependencies=[Depends(verify_jwt)])

@router.post("/bulk-reanalyse/start", status_code=202)
async def start_bulk_reanalyse(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(verify_jwt),
):
    """
    (Admin only) Lance la ré-analyse globale de tous les CVs via Vertex AI Batch.
    Retourne immédiatement 202 — le traitement est asynchrone.
    Utiliser GET /bulk-reanalyse/status pour suivre la progression.
    """
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Privilèges administrateur requis.")

    if await bulk_reanalyse_manager.is_running():
        raise HTTPException(
            status_code=409,
            detail="Une ré-analyse est déjà en cours. Utiliser /bulk-reanalyse/status pour suivre.",
        )

    total = (await db.execute(select(func.count()).select_from(CVProfile))).scalar_one()

    # Service token longue durée (AGENTS.md §4 — jamais le JWT utilisateur pour tâche longue)
    auth_header = request.headers.get("Authorization", "")
    service_token = await _acquire_service_token(auth_header)

    await bulk_reanalyse_manager.initialize(total_cvs=total)
    background_tasks.add_task(bg_bulk_reanalyse, service_token)

    return {
        "success": True,
        "total_cvs": total,
        "status": "building",
        "message": f"Ré-analyse de {total} CVs démarrée. Suivre via GET /bulk-reanalyse/status.",
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
    from src.services.data_quality_service import compute_data_quality_report, CACHE_TTL_SECONDS

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



