"""analytics_router.py — Ranking, embeddings, reanalyze, skills coverage."""
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

router = APIRouter(prefix="", tags=["CV Analytics"], dependencies=[Depends(verify_jwt)])

@router.get("/ranking/experience", response_model=List[RankedExperienceResponse])
async def get_consultants_experience_ranking(limit: int = 5, agency: Optional[str] = None, request: Request = None, db: AsyncSession = Depends(get_db)):
    """
    Retourne la liste des consultants les plus expérimentés basés sur les années d'expérience extraites des CVs.
    """
    # 1. Query candidates by years_of_experience descending
    stmt = (
        select(CVProfile)
        .filter(CVProfile.years_of_experience.is_not(None))
    )
    
    if agency:
        stmt = stmt.filter(CVProfile.source_tag.ilike(f"%{agency}%"))
        
    stmt = stmt.order_by(CVProfile.years_of_experience.desc()).limit(limit)
    
    profiles = (await db.execute(stmt)).scalars().all()
    
    # 2. Enrich with User details
    auth_header = request.headers.get("Authorization") if request else None
    headers_downstream = {"Authorization": auth_header} if auth_header else {}
    inject(headers_downstream)
    
    results = []
    seen_users = set()
    for p in profiles:
        if p.user_id in seen_users:
            continue
        seen_users.add(p.user_id)
        results.append({
            "user_id": p.user_id,
            "years_of_experience": p.years_of_experience,
            "agency": p.source_tag
        })
        
    async with httpx.AsyncClient(timeout=10.0) as http_client:
        async def fetch_user(res):
            try:
                u_res = await http_client.get(f"{USERS_API_URL.rstrip('/')}/{res['user_id']}", headers=headers_downstream)
                if u_res.status_code == 200:
                    u_data = u_res.json()
                    res["full_name"] = u_data.get("full_name")
                    res["email"] = u_data.get("email")
                    res["is_anonymous"] = u_data.get("is_anonymous", False)
            except Exception as e:
                logger.warning(f"Failed to fetch user details for {res['user_id']}: {e}")

        await asyncio.gather(*(fetch_user(res) for res in results))

    return results

class RecalculateStepRequest(BaseModel):
    step: str
    target_pillar: Optional[str] = None


@router.post("/reindex-embeddings")
async def reindex_embeddings(
    request: Request,
    background_tasks: BackgroundTasks,
    tag: Optional[str] = Query(default=None, description="Filtre par tag (agence)"),
    user_id: Optional[int] = Query(default=None, description="Filtre par user_id"),
    db: AsyncSession = Depends(get_db),
    token_payload: dict = Depends(verify_jwt),
):
    """(Admin Only) Re-calcule les embeddings vectoriels de tous les CVs avec le nouveau
    distilled_content structuré (missions + compétences), SANS relancer l'extraction LLM.
    Traitement en arrière-plan — retour immédiat. Suivre via GET /reanalyze/status.
    """
    if token_payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Privilèges administrateur requis.")
    auth_token = request.headers.get("Authorization")
    inject({"Authorization": auth_token} if auth_token else {})
    background_tasks.add_task(reindex_embeddings_bg, tag, user_id, auth_token)
    return {"message": "Re-indexation des embeddings lancée", "filter": {"tag": tag, "user_id": user_id}}


