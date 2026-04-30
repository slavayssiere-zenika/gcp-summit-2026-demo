"""taxonomy_router.py — Recalcul interactif et batch de l'arbre taxonomique."""
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

router = APIRouter(prefix="", tags=["CV Taxonomy"], dependencies=[Depends(verify_jwt)])

@router.post("/recalculate_tree/step")
async def recalculate_competencies_tree_step(
    request: Request,
    req_body: RecalculateStepRequest,
    background_tasks: BackgroundTasks,
    token_payload: dict = Depends(verify_jwt)
):
    if token_payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Privilèges administrateur requis.")
    
    auth_header = request.headers.get("Authorization")
    user_caller = token_payload.get("sub", "unknown")
    
    if req_body.step == "map":
        await tree_task_manager.initialize_task()
    else:
        await tree_task_manager.update_progress(status="running", new_log=f"Lancement de l'étape: {req_body.step}")
        
    background_tasks.add_task(run_taxonomy_step, auth_header, user_caller, req_body.step, _svc_config.client, req_body.target_pillar)
    return {"message": f"Étape {req_body.step} lancée", "status": "running"}


@router.post("/recalculate_tree")
async def recalculate_competencies_tree(
    request: Request,
    background_tasks: BackgroundTasks,
    resume: bool = False,
    token_payload: dict = Depends(verify_jwt)
):
    if token_payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Opération refusée: privilèges administrateur requis.")
        
    if await tree_task_manager.is_task_running():
        return {"message": "Un calcul de l'arbre est déjà en cours", "status": "running"}
        
    auth_header = request.headers.get("Authorization")
    user_caller = token_payload.get("sub", "unknown")
    
    if not resume:
        await tree_task_manager.initialize_task()
        background_tasks.add_task(run_taxonomy_step, auth_header, user_caller, "map", _svc_config.client)
    else:
        background_tasks.add_task(run_taxonomy_step, auth_header, user_caller, "reduce", _svc_config.client)

    return {"message": "Calcul interactif de l'arbre lancé", "status": "running"}


@router.get("/recalculate_tree/status")
async def get_recalculate_tree_status():
    """Récupère le statut du recalcul de l'arbre.
    
    Synthètise 'batch_running' quand mode=batch && status=running pour que
    le frontend déclenche checkBatchProgress() et fasse avancer le pipeline.
    """
    status = await tree_task_manager.get_latest_status()
    if not status:
        return {"status": "idle", "message": "Aucune tâche lancée récemment."}
    # Synthèse du status composé pour le frontend
    if status.get("mode") == "batch" and status.get("status") == "running":
        status = dict(status)
        status["status"] = "batch_running"
    return status

