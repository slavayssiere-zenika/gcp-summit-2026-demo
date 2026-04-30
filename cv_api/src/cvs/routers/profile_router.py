"""profile_router.py — Import CV, profils, tags, merge, pubsub."""
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

import database
import time
import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests
from jose import jwt as jose_jwt
from jose.exceptions import JWTError
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

router = APIRouter(prefix="", tags=["CV Profiles"], dependencies=[Depends(verify_jwt)])
public_router = APIRouter(prefix="", tags=["CV_Public"])

@router.post("/cache/invalidate-taxonomy")
async def force_invalidate_taxonomy_cache(_: dict = Depends(verify_jwt)):
    """Invalide spécifiquement le contexte sémantique de l'arbre des compétences (Taxonomy Event)."""
    _CV_CACHE["tree_context"] = {"value": None, "expires": datetime.min}
    _CV_CACHE["tree_items"] = {"value": None, "expires": datetime.min}
    logger.info("Cache de taxonomie purgé avec succès (Event-driven).")
    return {"message": "Cache de taxonomie invalidé"}


@router.post("/import", response_model=CVResponse)
async def import_and_analyze_cv(req: CVImportRequest, request: Request, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db), token_payload: dict = Depends(verify_jwt)):
    # M1 : Seuls rh, admin et service_account peuvent importer et analyser un CV
    # (protection FinOps : chaque import déclenche un appel Gemini + embedding Vertex AI)
    user_role = token_payload.get("role", "user")
    if user_role not in ("admin", "rh", "service_account"):
        raise HTTPException(
            status_code=403,
            detail="Accès refusé : l'import de CV est réservé aux rôles rh, admin et service_account."
        )
    # 1. Capture Authorization Context (Crucial per RULES[AGENTS.md])
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing Authorization via CV upload")
    
    headers = {"Authorization": auth_header}
    inject(headers)  # Mandatory Trace Span Propagation (Agent.md Rule 4)

    return await process_cv_core(
        url=req.url,
        google_access_token=req.google_access_token,
        source_tag=req.source_tag,
        folder_name=req.folder_name,
        headers=headers,
        token_payload=token_payload,
        db=db,
        auth_token=auth_header.replace("Bearer ", "") if "Bearer " in auth_header else auth_header,
        background_tasks=background_tasks, genai_client=_svc_config.client
    )