# ─────────────────────────────────────────────────────────────────────────────
# Sprint A1 — Consultants similaires (0 LLM, SQL pur pgvector)
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/reanalyze/status")
async def get_reanalyze_status(
    tag: Optional[str] = None,
    token_payload: dict = Depends(verify_jwt)
):
    """Proxy vers drive_api /status — retourne les compteurs PENDING/QUEUED/PROCESSING/IMPORTED_CV/ERROR.

    Remplace l'ancien statut Redis depuis la migration vers le pipeline Pub/Sub unifié.
    La progression est désormais observable directement dans le scanner Drive.
    """
    drive_url = f"{DRIVE_API_URL.rstrip('/')}/status"
    params = {}
    if tag:
        params["tag"] = tag
    try:
        async with httpx.AsyncClient(timeout=10.0) as http_client:
            res = await http_client.get(drive_url, params=params)
            if res.status_code == 200:
                return res.json()
            return {"status": "unavailable", "message": f"drive_api /status HTTP {res.status_code}"}
    except Exception as e:
        return {"status": "unavailable", "message": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Sprint B2 — Matching inversé Mission → CVs
# ─────────────────────────────────────────────────────────────────────────────

MISSIONS_API_URL = os.getenv("MISSIONS_API_URL", "http://missions_api:8000")



@router.get("/analytics/skills-coverage")
async def get_skills_coverage(
    agency: Optional[str] = Query(default=None, description="Filtre par agence/tag"),
    top_n: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
    token_payload: dict = Depends(verify_jwt),
):
    """Analyse la couverture de compétences du corpus de consultants Zenika.
    Retourne les N compétences les plus représentées et le nombre de consultants.
    Zéro appel LLM — agrégation SQL sur la colonne competencies_keywords[] (ARRAY).
    Réponse < 200ms. Idéal pour les requêtes stratégiques de couverture.
    """
    raw_query = sa_text("""
        SELECT unnest(competencies_keywords) AS skill,
               COUNT(DISTINCT user_id)       AS consultant_count
        FROM cv_profiles
        WHERE semantic_embedding IS NOT NULL
          AND competencies_keywords IS NOT NULL
          AND cardinality(competencies_keywords) > 0
          AND (CAST(:agency AS TEXT) IS NULL OR COALESCE(source_tag, '') ILIKE '%' || CAST(:agency AS TEXT) || '%')
        GROUP BY skill
        ORDER BY consultant_count DESC
        LIMIT :top_n
    """)

    try:
        result = await db.execute(raw_query, {"agency": agency, "top_n": top_n})
        rows = result.fetchall()
    except Exception as e:
        logger.error(f"[get_skills_coverage] SQL error: {e}")
        return []

    return [
        {"skill": row.skill, "consultant_count": row.consultant_count}
        for row in rows
        if row.skill
    ]



@router.post("/reanalyze")
async def reanalyze_cvs(
    request: Request,
    tag: Optional[str] = None,
    user_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    token_payload: dict = Depends(verify_jwt)
):
    """(Admin Only) Replanie le traitement des CVs via le pipeline Pub/Sub unifié.

    Délègue intégralement au mécanisme nominal (drive_api → Pub/Sub → cv_api worker)
    pour un seul chemin de traitement, de retry et de DLQ.

    Étapes :
    1. Efface les compétences existantes pour chaque user_id concerné
    2. Remet les DriveSyncState correspondants en PENDING dans drive_api
    3. Déclenche immédiatement drive_api /sync (sans attendre le scheduler horaire)
    4. Retourne un JSON immédiat avec les compteurs

    La progression est observable via GET /reanalyze/status ou le scanner Drive.
    """
    if token_payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Privilèges administrateur requis.")

    auth_header = request.headers.get("Authorization")
    headers = {"Authorization": auth_header} if auth_header else {}
    inject(headers)

    # ── 1. Identifier les CVs concernés ──────────────────────────────────────
    stmt = select(CVProfile)
    if tag:
        stmt = stmt.filter(CVProfile.source_tag.ilike(f"%{tag}%"))
    if user_id:
        stmt = stmt.filter(CVProfile.user_id == user_id)

    cvs = (await db.execute(stmt)).scalars().all()

    # Forcer une re-découverte Drive pour ce tag (remet is_initial_sync_done à False)
    try:
        reset_url = f"{DRIVE_API_URL.rstrip('/')}/folders/reset-sync"
        if tag:
            reset_url += f"?tag={tag}"
        async with httpx.AsyncClient(timeout=5.0) as http_client:
            await http_client.post(reset_url, headers=headers)
    except Exception as e:
        logger.warning(f"[reanalyze] Failed to trigger drive_api reset-sync: {e}")

    if not cvs:
        return {
            "message": "Aucun CV trouvé en base locale. Une re-découverte Drive a été ordonnée — les nouveaux CVs seront ingérés lors du prochain /sync.",
            "count": 0,
            "pending_reset": 0,
            "skipped_manual": 0
        }

    # ── 2. Obtenir un token de service longue durée (conforme AGENTS.md §4) ──
    effective_headers = dict(headers)
    try:
        async with httpx.AsyncClient(timeout=10.0) as http_client:
            svc_res = await http_client.post(
                f"{USERS_API_URL.rstrip('/')}/internal/service-token",
                headers=headers,
                timeout=10.0
            )
            if svc_res.status_code == 200:
                svc_token = svc_res.json().get("access_token")
                effective_headers = {"Authorization": f"Bearer {svc_token}"}
                inject(effective_headers)
                logger.info("[reanalyze] Token de service longue durée obtenu.")
    except Exception as e_svc:
        logger.warning(f"[reanalyze] Service token indisponible: {e_svc} — token original conservé.")

    user_ids_to_clear = {cv.user_id for cv in cvs if cv.user_id}

    # ── 3. Effacer les compétences existantes (table rase avant réingestion) ──
    clear_errors = []
    async with httpx.AsyncClient(timeout=30.0) as http_client:
        for uid in user_ids_to_clear:
            try:
                clear_res = await http_client.delete(
                    f"{COMPETENCIES_API_URL.rstrip('/')}/user/{uid}/clear",
                    headers=effective_headers
                )
                if clear_res.status_code not in (200, 204):
                    clear_errors.append(f"user_id={uid}: HTTP {clear_res.status_code}")
                    logger.warning(f"[reanalyze] clear competencies user={uid}: HTTP {clear_res.status_code}")
            except Exception as e_clear:
                clear_errors.append(f"user_id={uid}: {e_clear}")
                logger.warning(f"[reanalyze] clear competencies user={uid}: {e_clear}")

    # ── 4. Remettre chaque DriveSyncState en PENDING ──────────────────────────
    pending_reset = 0
    skipped_manual = 0
    google_file_id_pattern = re.compile(r"/d/([a-zA-Z0-9_-]+)")

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        for cv in cvs:
            url = cv.source_url or ""
            match = google_file_id_pattern.search(url)
            if not match:
                skipped_manual += 1
                logger.info(f"[reanalyze] CV id={cv.id} sans google_file_id (import manuel) — ignoré.")
                continue

            g_file_id = match.group(1)
            try:
                patch_res = await http_client.patch(
                    f"{DRIVE_API_URL.rstrip('/')}/files/{g_file_id}",
                    json={"status": "PENDING", "error_message": None},
                    headers=effective_headers,
                    timeout=5.0
                )
                if patch_res.status_code in (200, 204, 404):
                    # 404 = fichier pas encore dans drive_api (sera créé au /sync)
                    pending_reset += 1
                else:
                    logger.warning(f"[reanalyze] PATCH /files/{g_file_id} HTTP {patch_res.status_code}")
            except Exception as e_patch:
                logger.warning(f"[reanalyze] PATCH /files/{g_file_id}: {e_patch}")

        # ── 5. Déclencher immédiatement drive_api /sync ───────────────────────
        # Évite d'attendre le tick du Cloud Scheduler (max 1h d'attente).
        # Le /sync lance ingest_batch() en BackgroundTask → réponse instantanée.
        try:
            sync_res = await http_client.post(
                f"{DRIVE_API_URL.rstrip('/')}/sync",
                headers=effective_headers,
                timeout=10.0
            )
            sync_triggered = sync_res.status_code in (200, 202)
            if not sync_triggered:
                logger.warning(f"[reanalyze] /sync HTTP {sync_res.status_code}")
        except Exception as e_sync:
            sync_triggered = False
            logger.warning(f"[reanalyze] /sync indisponible: {e_sync}")

    logger.info(
        f"[reanalyze] Terminé — pending_reset={pending_reset}, skipped_manual={skipped_manual}, "
        f"users_cleared={len(user_ids_to_clear)}, sync_triggered={sync_triggered}"
    )

    return {
        "message": (
            f"{pending_reset} CV(s) remis en file Pub/Sub. "
            f"Le traitement démarrera dans quelques instants via le worker cv_api."
        ),
        "count": len(cvs),
        "pending_reset": pending_reset,
        "skipped_manual": skipped_manual,
        "users_cleared": len(user_ids_to_clear),
        "sync_triggered": sync_triggered,
        "clear_errors": clear_errors if clear_errors else None
    }