# ─────────────────────────────────────────────────────────────────────────────
# Sprint 0 — Re-indexation des embeddings (embeddings-only, sans re-extraction LLM)
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/recalculate_tree/batch/start", summary="Lance le processus batch asynchrone (Map)")
async def recalculate_tree_batch_start(request: Request, user: dict = Depends(verify_jwt)):
    auth_header = request.headers.get("Authorization")
    latest_status = await tree_task_manager.get_latest_status()
    if latest_status and latest_status.get("status") == "running" and latest_status.get("batch_job_id"):
        # Vérifier l'état réel sur Vertex AI pour éviter un Redis bloqué à 'running'
        # si le job est déjà terminé (SUCCEEDED/FAILED) côté GCP.
        job_id_check = latest_status.get("batch_job_id")
        try:
            live_job = await asyncio.to_thread(_svc_config.vertex_batch_client.batches.get, name=job_id_check)
            live_state = live_job.state.name if hasattr(live_job.state, "name") else str(live_job.state)
            if live_state in ("JOB_STATE_RUNNING", "JOB_STATE_PENDING", "JOB_STATE_QUEUED"):
                return {"success": False, "message": f"Batch déjà en cours ({live_state}). Attendez la fin ou annulez."}
            # État terminal côté GCP mais Redis pas encore mis à jour → on débloque
            logger.info(f"[batch-start] Job {job_id_check} déjà terminé ({live_state}) mais Redis bloqué — déblocage automatique.")
        except Exception as e_check:
            # Si on ne peut pas joindre Vertex AI, on reste conservateur
            logger.warning(f"[batch-start] Impossible de vérifier l'état Vertex AI : {e_check} — blocage conservateur.")
            return {"success": False, "message": "Batch en cours (impossible de vérifier Vertex AI). Utilisez 'Réinitialiser' si bloqué."}
        
    await tree_task_manager.initialize_task()
    await tree_task_manager.update_progress(batch_step="map", new_log="Démarrage du processus Batch (Map)...")

    # AGENTS.md §4 : obtenir le service-token MAINTENANT (JWT valide) et le stocker en Redis.
    # Tous les batch/check suivants (dedup, reduce, sweep) arriveront 1h+ plus tard JWT expiré.
    auth_token = auth_header.replace("Bearer ", "") if auth_header and "Bearer " in auth_header else auth_header
    _start_service_token: str = auth_token
    try:
        async with httpx.AsyncClient(timeout=10.0) as _svc_start:
            _res_start = await _svc_start.post(
                f"{USERS_API_URL.rstrip('/')}/internal/service-token",
                headers={"Authorization": auth_header},
                timeout=10.0,
            )
            if _res_start.status_code == 200:
                _fresh = _res_start.json().get("access_token")
                if _fresh:
                    _start_service_token = _fresh
                    logger.info("[batch-start] Service token 90 min stocké en Redis.")
            else:
                logger.warning(f"[batch-start] /internal/service-token HTTP {_res_start.status_code} — fallback JWT court.")
    except Exception as _e_start:
        logger.warning(f"[batch-start] Impossible d'obtenir le service-token: {_e_start} — fallback JWT court.")
    await tree_task_manager.update_progress(service_token=_start_service_token)

    existing_names = await _get_existing_competencies(auth_header)
    logger.info(f"[batch-start] {len(existing_names)} compétences récupérées pour le Map.")
    if not existing_names:
        error_msg = "Aucune compétence trouvée dans competencies_api. Vérifiez que l'API est démarrée et que des compétences existent en base avant de lancer le batch."
        await tree_task_manager.update_progress(status="error", error=error_msg)
        return {"success": False, "error": error_msg}
        
    instruction_map = await _fetch_prompt("cv_api.generate_taxonomy_tree_map", "cv_api.generate_taxonomy_tree_map.txt", auth_header)
    
    chunk_size = 500
    existing_names_chunks = [existing_names[i:i + chunk_size] for i in range(0, len(existing_names), chunk_size)]
    
    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".jsonl") as f:
        for i, chunk in enumerate(existing_names_chunks):
            skills_str = ", ".join(chunk)
            map_instruction = instruction_map.replace("{{EXISTING_COMPETENCIES}}", skills_str)
            req = {
                "id": f"chunk-{i}",
                "request": {
                    "contents": [{"role": "user", "parts": [{"text": map_instruction}]}],
                    "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"}
                }
            }
            f.write(json.dumps(req) + "\n")
        temp_path = f.name
        
    try:
        if not _svc_config.vertex_batch_client:
            raise ValueError("Vertex AI _svc_config.client non initialisé (GCP_PROJECT_ID ou VERTEX_LOCATION manquant).")
        if not BATCH_GCS_BUCKET:
            raise ValueError("BATCH_GCS_BUCKET non configuré.")

        # Upload du JSONL vers GCS
        gcs_client = gcs_storage.Client()
        timestamp = int(datetime.utcnow().timestamp())
        blob_name = f"taxonomy/input/map-{timestamp}.jsonl"
        bucket = gcs_client.bucket(BATCH_GCS_BUCKET)
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(temp_path, content_type="application/jsonl")
        src_uri = f"gs://{BATCH_GCS_BUCKET}/{blob_name}"
        dest_uri = f"gs://{BATCH_GCS_BUCKET}/taxonomy/output/map-{timestamp}/"

        batch_job = await asyncio.to_thread(
            _svc_config.vertex_batch_client.batches.create,
            model=os.environ["GEMINI_PRO_MODEL"],
            src=src_uri,
            config={"display_name": "taxonomy-map-batch", "dest": dest_uri}
        )
        await tree_task_manager.update_progress(batch_job_id=batch_job.name, batch_step="map", new_log=f"Job Batch Map créé (ID: {batch_job.name}). En attente de Vertex AI...")
        os.unlink(temp_path)
        return {"success": True, "batch_job_id": batch_job.name}
    except Exception as e:
        logger.error(f"Erreur création batch Map: {e}")
        await tree_task_manager.update_progress(status="error", error=str(e))
        os.unlink(temp_path)
        return {"success": False, "error": str(e)}