@public_router.post("/pubsub/import-cv")
async def handle_pubsub_cv_import(request: Request, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """
    Worker Pub/Sub push subscriber pour l'ingestion des CVs.

    Workflow :
    1. Validation OIDC du token Google (RS256) — vérifie que l'émetteur est bien le SA pubsub_invoker.
    2. Décodage base64 du payload Pub/Sub.
    3. ACK IMMÉDIAT (202) → Pub/Sub augmente sa concurrence (slow-start algorithm).
    4. Traitement ASYNCHRONE du pipeline LLM en BackgroundTask.
    5. Notification PATCH drive_api : IMPORTED_CV (succès) ou ERROR (échec).

    ARCHITECTURE : Le retour 202 immédiat est essentiel pour le parallélisme.
    Pub/Sub mesure le temps de réponse de l'endpoint pour calibrer sa concurrence.
    Une réponse en 2 min forçait une concurrence de 1-2 messages. Avec < 1s → 10+ parallèles.

    Sécurité : si le token OIDC est absent ou invalide → 401 (Pub/Sub va retenter).
    Idempotence : si le CV existe déjà (même email), mise à jour au lieu de création.
    """

    # ── 1. Validation OIDC ───────────────────────────────────────────────────
    invoker_sa_email = os.getenv("PUBSUB_INVOKER_SA_EMAIL", "")
    auth_header_val = request.headers.get("Authorization", "")

    if not auth_header_val.startswith("Bearer "):
        logger.warning("[PubSub] Requête sans token OIDC — rejetée.")
        raise HTTPException(status_code=401, detail="Missing OIDC token")

    oidc_token = auth_header_val.replace("Bearer ", "")

    # En dev local (pas de SA configuré), on tolère un bypass contrôlé
    if invoker_sa_email and invoker_sa_email != "sa-pubsub-invoker-dev@your-project.iam.gserviceaccount.com":
        try:
            # ⚠️ Ne PAS utiliser request.url.path : le LB GCP réécrit le path
            # (ex: /cv-api/pubsub/import-cv → /pubsub/import-cv) donc il ne
            # correspond plus à l'audience dans le token OIDC.
            # On lit l'audience depuis une env var injectée par Terraform,
            # qui est identique à push_config.oidc_token.audience dans pubsub.tf.
            pubsub_audience = os.getenv("PUBSUB_CV_IMPORT_AUDIENCE", "")
            if not pubsub_audience:
                # Fallback: reconstruction depuis Host + path original (dev local sans LB)
                pubsub_audience = f"https://{request.headers.get('host', '')}{request.url.path}"
            decoded = google_id_token.verify_oauth2_token(
                oidc_token,
                google_requests.Request(),
                audience=pubsub_audience
            )
            token_email = decoded.get("email", "")
            if token_email != invoker_sa_email:
                logger.warning(f"[PubSub] SA non autorisé: {token_email} (attendu: {invoker_sa_email})")
                raise HTTPException(status_code=401, detail="Unauthorized Pub/Sub invoker")
            logger.info(f"[PubSub] OIDC validé pour {token_email} (audience: {pubsub_audience})")
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"[PubSub] Échec validation OIDC: {e}")
            raise HTTPException(status_code=401, detail=f"Invalid OIDC token: {e}")

    # ── 2. Décodage du payload Pub/Sub ───────────────────────────────────────
    try:
        body = await request.json()
        message = body.get("message", {})
        raw_data = base64.b64decode(message.get("data", "")).decode("utf-8")
        payload = json.loads(raw_data)
    except Exception as e:
        logger.error(f"[PubSub] Payload invalide: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid Pub/Sub payload: {e}")

    google_file_id = payload.get("google_file_id", "")
    url = payload.get("url", "")
    source_tag = payload.get("source_tag", "")
    folder_name = payload.get("folder_name", "")
    google_access_token = payload.get("google_access_token")
    file_type = payload.get("file_type", "google_doc")  # "google_doc" | "docx"
    oidc_token = payload.get("oidc_token", "")   # Production: OIDC ID Token Google (RS256, 1h)
    jwt = payload.get("jwt", "")                  # Local dev: MOCK_M2M_JWT fallback

    if not url or not google_file_id:
        logger.error("[PubSub] Payload incomplet (url ou google_file_id manquant)")
        raise HTTPException(status_code=400, detail="Payload incomplet")

    # ── Fix #4 : Échange du token OIDC Google → JWT applicatif frais ─────────
    # En production, drive_api embarque un OIDC ID Token (validité 1h) dans le message Pub/Sub
    # à la place du JWT applicatif HS256 qui expirait pendant le backoff Pub/Sub (30s→600s).
    # Le worker échange le token OIDC ici, au moment réel du traitement, pour un JWT frais.
    if oidc_token:
        try:
            async with httpx.AsyncClient(timeout=10.0) as oidc_client:
                oidc_res = await oidc_client.post(
                    f"{USERS_API_URL.rstrip('/')}/service-account/login",
                    json={"id_token": oidc_token},
                )
                if oidc_res.status_code == 200:
                    jwt = oidc_res.json().get("access_token", "")
                    logger.info(f"[PubSub] OIDC token échangé → JWT applicatif frais obtenu.")
                else:
                    logger.error(f"[PubSub] Échange OIDC échoué (HTTP {oidc_res.status_code}) — retry Pub/Sub.")
                    raise HTTPException(status_code=500, detail=f"OIDC exchange failed: HTTP {oidc_res.status_code}")
        except HTTPException:
            raise
        except Exception as e_oidc:
            logger.error(f"[PubSub] Impossible d'échanger l'OIDC token: {e_oidc}")
            raise HTTPException(status_code=500, detail=f"OIDC exchange error: {e_oidc}")

        # ── Upgrade vers un service-token longue durée (90 min) ─────────────
        # Le JWT issu de service-account/login n'a que 15 min (ACCESS_TOKEN_EXPIRE_MINUTES).
        # Le traitement Gemini + compétences + missions peut dépasser ce délai → 403 sur items_api.
        # On échange vers /internal/service-token qui délivre un token de 90 min.
        if jwt:
            try:
                async with httpx.AsyncClient(timeout=10.0) as svc_client:
                    svc_res = await svc_client.post(
                        f"{USERS_API_URL.rstrip('/')}/internal/service-token",
                        headers={"Authorization": f"Bearer {jwt}"},
                    )
                    if svc_res.status_code == 200:
                        jwt = svc_res.json().get("access_token", jwt)
                        logger.info(f"[PubSub] Service-token longue durée obtenu (90 min).")
                    else:
                        logger.warning(f"[PubSub] Upgrade service-token échoué (HTTP {svc_res.status_code}) — JWT court conservé (15 min).")
            except Exception as e_svc:
                logger.warning(f"[PubSub] Impossible d'obtenir le service-token longue durée: {e_svc} — JWT court conservé.")

    if not jwt:
        logger.error("[PubSub] Aucun token d'authentification dans le payload (ni oidc_token, ni jwt).")
        raise HTTPException(status_code=500, detail="Configuration error: aucun token dans le message Pub/Sub")

    headers = {"Authorization": f"Bearer {jwt}"}
    inject(headers)
    logger.info(f"[PubSub] Traitement de {google_file_id} ({url})")

    drive_api_url = os.getenv("DRIVE_API_URL", "http://drive_api:8006")
    try:
        async with httpx.AsyncClient(timeout=10.0) as patch_client:
            res = await patch_client.patch(
                f"{drive_api_url.rstrip('/')}/files/{google_file_id}",
                json={"status": "PROCESSING"},
                headers=headers
            )
            if res.is_error:
                logger.error(f"[PubSub] Échec PATCH PROCESSING vers drive_api: HTTP {res.status_code} - {res.text}")
    except Exception as e:
        logger.warning(f"[PubSub] Impossible de notifier drive_api (PROCESSING): {e}")

    # ── 4. Décoder le JWT applicatif pour obtenir token_payload compatible ────
    # Le JWT a été obtenu via échange OIDC (prod) ou MOCK_M2M_JWT (local).
    # Il est nécessaire pour que process_cv_core puisse appeler les services internes
    # (users_api, competencies_api, missions_api) avec une identité valide.
    # _AUTH_SECRET_KEY est la constante chargée au démarrage par src.auth (avant purge env)
    if not _AUTH_SECRET_KEY:
        logger.error("[PubSub] SECRET_KEY absente — impossible de valider le JWT interne.")
        raise HTTPException(status_code=500, detail="Configuration error: SECRET_KEY manquante")
    try:
        token_payload = jose_jwt.decode(jwt, _AUTH_SECRET_KEY, algorithms=["HS256"])
    except JWTError as e:
        logger.error(f"[PubSub] JWT interne invalide (corrompu ou expiré): {e}")
        raise HTTPException(status_code=500, detail=f"JWT interne invalide: {e}")


    # ── 5. Pipeline LLM en BackgroundTask → ACK immédiat pour Pub/Sub ─────────
    # ARCHITECTURE : Pub/Sub slow-start algorithm mesure le temps de réponse de
    # l'endpoint pour calibrer sa concurrence. Une réponse en 2 min → concurrence=1.
    # En retournant 202 en < 1s, Pub/Sub monte la concurrence à 10+ messages simultanés.
    # Le pipeline complet (Gemini + compétences + missions) s'exécute en arrière-plan.
    # Les statuts drive_api (PROCESSING → IMPORTED_CV / ERROR) restent correctement trackés.

    async def _run_cv_pipeline_bg(
        bg_google_file_id: str,
        bg_url: str,
        bg_google_access_token: Optional[str],
        bg_source_tag: Optional[str],
        bg_folder_name: Optional[str],
        bg_headers: dict,
        bg_jwt: str,
        bg_token_payload: dict,
        bg_drive_api_url: str,
        bg_file_type: str = "google_doc",
    ):
        """Pipeline complet exécuté en arrière-plan après ACK Pub/Sub."""
        pipeline_start_time = time.monotonic()  # Chrono pour KPI processing_duration_ms
        async with database.SessionLocal() as bg_db:
            try:
                local_bg_tasks = BackgroundTasks()
                result = await process_cv_core(
                    url=bg_url,
                    google_access_token=bg_google_access_token,
                    source_tag=bg_source_tag,
                    folder_name=bg_folder_name,
                    headers=bg_headers,
                    token_payload=bg_token_payload,
                    db=bg_db,
                    auth_token=bg_jwt,
                    file_type=bg_file_type,
                    background_tasks=local_bg_tasks, genai_client=_svc_config.client
                )
                
                # IMPORTANT: Starlette's BackgroundTasks are not automatically executed 
                # when not returned in an HTTP response. We must execute them manually.
                await local_bg_tasks()
                # Notification succès → drive_api (avec durée de traitement pour KPIs)
                pipeline_duration_ms = int((time.monotonic() - pipeline_start_time) * 1000)
                try:
                    async with httpx.AsyncClient(timeout=10.0) as patch_client:
                        res = await patch_client.patch(
                            f"{bg_drive_api_url.rstrip('/')}/files/{bg_google_file_id}",
                            json={
                                "status": "IMPORTED_CV",
                                "user_id": result.user_id,
                                "error_message": None,
                                "processing_duration_ms": pipeline_duration_ms,
                            },
                            headers=bg_headers
                        )
                        if res.is_error:
                            logger.error(f"[PubSub/BG] Échec PATCH IMPORTED_CV: HTTP {res.status_code}")
                        else:
                            logger.info(f"[PubSub/BG] Import réussi {bg_google_file_id} → user_id={result.user_id} duration={pipeline_duration_ms}ms")
                except Exception as e:
                    logger.warning(f"[PubSub/BG] Impossible de notifier drive_api (IMPORTED_CV): {e}")

            except HTTPException as he:
                error_detail = he.detail
                status = "IGNORED_NOT_CV" if ("Not a CV" in str(error_detail) or "LLM Parsing failed" in str(error_detail)) else "ERROR"
                logger.error(f"[PubSub/BG] Échec pipeline {bg_google_file_id}: {error_detail} → statut={status}")
                try:
                    async with httpx.AsyncClient(timeout=10.0) as patch_client:
                        await patch_client.patch(
                            f"{bg_drive_api_url.rstrip('/')}/files/{bg_google_file_id}",
                            json={"status": status, "error_message": str(error_detail)},
                            headers=bg_headers
                        )
                except Exception as e:
                    logger.warning(f"[PubSub/BG] Impossible de notifier drive_api ({status}): {e}")

            except Exception as ex:
                logger.error(f"[PubSub/BG] Erreur inattendue pour {bg_google_file_id}: {ex}", exc_info=True)
                try:
                    async with httpx.AsyncClient(timeout=10.0) as patch_client:
                        await patch_client.patch(
                            f"{bg_drive_api_url.rstrip('/')}/files/{bg_google_file_id}",
                            json={"status": "ERROR", "error_message": f"Erreur inattendue: {ex}"},
                            headers=bg_headers
                        )
                except Exception: raise

    # Lancement du pipeline en arrière-plan
    # IMPORTANT : toute exception ici (NameError, AttributeError, etc.) laisserait
    # le CV en PROCESSING sans jamais le passer en ERROR. On wrappe add_task pour
    # attraper ces erreurs de setup et notifier drive_api immédiatement.
    try:
        background_tasks.add_task(
            _run_cv_pipeline_bg,
            google_file_id, url, google_access_token, source_tag, folder_name,
            headers, jwt, token_payload, drive_api_url,
            file_type,
        )
    except Exception as setup_err:
        logger.error(f"[PubSub] Impossible de planifier le BackgroundTask pour {google_file_id}: {setup_err}", exc_info=True)
        # PATCH drive_api en ERROR pour éviter que le CV reste bloqué en PROCESSING
        try:
            async with httpx.AsyncClient(timeout=10.0) as err_client:
                await err_client.patch(
                    f"{drive_api_url.rstrip('/')}/files/{google_file_id}",
                    json={"status": "ERROR", "error_message": f"Erreur setup pipeline: {setup_err}"},
                    headers=headers
                )
        except Exception: raise
        # Retourner 500 pour que Pub/Sub retente après correction du code
        raise

    # ACK immédiat → Pub/Sub augmente la concurrence via slow-start
    logger.info(f"[PubSub] Message {google_file_id} accepté — pipeline en arrière-plan.")
    return {"status": "accepted", "google_file_id": google_file_id}