@router.post("/recalculate_tree/batch/check", summary="Vérifie l'état du batch et avance la machine à états")
async def recalculate_tree_batch_check(request: Request, user: dict = Depends(verify_jwt)):
    auth_header = request.headers.get("Authorization")
    auth_token = auth_header.replace("Bearer ", "") if auth_header and "Bearer " in auth_header else auth_header
    user_caller = user.get("sub", "scheduler")
    
    latest_status = await tree_task_manager.get_latest_status()
    if not latest_status or latest_status.get("status") != "running" or not latest_status.get("batch_job_id"):
        return {"success": True, "message": "Aucun batch en cours"}
        
    batch_job_id = latest_status.get("batch_job_id")
    batch_step = latest_status.get("batch_step")

    # Lire le service-token persisté à batch/start (JWT encore valide à l'époque).
    # Ne PAS tenter de ré-acquérir via /internal/service-token : le JWT est expiré depuis longtemps.
    _persisted_svc_token = latest_status.get("service_token") or auth_token
    if not latest_status.get("service_token"):
        logger.warning(
            "[batch-check] service_token absent du state Redis (ancien batch pré-migration) —"
            " tentative de ré-acquisition avec le JWT courant."
        )
        try:
            async with httpx.AsyncClient(timeout=10.0) as _svc_compat:
                _res_compat = await _svc_compat.post(
                    f"{USERS_API_URL.rstrip('/')}/internal/service-token",
                    headers={"Authorization": auth_header},
                    timeout=10.0,
                )
                if _res_compat.status_code == 200:
                    _fresh = _res_compat.json().get("access_token")
                    if _fresh:
                        _persisted_svc_token = _fresh
                        await tree_task_manager.update_progress(service_token=_fresh)
        except Exception as _e_compat:
            logger.warning(f"[batch-check] Ré-acquisition échouée: {_e_compat}")

    try:
        batch_job = await asyncio.to_thread(_svc_config.vertex_batch_client.batches.get, name=batch_job_id)
        if batch_job.state.name != "JOB_STATE_SUCCEEDED":
            if batch_job.state.name == "JOB_STATE_FAILED":
                try:
                    await asyncio.to_thread(_svc_config.vertex_batch_client.batches.delete, name=batch_job_id)
                except Exception as e:
                    logger.error(f"Impossible de supprimer le batch échoué: {e}")
                
                error_msg = f"Le job Batch a échoué côté GCP (Status: {batch_job.state.name})"
                await tree_task_manager.update_progress(status="error", error=error_msg)
                return {"success": False, "error": error_msg}

            # ── Auto-healing : PENDING timeout ────────────────────────────────
            # Si le batch est bloqué en PENDING trop longtemps (file GCP saturée),
            # on le cancelle et on repart de zéro automatiquement.
            if batch_job.state.name == "JOB_STATE_PENDING":
                timeout_hours = float(os.environ.get("BATCH_PENDING_TIMEOUT_HOURS", "3"))
                create_time = getattr(batch_job, "create_time", None)
                if create_time:
                    elapsed_hours = (datetime.now(timezone.utc) - create_time).total_seconds() / 3600
                    if elapsed_hours >= timeout_hours:
                        logger.warning(
                            f"[batch-check] Batch {batch_job_id} bloqué en PENDING depuis "
                            f"{elapsed_hours:.1f}h (seuil={timeout_hours}h) — cancel + restart automatique."
                        )
                        try:
                            await asyncio.to_thread(_svc_config.vertex_batch_client.batches.cancel, name=batch_job_id)
                        except Exception as e_cancel:
                            logger.warning(f"[batch-check] Impossible d'annuler le batch: {e_cancel}")
                        # Reset complet de l'état Redis pour forcer un nouveau /batch/start
                        await tree_task_manager.update_progress(
                            status="error",
                            error=(
                                f"Batch {batch_job_id} annulé automatiquement après {elapsed_hours:.1f}h en PENDING "
                                f"(file GCP saturée). Un nouveau batch sera déclenché au prochain trigger du scheduler."
                            )
                        )
                        return {
                            "success": True,
                            "action": "auto_restart",
                            "message": f"Batch annulé après {elapsed_hours:.1f}h — prochain trigger relancera le pipeline.",
                        }
            # ── Fin auto-healing ───────────────────────────────────────────────

            # Monitoring : completion_stats (Vertex AI) ou fallback vide
            progress_data = {}
            cs = getattr(batch_job, "completion_stats", None)
            if cs:
                successful = int(getattr(cs, "success_count", None) or getattr(cs, "successful_count", 0) or 0)
                failed = int(getattr(cs, "failed_count", None) or getattr(cs, "error_count", 0) or 0)
                incomplete = int(getattr(cs, "incomplete_count", 0) or 0)
                total = int(getattr(cs, "total_count", None) or 0) or (successful + failed + incomplete)
                progress_data = {
                    "completed": successful,
                    "total": total,
                    "failed": failed,
                    "percent": int((successful / total) * 100) if total > 0 else 0
                }
                
            # Temps écoulé depuis création
            elapsed_info = ""
            if getattr(batch_job, "create_time", None):
                from datetime import timezone
                elapsed_s = (datetime.now(timezone.utc) - batch_job.create_time).total_seconds()
                elapsed_info = f"{int(elapsed_s // 3600)}h{int((elapsed_s % 3600) // 60)}m"

            return {
                "success": True,
                "state": batch_job.state.name,
                "step": batch_step,
                "progress": progress_data,
                "elapsed": elapsed_info
            }

            
        # Téléchargement du résultat depuis GCS (Vertex AI stocke dans dest)
        # batch_job.dest est un objet BatchJobDestination, pas une string — utiliser .gcs_uri
        dest_obj = batch_job.dest
        if not dest_obj or not dest_obj.gcs_uri:
            raise ValueError("batch_job.dest.gcs_uri est vide — le résultat n'est pas encore disponible.")

        dest_uri = dest_obj.gcs_uri  # ex: gs://bucket/taxonomy/output/map-xxx/
        # Normalise le préfixe GCS
        gcs_dest = dest_uri.replace(f"gs://{BATCH_GCS_BUCKET}/", "")
        gcs_client = gcs_storage.Client()
        output_bucket = gcs_client.bucket(BATCH_GCS_BUCKET)
        blobs = list(output_bucket.list_blobs(prefix=gcs_dest))
        output_blob = next((b for b in blobs if b.name.endswith(".jsonl")), None)
        if not output_blob:
            raise ValueError(f"Aucun fichier .jsonl trouvé dans {dest_uri}")
        file_content = output_blob.download_as_text()

        total_prompt_tokens = 0
        total_candidates_tokens = 0
        parsed_results = []
        
        for line in file_content.splitlines():
            resp = json.loads(line)
            if "response" in resp and "usageMetadata" in resp["response"]:
                total_prompt_tokens += resp["response"]["usageMetadata"].get("promptTokenCount", 0)
                total_candidates_tokens += resp["response"]["usageMetadata"].get("candidatesTokenCount", 0)
            
            # Text content
            if "response" in resp and "candidates" in resp["response"] and len(resp["response"]["candidates"]) > 0:
                parts = resp["response"]["candidates"][0].get("content", {}).get("parts", [])
                if parts:
                    parsed_results.append(parts[0].get("text", ""))
                    
        usage = {"prompt_token_count": total_prompt_tokens, "candidates_token_count": total_candidates_tokens}
        
        if batch_step == "map":
            await log_finops(user_caller, "recalculate_tree_batch_map", os.environ["GEMINI_MODEL"], usage, auth_token=auth_token)
            
            map_result = {}
            for i, text in enumerate(parsed_results):
                try:
                    cleaned = text.strip()
                    if cleaned.startswith("```json"): cleaned = cleaned[7:]
                    if cleaned.startswith("```"): cleaned = cleaned[3:]
                    if cleaned.endswith("```"): cleaned = cleaned[:-3]
                    cleaned = cleaned.strip()
                    
                    raw_map, _ = json.JSONDecoder().raw_decode(cleaned)
                    if isinstance(raw_map, dict) and "items" in raw_map:
                        raw_map = raw_map["items"]
                    parsed_chunk = {}
                    if isinstance(raw_map, list):
                        for item in raw_map:
                            if isinstance(item, dict):
                                parsed_chunk.update(item)
                    elif isinstance(raw_map, dict):
                        parsed_chunk.update(raw_map)
                        
                    for pillar, skills in parsed_chunk.items():
                        if not isinstance(skills, list): continue
                        if pillar not in map_result: map_result[pillar] = []
                        map_result[pillar].extend(skills)
                except Exception as e:
                    logger.error(f"Erreur de parsing sur le chunk {i} du Map (ignoré): {e}")
                    continue
                    
            if not map_result:
                return {"success": False, "error": "Aucun chunk JSONL n'a pu être parsé correctement."}
                
            await tree_task_manager.update_progress(map_result=map_result, batch_step="deduplicating", new_log="Map Batch terminé. Exécution de Deduplicate...")
            
            # Service token lu depuis Redis (stocké à batch/start quand le JWT était encore valide).
            dedup_service_token: str = _persisted_svc_token

            # Lancement en tâche de fond pour éviter le timeout HTTP
            async def run_dedup(svc_token: str = dedup_service_token):
                _svc_auth_header = f"Bearer {svc_token}"
                try:
                    instruction_dedup = await _fetch_prompt("cv_api.generate_taxonomy_tree_deduplicate", "cv_api.generate_taxonomy_tree_deduplicate.txt", _svc_auth_header)
                    # map_json_str = map_result complet, injecté dans Dedup ET Reduce
                    map_json_str = json.dumps(map_result, ensure_ascii=False)
                    # Dedup utilise GEMINI_PRO_MODEL (contexte 1M tokens) pour traiter
                    # le map_result complet sans troncature ni perte de qualité.
                    dedup_instruction = instruction_dedup.replace("{{MAP_RESULT}}", map_json_str)

                    response_dedup = await generate_content_with_retry(
                        _svc_config.client,
                        model=os.environ["GEMINI_PRO_MODEL"],
                        contents=[dedup_instruction],
                        config=types.GenerateContentConfig(
                            temperature=0.1,
                            response_mime_type="application/json",
                            max_output_tokens=65536,
                        )
                    )
                    await log_finops(user_caller, "recalculate_tree_batch_dedup", os.environ["GEMINI_PRO_MODEL"], response_dedup.usage_metadata, auth_token=svc_token)

                    # Vérifier que la réponse n'est pas tronquée
                    finish_reason = None
                    if response_dedup.candidates:
                        finish_reason = str(getattr(response_dedup.candidates[0], "finish_reason", "")).upper()
                    if finish_reason and "MAX_TOKEN" in finish_reason:
                        raise ValueError(
                            f"La réponse Deduplicate a été tronquée par le LLM (finish_reason={finish_reason}). "
                            "Augmentez max_output_tokens ou réduisez le prompt."
                        )

                    cleaned = response_dedup.text.strip()
                    if cleaned.startswith("```json"): cleaned = cleaned[7:]
                    if cleaned.startswith("```"): cleaned = cleaned[3:]
                    if cleaned.endswith("```"): cleaned = cleaned[:-3]
                    cleaned = cleaned.strip()
                    try:
                        raw_dedup, _ = json.JSONDecoder().raw_decode(cleaned)
                    except json.JSONDecodeError as json_err:
                        raise ValueError(
                            f"Erreur Deduplicate: {json_err} — "
                            f"Réponse LLM (premiers 500 chars): {cleaned[:500]!r}"
                        )

                    
                    pillars_list = []
                    if isinstance(raw_dedup, dict) and "pillars" in raw_dedup:
                        pillars_list = raw_dedup["pillars"]
                    elif isinstance(raw_dedup, list):
                        pillars_list = raw_dedup
                    elif isinstance(raw_dedup, dict) and len(raw_dedup) > 0:
                        pillars_list = [{"name": k} for k in raw_dedup.keys()]
                        
                    completed_pillars = []
                    for p in pillars_list:
                        if isinstance(p, dict) and "name" in p:
                            completed_pillars.append(p)
                        elif isinstance(p, str):
                            completed_pillars.append({"name": p, "description": ""})
                            
                    if not completed_pillars:
                        raise ValueError(f"Le LLM a retourné un résultat vide ou non reconnu pour la déduplication : {str(raw_dedup)[:200]}")
                            
                    await tree_task_manager.update_progress(completed_pillars=completed_pillars, new_log="Deduplicate terminé. Lancement du Batch Reduce...")
                    
                    # Start Reduce Batch
                    instruction_reduce = await _fetch_prompt("cv_api.generate_taxonomy_tree_reduce", "cv_api.generate_taxonomy_tree_reduce.txt", _svc_auth_header)
                    
                    import tempfile
                    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".jsonl") as f:
                        for i, p in enumerate(completed_pillars):
                            p_name = p.get("name", "")
                            reduce_prompt = instruction_reduce.replace("{{CURRENT_PILLAR}}", p_name).replace("{{MAP_RESULT}}", map_json_str)
                            req = {
                                "id": f"pillar-{i}",
                                "request": {
                                    "contents": [{"role": "user", "parts": [{"text": reduce_prompt}]}],
                                    "generationConfig": {
                                        "temperature": 0.1,
                                        "responseMimeType": "application/json",
                                        "maxOutputTokens": 65536
                                    }
                                }
                            }
                            f.write(json.dumps(req) + "\n")
                        temp_path = f.name
                        
                    # Init GCS _svc_config.client avant usage
                    gcs_client_reduce = gcs_storage.Client()
                    ts_reduce = int(datetime.utcnow().timestamp())
                    blob_reduce_name = f"taxonomy/input/reduce-{ts_reduce}.jsonl"
                    reduce_bucket = gcs_client_reduce.bucket(BATCH_GCS_BUCKET)
                    blob_reduce = reduce_bucket.blob(blob_reduce_name)
                    blob_reduce.upload_from_filename(temp_path, content_type="application/jsonl")
                    src_reduce_uri = f"gs://{BATCH_GCS_BUCKET}/{blob_reduce_name}"
                    dest_reduce_uri = f"gs://{BATCH_GCS_BUCKET}/taxonomy/output/reduce-{ts_reduce}/"

                    reduce_batch_job = await asyncio.to_thread(
                        _svc_config.vertex_batch_client.batches.create,
                        model=os.environ["GEMINI_PRO_MODEL"],
                        src=src_reduce_uri,
                        config={"display_name": "taxonomy-reduce-batch", "dest": dest_reduce_uri}
                    )
                    await tree_task_manager.update_progress(batch_job_id=reduce_batch_job.name, batch_step="reduce", new_log=f"Job Batch Reduce créé (ID: {reduce_batch_job.name}). En attente Vertex AI...")
                    os.unlink(temp_path)
                except Exception as e:
                    logger.error(f"Erreur background dedup: {e}")
                    await tree_task_manager.update_progress(status="error", error=f"Erreur Deduplicate: {str(e)}")
            
            asyncio.create_task(run_dedup())
            return {"success": True, "state": "PROCESSING_DEDUP"}
            
        elif batch_step == "reduce":
            await log_finops(user_caller, "recalculate_tree_batch_reduce", os.environ["GEMINI_PRO_MODEL"], usage, auth_token=auth_token)
            
            res_tree = {}
            for i, text in enumerate(parsed_results):
                try:
                    cleaned = text.strip()
                    if cleaned.startswith("```json"): cleaned = cleaned[7:]
                    if cleaned.startswith("```"): cleaned = cleaned[3:]
                    if cleaned.endswith("```"): cleaned = cleaned[:-3]
                    cleaned = cleaned.strip()
                    
                    raw_res, _ = json.JSONDecoder().raw_decode(cleaned)
                    if isinstance(raw_res, dict):
                        res_tree.update(raw_res)
                except Exception as e:
                    logger.error(f"Erreur de parsing de chunk JSONL Reduce {i} (ignoré): {e}")
                    continue
                    
            if not res_tree:
                return {"success": False, "error": "Aucun chunk JSONL du Reduce n'a pu être parsé."}
                
            await tree_task_manager.update_progress(res_tree=res_tree, batch_step="sweeping", new_log="Reduce Batch terminé. Exécution de Sweep...")

            # --- Garde-fou : détecter un res_tree corrompu (placeholder non substitué) ---
            if "{{CURRENT_PILLAR}}" in res_tree or "{{PILLAR_NAME}}" in res_tree:
                error_msg = (
                    "res_tree corrompu : la clef '{{CURRENT_PILLAR}}' est présente, "
                    "le prompt Reduce n'a pas substitué le placeholder. "
                    "Relancez un nouveau batch depuis zéro (Recover ne suffit pas)."
                )
                await tree_task_manager.update_progress(status="error", error=error_msg)
                return {"success": False, "error": error_msg}

            # Service token lu depuis Redis (stocké à batch/start quand le JWT était encore valide).
            sweep_service_token: str = _persisted_svc_token

            # Lancement en tâche de fond pour Sweep
            async def run_sweep(service_token: str = sweep_service_token):
                try:
                    from google.genai import types
                    instruction_sweep = await _fetch_prompt("cv_api.generate_taxonomy_tree_sweep", "cv_api.generate_taxonomy_tree_sweep.txt", f"Bearer {service_token}")
                    existing_names = await _get_existing_competencies(f"Bearer {service_token}")
                    def get_all_used_names(node, used=None):
                        if used is None: used = set()
                        if isinstance(node, dict):
                            if "name" in node:
                                used.add(node["name"])
                            if "merge_from" in node and isinstance(node["merge_from"], list):
                                for m in node["merge_from"]: used.add(m)
                            for v in node.values():
                                if isinstance(v, (dict, list)):
                                    get_all_used_names(v, used)
                        elif isinstance(node, list):
                            for item in node:
                                get_all_used_names(item, used)
                        return used
        
                    used_names = get_all_used_names(res_tree)
                    missing = list(set(existing_names) - used_names)
                            
                    sweep_instruction = instruction_sweep.replace("{{MISSING_COMPETENCIES}}", ", ".join(missing) if missing else "Aucune").replace("{{CURRENT_TREE}}", json.dumps(res_tree, ensure_ascii=False))
                    response_sweep = await generate_content_with_retry(
                        _svc_config.client,
                        model=os.environ["GEMINI_PRO_MODEL"],
                        contents=[sweep_instruction],
                        config=types.GenerateContentConfig(
                            temperature=0.1,
                            response_mime_type="application/json",
                            max_output_tokens=16384,  # liste d'assignments, peut être longue
                        )
                    )
                    await log_finops(user_caller, "recalculate_tree_batch_sweep", os.environ["GEMINI_PRO_MODEL"], response_sweep.usage_metadata, auth_token=service_token)
                    
                    cleaned = _clean_llm_json(response_sweep.text or "")

                    # Guard : réponse vide ou non-JSON (LLM dit "Aucune" ou rend du texte libre)
                    sweep_result = []
                    if cleaned and cleaned[0] in ("{", "["):
                        try:
                            sweep_raw, _ = json.JSONDecoder().raw_decode(cleaned)
                            if isinstance(sweep_raw, dict) and "assignments" in sweep_raw:
                                sweep_result = sweep_raw["assignments"]
                            elif isinstance(sweep_raw, list):
                                sweep_result = sweep_raw
                        except json.JSONDecodeError as e:
                            logger.warning(f"[sweep] JSON invalide même après nettoyage : {e} — sweep ignoré.")
                    else:
                        logger.info(
                            f"[sweep] Réponse LLM vide ou non-JSON ('{cleaned[:80]}') "
                            "— aucun assignment Sweep à appliquer."
                        )

                    await tree_task_manager.update_progress(sweep_result=sweep_result, missing_competencies=missing, new_log="Sweep terminé. Application en base de données...")

                    # Utilisation du service_token obtenu AVANT le lancement de la tâche
                    competencies_api_url = os.getenv("COMPETENCIES_API_URL", "http://competencies_api:8000")
                    apply_headers = {"Authorization": f"Bearer {service_token}"}
                    from opentelemetry.propagate import inject
                    inject(apply_headers)
                    async with httpx.AsyncClient() as http_client:
                        res = await http_client.post(
                            f"{competencies_api_url}/bulk_tree",
                            json={"tree": res_tree, "sweep_assignments": sweep_result},
                            headers=apply_headers,
                            timeout=180.0
                        )
                        if res.status_code == 200:
                            await tree_task_manager.update_progress(status="completed", new_log="Taxonomie appliquée avec succès !")
                        else:
                            await tree_task_manager.update_progress(status="error", error=f"Erreur d'application: {res.text}")
                except Exception as e:
                    logger.error(f"Erreur background sweep: {e}")
                    await tree_task_manager.update_progress(status="error", error=f"Erreur Sweep: {str(e)}")
                    
            asyncio.create_task(run_sweep())
            return {"success": True, "state": "PROCESSING_SWEEP"}
            
    except Exception as e:
        logger.error(f"Erreur check batch: {e}")
        return {"success": False, "error": str(e)}



@router.get("/recalculate_tree/batch/list", summary="Liste l'historique des jobs batch de taxonomie")
async def recalculate_tree_batch_list(request: Request, user: dict = Depends(verify_jwt)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Privilèges administrateur requis.")
    try:
        batches = []
        all_batches = await asyncio.to_thread(lambda: list(_svc_config.vertex_batch_client.batches.list()))
        for b in all_batches:
            display_name = "batch_job"
            if hasattr(b, "display_name") and b.display_name:
                display_name = b.display_name
            elif hasattr(b, "config") and hasattr(b.config, "display_name") and b.config.display_name:
                display_name = b.config.display_name
            
            if hasattr(b, "name") and hasattr(b, "state"):
                # Vertex AI expose completion_stats (pas request_counts)
                cs = getattr(b, "completion_stats", None)
                completion_stats = None
                if cs:
                    successful = int(getattr(cs, "success_count", None) or getattr(cs, "successful_count", 0) or 0)
                    failed = int(getattr(cs, "failed_count", None) or getattr(cs, "error_count", 0) or 0)
                    incomplete = int(getattr(cs, "incomplete_count", 0) or 0)
                    total = int(getattr(cs, "total_count", None) or 0) or (successful + failed + incomplete)
                    if total > 0:
                        completion_stats = {
                            "successful": successful,
                            "failed": failed,
                            "incomplete": incomplete,
                            "total": total,
                            "percent": int((successful / total) * 100)
                        }

                batches.append({
                    "name": b.name,
                    "display_name": display_name,
                    "state": b.state.name if hasattr(b.state, "name") else str(b.state),
                    "create_time": str(b.create_time) if hasattr(b, "create_time") else None,
                    "start_time": str(b.start_time) if getattr(b, "start_time", None) else None,
                    "end_time": str(b.end_time) if getattr(b, "end_time", None) else None,
                    "update_time": str(b.update_time) if hasattr(b, "update_time") else None,
                    "model": getattr(b, "model", None),
                    "completion_stats": completion_stats
                })
        batches.sort(key=lambda x: x["create_time"] or "", reverse=True)
        return {"success": True, "batches": batches}
    except Exception as e:
        logger.error(f"Erreur listage batch GCP: {e}")
        return {"success": False, "error": str(e)}


@router.delete("/recalculate_tree/batch/{job_id}", summary="Supprime un job batch GCP de l'historique")
async def recalculate_tree_batch_delete(job_id: str, request: Request, user: dict = Depends(verify_jwt)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Privilèges administrateur requis.")
    try:
        # Vertex AI utilise un chemin complet : projects/.../batchPredictionJobs/ID
        # Si le frontend envoie juste l'ID numérique, on reconstruit le chemin complet.
        if "/" in job_id:
            full_job_id = job_id  # déjà un chemin complet
        else:
            full_job_id = f"projects/{GCP_PROJECT_ID}/locations/{VERTEX_LOCATION}/batchPredictionJobs/{job_id}"
        await asyncio.to_thread(_svc_config.vertex_batch_client.batches.delete, name=full_job_id)
        return {"success": True, "message": f"Job {job_id} supprimé avec succès."}
    except Exception as e:
        logger.error(f"Erreur suppression batch GCP: {e}")
        return {"success": False, "error": str(e)}


@router.post("/recalculate_tree/cancel", summary="Annule le traitement interactif en cours")
async def recalculate_tree_cancel(request: Request, user: dict = Depends(verify_jwt)):
    await tree_task_manager.update_progress(status="cancelled", error="Traitement interactif annulé par l'utilisateur.")
    return {"success": True, "message": "Traitement annulé"}


@router.post("/recalculate_tree/batch/cancel", summary="Annule le batch en cours")
async def recalculate_tree_batch_cancel(request: Request, user: dict = Depends(verify_jwt)):
    latest_status = await tree_task_manager.get_latest_status()
    if latest_status and latest_status.get("batch_job_id"):
        try:
            await asyncio.to_thread(_svc_config.vertex_batch_client.batches.cancel, name=latest_status.get("batch_job_id"))
        except Exception as e:
            logger.warning(f"Impossible d'annuler le batch Vertex AI (déjà terminé ou inexistant) : {e}")
            
    await tree_task_manager.update_progress(status="error", error="Annulé par l'utilisateur")
    return {"success": True, "message": "Batch annulé"}


@router.post("/recalculate_tree/batch/recover", summary="Tente de récupérer un batch bloqué en erreur")
async def recalculate_tree_batch_recover(request: Request, user: dict = Depends(verify_jwt)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Privilèges administrateur requis.")
    latest_status = await tree_task_manager.get_latest_status()
    if latest_status and latest_status.get("batch_job_id"):
        # On le remet en running pour que le frontend reprenne le polling
        # On efface l'erreur et on repart sur l'étape map si c'était planté au parsing
        # ou deduplicating si on a perdu l'étape. Pour être safe, on remet "map" 
        # car deduplicate est idempotent.
        step = latest_status.get("batch_step")
        if step == "deduplicating": step = "map"
        elif step == "sweeping": step = "reduce"
        
        await tree_task_manager.update_progress(status="running", batch_step=step, error="")
        return {"success": True, "message": "État du batch forcé à 'running'. L'interface va reprendre le relais."}
    return {"success": False, "error": "Aucun job batch récent en mémoire."}




@router.post("/recalculate_tree/batch/reset", summary="Réinitialise forcé l'état Redis du batch (déblocage d'urgence)")
async def recalculate_tree_batch_reset(request: Request, user: dict = Depends(verify_jwt)):
    """Efface l'état Redis du pipeline Batch pour permettre un nouveau démarrage.
    A utiliser quand l'interface est bloquée et que Cancel/Recover ne suffisent pas.
    Le job GCP en cours n'est PAS annulé — utilisez Cancel d'abord si nécessaire.
    """
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Privileges administrateur requis.")
    await tree_task_manager.initialize_task()
    await tree_task_manager.update_progress(status="idle", error="Reinitialise manuellement par l'admin.")
    return {"success": True, "message": "Etat du pipeline reinitialise. Vous pouvez lancer un nouveau batch."}


# ─────────────────────────────────────────────────────────────────────────────
# BULK RE-ANALYSE — Vertex AI Batch (Option B — Full Quality)
# Pipeline : Build JSONL → GCS Upload → Vertex Batch → Auto-Apply complet
# Chaque CV : UPDATE cv_profiles + purge évals + purge comps + bulk assign
#             + purge missions + ré-indexation + scoring IA + FinOps
# ─────────────────────────────────────────────────────────────────────────────