@router.get("/users/tags/map", response_model=dict[str, str])
async def get_all_user_tags(db: AsyncSession = Depends(get_db)):
    """
    Retourne un mapping global {str(user_id): source_tag} pour tous les CVs.
    Pratique pour afficher l'agence dans la liste des utilisateurs du panel admin
    sans problème de N+1 requêtes.
    """
    # Pour garantir le bon tag, on trie par date ascendante, 
    # de sorte que le dernier CV écrase les précédents dans le dictionnaire.
    profiles = (await db.execute(
        select(CVProfile.user_id, CVProfile.source_tag)
        .filter(CVProfile.source_tag.is_not(None))
        .order_by(CVProfile.created_at.asc())
    )).all()
    return {str(p.user_id): p.source_tag for p in profiles}


@router.get("/users/tag/{tag}", response_model=List[CVProfileResponse])
async def get_users_by_tag(tag: str, request: Request = None, db: AsyncSession = Depends(get_db)):
    """
    Récupère les profils CV (et user_ids) associés à un tag spécifique (ex: localisation 'Niort').
    Sans redondance par utilisateur (déduplication).
    """
    # On utilise DISTINCT ON pour récupérer uniquement le CV le plus récent par utilisateur
    profiles = (await db.execute(
        select(CVProfile)
        .distinct(CVProfile.user_id)
        .order_by(CVProfile.user_id, CVProfile.created_at.desc())
    )).scalars().all()
    
    seen_users = set()
    unique_profiles = []
    
    for p in profiles:
        # On ne garde que les utilisateurs dont le CV le plus récent correspond au tag
        if p.source_tag and tag.lower() in p.source_tag.lower():
            if p.user_id not in seen_users:
                seen_users.add(p.user_id)
                unique_profiles.append(p)
    # Group by user for bulk enrichment
    user_ids = list(seen_users)
    user_enrich_map = {}
    auth_header = request.headers.get("Authorization") if request else None
    headers_downstream = {"Authorization": auth_header} if auth_header else {}
    inject(headers_downstream)
    
    async with httpx.AsyncClient(timeout=10.0) as http_client:
        for u_id in user_ids:
            try:
                u_res = await http_client.get(f"{USERS_API_URL.rstrip('/')}/{u_id}", headers=headers_downstream)
                if u_res.status_code == 200:
                    user_enrich_map[u_id] = u_res.json()
            except Exception as e:
                logger.warning(f"Failed to fetch user {u_id} for enrichment: {e}")

    return [
        CVProfileResponse(
            user_id=p.user_id,
            source_url=p.source_url,
            source_tag=p.source_tag,
            imported_by_id=p.imported_by_id,
            is_anonymous=user_enrich_map.get(p.user_id, {}).get("is_anonymous", False),
            full_name=user_enrich_map.get(p.user_id, {}).get("full_name"),
            email=user_enrich_map.get(p.user_id, {}).get("email"),
            username=user_enrich_map.get(p.user_id, {}).get("username")
        ) for p in unique_profiles
    ]


@router.get("/user/{user_id}", response_model=List[CVProfileResponse])
async def get_user_cv(user_id: int, request: Request = None, db: AsyncSession = Depends(get_db)):
    """
    Récupére le ou les liens source (Google Doc) originaux des CVs associés au collaborateur.
    """
    profiles = (await db.execute(select(CVProfile).filter(CVProfile.user_id == user_id).order_by(CVProfile.created_at.desc()))).scalars().all()
    if not profiles:
        raise HTTPException(status_code=404, detail="Aucun CV trouvé pour cet utilisateur.")
        
    # Fetch user details for anonymity status
    is_anon = False
    auth_header = request.headers.get("Authorization") if request else None
    headers_downstream = {"Authorization": auth_header} if auth_header else {}
    inject(headers_downstream)
    async with httpx.AsyncClient(timeout=5.0) as http_client:
        try:
            u_res = await http_client.get(f"{USERS_API_URL.rstrip('/')}/{user_id}", headers=headers_downstream)
            if u_res.status_code == 200:
                is_anon = u_res.json().get("is_anonymous", False)
        except Exception as e:
            logger.warning(f"Failed to fetch user {user_id} for is_anonymous check: {e}")

    return [
        CVProfileResponse(
            user_id=p.user_id,
            source_url=p.source_url,
            source_tag=p.source_tag,
            imported_by_id=p.imported_by_id,
            is_anonymous=is_anon
        ) for p in profiles
    ]


@router.get("/user/{user_id}/missions")
async def get_user_missions(user_id: int, db: AsyncSession = Depends(get_db)):
    """
    Récupère le détail des missions extraites du CV pour un utilisateur.
    """
    profiles = (await db.execute(select(CVProfile).filter(CVProfile.user_id == user_id).order_by(CVProfile.created_at.desc()))).scalars().all()
    if not profiles:
        raise HTTPException(status_code=404, detail="Aucun profil CV trouvé pour cet utilisateur.")
    
    merged_missions = []
    seen_mission_keys = set()
    
    for profile in profiles:
        if not profile.missions:
            continue
        for mission in profile.missions:
            title = mission.get("title", "").strip().lower()
            company = mission.get("company", "").strip().lower()
            key = f"{title}|{company}"
            
            if key not in seen_mission_keys:
                seen_mission_keys.add(key)
                merged_missions.append(mission)
                
    return {"user_id": user_id, "missions": merged_missions}


@router.get("/user/{user_id}/details", response_model=CVFullProfileResponse)
async def get_user_cv_details(user_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """
    Récupère le profil sémantique complet d'un utilisateur (RAG Context).
    """
    profiles = (await db.execute(
        select(CVProfile)
        .filter(CVProfile.user_id == user_id)
        .order_by(CVProfile.created_at.desc())
    )).scalars().all()
    
    if not profiles:
        raise HTTPException(status_code=404, detail="Profil sémantique introuvable pour cet utilisateur.")
        
    base_profile = profiles[0]
        
    # Fetch user details for anonymity status
    is_anon = False
    
    # Propagate Authorization and Tracing (Rule 3 & 4)
    auth_header = request.headers.get("Authorization")
    headers = {"Authorization": auth_header} if auth_header else {}
    inject(headers)

    async with httpx.AsyncClient(timeout=5.0) as http_client:
        try:
            u_res = await http_client.get(f"{USERS_API_URL.rstrip('/')}/{user_id}", headers=headers)
            if u_res.status_code == 200:
                is_anon = u_res.json().get("is_anonymous", False)
        except Exception as e:
            logger.warning(f"Failed to fetch user anonymity status for {user_id}: {e}")

    # Inférer seniority depuis years_of_experience si non stocké directement
    years = base_profile.years_of_experience or 0
    if years >= 8:
        inferred_seniority = "Senior"
    elif years >= 3:
        inferred_seniority = "Mid"
    elif years > 0:
        inferred_seniority = "Junior"
    else:
        inferred_seniority = None

    merged_missions = []
    seen_mission_keys = set()
    merged_comp_keywords = set()
    
    merged_educations = []
    seen_edu_keys = set()
    
    for p in profiles:
        if p.competencies_keywords:
            merged_comp_keywords.update(p.competencies_keywords)
            
        if p.educations:
            for edu in p.educations:
                degree = edu.get("degree", "").strip().lower()
                school = edu.get("school", "").strip().lower()
                key = f"{degree}|{school}"
                if key not in seen_edu_keys:
                    seen_edu_keys.add(key)
                    merged_educations.append(edu)
            
        if not p.missions:
            continue
        for mission in p.missions:
            title = mission.get("title", "").strip().lower()
            company = mission.get("company", "").strip().lower()
            key = f"{title}|{company}"
            
            if key not in seen_mission_keys:
                seen_mission_keys.add(key)
                merged_missions.append(mission)

    return CVFullProfileResponse(
        user_id=base_profile.user_id,
        summary=base_profile.summary,
        current_role=base_profile.current_role,
        seniority=inferred_seniority,
        years_of_experience=base_profile.years_of_experience,
        competencies_keywords=list(merged_comp_keywords),
        missions=merged_missions,
        educations=merged_educations,
        is_anonymous=is_anon
    )


@router.post("/internal/users/merge")
async def merge_users(req: UserMergeRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """
    Internal endpoint to merge user data.
    Updates cv_profiles.user_id = target_id where user_id = source_id.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing Authorization via CV merge")
        
    stmt = sa_update(CVProfile).where(CVProfile.user_id == req.source_id).values(user_id=req.target_id)
    await db.execute(stmt)
    
    stmt2 = sa_update(CVProfile).where(CVProfile.imported_by_id == req.source_id).values(imported_by_id=req.target_id)
    await db.execute(stmt2)

    await db.commit()
    return {"message": f"Successfully migrated CVs from user {req.source_id} to {req.target_id}"}



@public_router.post("/pubsub/user-events")
async def handle_user_pubsub_events(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Handle GCP Pub/Sub Push Notifications for CV API.
    """
    try:
        payload = await request.json()
        message = payload.get("message")
        if not message or "data" not in message:
            return {"status": "ignored"}

        data_str = base64.b64decode(message["data"]).decode("utf-8")
        event_data = json.loads(data_str)
        event_type = event_data.get("event")
        data = event_data.get("data", {})
        
        if event_type == "user.merged":
            source_id = data.get("source_id")
            target_id = data.get("target_id")
            if source_id and target_id:
                stmt = sa_update(CVProfile).where(CVProfile.user_id == source_id).values(user_id=target_id)
                await db.execute(stmt)
                
                # Update profiles imported BY the user
                stmt2 = sa_update(CVProfile).where(CVProfile.imported_by_id == source_id).values(imported_by_id=target_id)
                await db.execute(stmt2)
                
                await db.commit()
        
        return {"status": "processed"}
    except Exception as e:
        logger.error(f"Error processing Pub/Sub event: {e}")
        return {"status": "error", "detail": str(e)}


