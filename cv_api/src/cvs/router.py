from fastapi import APIRouter, Depends, HTTPException, Request, Response, Query, BackgroundTasks
from fastapi.security import HTTPAuthorizationCredentials
import json
import math
import tempfile
import time
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, delete as sa_delete, text as sa_text, update as sa_update, JSON
import httpx
import os
import re
import unicodedata
from typing import Any, Optional, List
from pydantic import BaseModel
from google import genai
from google.genai import types
from google.cloud import storage as gcs_storage
from google.cloud import run_v2 as cloudrun_v2
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests
from opentelemetry.propagate import inject
from jose import jwt as jose_jwt
import asyncio
import base64
from datetime import datetime, timedelta, timezone
from jose.exceptions import JWTError
import random
import string
import traceback
import urllib.parse
import logging

from database import get_db
import database
from src.auth import verify_jwt, security, SECRET_KEY as _AUTH_SECRET_KEY
from src.cvs.models import CVProfile
from src.cvs.schemas import CVImportRequest, CVImportStep, CVResponse, SearchCandidateResponse, SearchCandidateRequest, CVProfileResponse, CVFullProfileResponse, UserMergeRequest, RankedExperienceResponse
from .task_state import task_state_manager, tree_task_manager
from .bulk_task_state import bulk_reanalyse_manager
from metrics import CV_PROCESSING_TOTAL, CV_MISSING_EMBEDDINGS
from src.gemini_retry import generate_content_with_retry, embed_content_with_retry

# --- SERVICES IMPORTS ---
from src.services.cv_import_service import process_cv_core
from src.services.search_service import execute_search, scale_bulk_dependencies
from src.services.config import client, vertex_batch_client
from src.services.taxonomy_service import (
    run_taxonomy_step,
    fetch_prompt,
    get_existing_competencies,
)
from src.services.finops import log_finops
from src.services.embedding_service import reindex_embeddings_bg
from src.services.bulk_service import bg_bulk_reanalyse, _acquire_service_token, bg_retry_apply
from src.services.utils import _build_distilled_content, _clean_llm_json, _chunk_text

# Aliases underscore — maintenus pour la compatibilité avec les appels existants dans ce router
_fetch_prompt = fetch_prompt
_get_existing_competencies = get_existing_competencies
_bg_retry_apply = bg_retry_apply
# ------------------------

# ── Schéma JSON partagé entre route unitaire ET batch Vertex ─────────────────
# Toute modification ici s'applique automatiquement aux deux pipelines.
_CV_RESPONSE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "is_cv": {"type": "boolean"},
        "first_name": {"type": "string"},
        "last_name": {"type": "string"},
        "email": {"type": "string"},
        "summary": {"type": "string"},
        "current_role": {"type": "string"},
        "years_of_experience": {"type": "integer"},
        "competencies": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "parent": {"type": "string"},
                    "aliases": {"type": "array", "items": {"type": "string"}},
                    "practiced": {
                        "type": "boolean",
                        "description": "True if the consultant has actively used this skill in at least one mission."
                    }
                },
                "required": ["name", "practiced"]
            }
        },
        "missions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "company": {"type": "string"},
                    "description": {"type": "string"},
                    "start_date": {"type": "string", "description": "YYYY-MM or YYYY, null if unknown"},
                    "end_date": {"type": "string", "description": "YYYY-MM, YYYY, 'present', or null"},
                    "duration": {"type": "string", "description": "Explicit duration from CV text, null if not stated"},
                    "mission_type": {"type": "string", "description": "One of: audit, conseil, accompagnement, formation, expertise, build"},
                    "is_sensitive": {"type": "boolean"},
                    "competencies": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["title", "competencies", "is_sensitive", "mission_type"]
            }
        },
        "educations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "degree": {"type": "string"},
                    "school": {"type": "string"}
                }
            }
        },
        "is_anonymous": {"type": "boolean"},
        "trigram": {"type": "string"}
    },
    "required": ["is_cv", "first_name", "last_name", "email", "summary", "current_role",
                 "years_of_experience", "competencies", "missions", "educations", "is_anonymous"]
}


router = APIRouter(prefix="", tags=["CV Analysis"], dependencies=[Depends(verify_jwt)])
public_router = APIRouter(prefix="", tags=["CV_Public"])

USERS_API_URL = os.getenv("USERS_API_URL", "http://users_api:8000")
COMPETENCIES_API_URL = os.getenv("COMPETENCIES_API_URL", "http://competencies_api:8003")
PROMPTS_API_URL = os.getenv("PROMPTS_API_URL", "http://prompts_api:8000")
DRIVE_API_URL = os.getenv("DRIVE_API_URL", "http://drive_api:8006")
ITEMS_API_URL = os.getenv("ITEMS_API_URL", "http://items_api:8001")

# Credentials admin pour les tâches de fond (bulk reanalyse)
# Permettent de générer un service token indépendamment du token utilisateur appelant.
# AGENTS.md §4 : les tâches longues doivent utiliser un compte de service dédié.
ADMIN_SERVICE_USERNAME = os.getenv("ADMIN_SERVICE_USERNAME", "")
ADMIN_SERVICE_PASSWORD = os.getenv("ADMIN_SERVICE_PASSWORD", "")

GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY", "")
ANALYTICS_MCP_URL = os.getenv("ANALYTICS_MCP_URL", "http://analytics_mcp:8008")
VERTEX_LOCATION = os.getenv("VERTEX_LOCATION", "europe-west1")
BATCH_GCS_BUCKET = os.getenv("BATCH_GCS_BUCKET", "")

# ── Parallélisme du pipeline bulk-reanalyse (configurable via env) ────────────
# BULK_APPLY_SEMAPHORE : nombre de CVs appliqués simultanément (DB + HTTP).
#   Défaut 5 — safe pour AlloyDB avec pool_size=20 (5 workers × 3 conn max = 15).
# BULK_EMBED_SEMAPHORE : nombre d'appels Gemini Embedding API simultanés.
#   Défaut 10 — conservative vs quota Gemini Embedding (600 QPM Vertex AI).
BULK_APPLY_SEMAPHORE: int = int(os.getenv("BULK_APPLY_SEMAPHORE", "5"))
BULK_EMBED_SEMAPHORE: int = int(os.getenv("BULK_EMBED_SEMAPHORE", "10"))

# ── Scaling dynamique des Cloud Run cibles pendant le Bulk Apply ─────────
# CLOUDRUN_WORKSPACE : workspace Terraform (ex: "prd", "dev") — injecté via cr_cv.tf.
# BULK_SCALE_SERVICES : noms logiques des services à scaler (sans workspace suffix).
CLOUDRUN_WORKSPACE: str = os.getenv("CLOUDRUN_WORKSPACE", "")
BULK_SCALE_SERVICES: list[str] = ["competencies-api", "items-api"]
# Nombre d'instances minimum à maintenir PENDANT la phase APPLY.
# Défaut 1 : évite les cold starts AlloyDB IAM (~15s) sans sur-provisionner.
# Augmenter à 2+ si Cloud Run auto-scale trop lentement sous charge.
# MATH pour 1000 CVs (BULK_APPLY_SEMAPHORE=5) :
#   competencies_api : 5×3=15 req simultanées, pool=30/instance → 1 instance ok
#   items_api        : 5×2=10 req simultanées, pool=30/instance → 1 instance ok
# Si BULK_APPLY_SEMAPHORE passe à 10, augmenter BULK_SCALE_MIN_INSTANCES à 2.
BULK_SCALE_MIN_INSTANCES: int = int(os.getenv("BULK_SCALE_MIN_INSTANCES", "1"))

# ------------------------


GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "")

if not GEMINI_API_KEY:
    print("WARNING: GOOGLE_API_KEY is missing. RAG embeddings will fail.")
    client = None
else:
    client = genai.Client(api_key=GEMINI_API_KEY)

# Client Vertex AI dédié au pipeline Batch Taxonomie (IAM/ADC, pas d'API key)
# Distinct du client 'client' utilisé pour les embeddings (api_key).
if GCP_PROJECT_ID and VERTEX_LOCATION:
    vertex_batch_client = genai.Client(
        vertexai=True,
        project=GCP_PROJECT_ID,
        location=VERTEX_LOCATION
    )
else:
    vertex_batch_client = None
    print("WARNING: GCP_PROJECT_ID ou VERTEX_LOCATION manquant. Vertex AI Batch indisponible.")

logger = logging.getLogger(__name__)

# Note : plus de lock global ici.
# competencies_api gère l'idempotence nativement : POST avec un nom existant
# retourne HTTP 200 avec l'entité existante (check_grammatical_conflict → exact match).
# Un lock global asyncio.Lock() ici sérialisait ALL les BackgroundTasks CV concurrents,
# causant N_cvs × N_comps × 2 acquisitions séquentielles (ex: 47 × 25 × 2 = 2350 appels
# en file unique → 1-2h de blocage observé sous charge).
_CV_CACHE = {
    "prompt": {"value": None, "expires": datetime.min},
    "tree_items": {"value": None, "expires": datetime.min},
    "tree_context": {"value": None, "expires": datetime.min}
}

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
        background_tasks=background_tasks, genai_client=client
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
                    background_tasks=local_bg_tasks, genai_client=client
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


@router.get("/search", response_model=List[SearchCandidateResponse])
async def search_candidates(
    request: Request,
    response: Response,
    query: str, 
    limit: int = 5, 
    skills: List[str] = Query(default=None),
    agency: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    token_payload: dict = Depends(verify_jwt),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    return await execute_search(request, response, query, limit, skills, db, token_payload, credentials, client, agency)

@router.post("/search", response_model=List[SearchCandidateResponse])
async def search_candidates_post(
    req_body: SearchCandidateRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    token_payload: dict = Depends(verify_jwt),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    return await execute_search(request, response, req_body.query, req_body.limit, req_body.skills, db, token_payload, credentials, client, req_body.agency)

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
        
    background_tasks.add_task(run_taxonomy_step, auth_header, user_caller, req_body.step, client, req_body.target_pillar)
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
        background_tasks.add_task(run_taxonomy_step, auth_header, user_caller, "map", client)
    else:
        background_tasks.add_task(run_taxonomy_step, auth_header, user_caller, "reduce", client)

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

@router.get("/user/{user_id}/similar")
async def find_similar_consultants(
    user_id: int,
    limit: int = Query(default=5, le=20),
    agency: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    token_payload: dict = Depends(verify_jwt),
    request: Request = None,
):
    """Retourne les N consultants dont le profil sémantique est le plus proche d'un consultant donné.
    Utile pour : cloner un profil de staffing, trouver des remplaçants potentiels, constituer une équipe.
    Zéro appel LLM — résultat O(log N) grâce à l'index HNSW pgvector.
    """
    # Récupère l'embedding du profil source
    source_result = await db.execute(
        select(CVProfile.semantic_embedding).filter(CVProfile.user_id == user_id)
    )
    source_embedding = source_result.scalar_one_or_none()
    if source_embedding is None:
        raise HTTPException(status_code=404, detail=f"Profil introuvable ou embedding manquant pour user_id={user_id}")

    stmt = (
        select(CVProfile, CVProfile.semantic_embedding.cosine_distance(source_embedding).label("distance"))
        .filter(CVProfile.user_id != user_id)
        .filter(CVProfile.semantic_embedding.is_not(None))
    )
    if agency:
        stmt = stmt.filter(CVProfile.source_tag.ilike(f"%{agency}%"))

    stmt = stmt.order_by("distance").limit(limit)
    rows = (await db.execute(stmt)).all()

    auth_header = request.headers.get("Authorization") if request else None
    headers_downstream = {"Authorization": auth_header} if auth_header else {}
    inject(headers_downstream)

    results = []
    async with httpx.AsyncClient(timeout=8.0) as http_client:
        for profile, distance in rows:
            entry = {
                "user_id": profile.user_id,
                "similarity_score": round(max(0.0, 1.0 - distance), 4),
                "current_role": profile.current_role,
                "years_of_experience": profile.years_of_experience,
                "source_tag": profile.source_tag,
            }
            try:
                u_res = await http_client.get(
                    f"{USERS_API_URL.rstrip('/')}/{profile.user_id}", headers=headers_downstream
                )
                if u_res.status_code == 200:
                    u_data = u_res.json()
                    entry["full_name"] = u_data.get("full_name")
                    entry["email"] = u_data.get("email")
            except Exception as e:
                logger.warning(f"[SIMILAR] Enrichissement user {profile.user_id} échoué: {e}")
            results.append(entry)

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Sprint A2 — Recherche multi-critères (N vecteurs pondérés, 1 requête SQL)
# ─────────────────────────────────────────────────────────────────────────────

class MultiCriteriaSearchRequest(BaseModel):
    queries: List[str]
    weights: Optional[List[float]] = None
    limit: int = 10
    agency: Optional[str] = None


@router.post("/search/multi-criteria")
async def search_candidates_multi_criteria(
    req_body: MultiCriteriaSearchRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    token_payload: dict = Depends(verify_jwt),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Recherche sémantique multi-critères : trouve les consultants correspondant à
    PLUSIEURS dimensions simultanément via une moyenne pondérée de distances cosine.
    Remplace N appels search_best_candidates séquentiels par une seule requête SQL.
    Exemple : queries=["expert GCP", "migration legacy"], weights=[0.7, 0.3]
    """
    if not client:
        raise HTTPException(status_code=500, detail="Client Gemini non configuré.")
    if not req_body.queries:
        raise HTTPException(status_code=400, detail="Au moins une query est requise.")
    if len(req_body.queries) > 5:
        raise HTTPException(status_code=400, detail="Maximum 5 critères simultanés.")

    weights = req_body.weights or [1.0 / len(req_body.queries)] * len(req_body.queries)
    if len(weights) != len(req_body.queries):
        raise HTTPException(status_code=400, detail="Nombre de weights ≠ nombre de queries.")

    # Normaliser les weights pour que leur somme = 1
    total_w = sum(weights)
    weights = [w / total_w for w in weights]

    # Calculer un embedding par query
    embeddings = []
    for q in req_body.queries:
        try:
            emb_res = await embed_content_with_retry(
                client,
                model=os.getenv("GEMINI_EMBEDDING_MODEL"),
                contents=q[:3000]
            )
            embeddings.append(emb_res.embeddings[0].values)
        except Exception as e:
            logger.error(f"[MULTI-SEARCH] Embedding échoué pour query '{q}': {e}")
            raise HTTPException(status_code=400, detail=f"Embedding échoué pour: {q}")

    # Score combiné = somme pondérée des distances cosine
    combined_distance = sum(
        CVProfile.semantic_embedding.cosine_distance(emb) * w
        for emb, w in zip(embeddings, weights)
    )

    stmt = (
        select(CVProfile, combined_distance.label("combined_distance"))
        .filter(CVProfile.semantic_embedding.is_not(None))
    )
    if req_body.agency:
        stmt = stmt.filter(CVProfile.source_tag.ilike(f"%{req_body.agency}%"))
    stmt = stmt.order_by("combined_distance").limit(req_body.limit * 2)

    rows = (await db.execute(stmt)).all()

    user_caller = token_payload.get("sub", "unknown")
    for q in req_body.queries:
        await log_finops(
            user_caller, "multi_criteria_embedding",
            os.getenv("GEMINI_EMBEDDING_MODEL"),
            {"prompt_token_count": len(q) // 4, "candidates_token_count": 0},
            auth_token=credentials.credentials
        )

    auth_header = request.headers.get("Authorization")
    headers_downstream = {"Authorization": auth_header} if auth_header else {}
    inject(headers_downstream)

    results, seen = [], set()
    async with httpx.AsyncClient(timeout=8.0) as http_client:
        for profile, dist in rows:
            if profile.user_id in seen:
                continue
            seen.add(profile.user_id)
            score = round(max(0.0, 1.0 - float(dist)), 4)
            entry = {
                "user_id": profile.user_id,
                "combined_similarity": score,
                "current_role": profile.current_role,
                "years_of_experience": profile.years_of_experience,
                "source_tag": profile.source_tag,
            }
            try:
                u_res = await http_client.get(
                    f"{USERS_API_URL.rstrip('/')}/{profile.user_id}", headers=headers_downstream
                )
                if u_res.status_code == 200:
                    u_data = u_res.json()
                    entry["full_name"] = u_data.get("full_name")
                    entry["email"] = u_data.get("email")
            except Exception as e:
                logger.warning(f"[MULTI-SEARCH] Enrichissement user {profile.user_id} échoué: {e}")
            results.append(entry)
            if len(results) >= req_body.limit:
                break

    if not results:
        raise HTTPException(status_code=404, detail="Aucun candidat correspondant à ces critères combinés.")
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Sprint A3 — RAG Snippet (passages les plus pertinents d'un CV pour une query)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/user/{user_id}/rag-snippet")
async def get_rag_snippet(
    user_id: int,
    query: str = Query(..., description="La requête pour laquelle chercher les passages pertinents"),
    top_k: int = Query(default=3, le=5),
    db: AsyncSession = Depends(get_db),
    token_payload: dict = Depends(verify_jwt),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Retourne les passages les plus pertinents du CV d'un consultant pour une query donnée.
    Utilise un chunking du distilled_content + re-ranking par similarité cosine.
    Permet de JUSTIFIER une recommandation avec des preuves textuelles précises.
    Timeout MCP : 30s (embedding de la query + N passages).
    """
    if not client:
        raise HTTPException(status_code=500, detail="Client Gemini non configuré.")

    profile = (await db.execute(
        select(CVProfile).filter(CVProfile.user_id == user_id).order_by(CVProfile.created_at.desc())
    )).scalars().first()

    if not profile:
        raise HTTPException(status_code=404, detail=f"Profil introuvable pour user_id={user_id}")

    # Reconstituer le distilled_content depuis les champs structurés en base
    structured_cv = {
        "current_role": profile.current_role or "Unknown",
        "years_of_experience": profile.years_of_experience or 0,
        "summary": profile.summary or "",
        "competencies": [{"name": k} for k in (profile.competencies_keywords or [])],
        "educations": profile.educations or [],
        "missions": profile.missions or [],
    }
    distilled = _build_distilled_content(structured_cv)

    # Chunking du contenu distillé
    passages = _chunk_text(distilled, chunk_size=150, overlap=20)
    if not passages:
        return {"user_id": user_id, "snippets": [], "message": "Aucun contenu disponible pour ce profil."}

    # Embedding de la query
    try:
        query_emb_res = await embed_content_with_retry(
            client,
            model=os.getenv("GEMINI_EMBEDDING_MODEL"),
            contents=query[:3000]
        )
        query_vector = query_emb_res.embeddings[0].values
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Embedding de la query échoué: {e}")

    # Embedding de chaque passage (parallèle, max 10 passages)
    passages_to_rank = passages[:10]

    async def embed_passage(p: str):
        try:
            res = await embed_content_with_retry(
                client,
                model=os.getenv("GEMINI_EMBEDDING_MODEL"),
                contents=p
            )
            return res.embeddings[0].values
        except Exception:
            return None

    passage_embeddings = await asyncio.gather(*[embed_passage(p) for p in passages_to_rank])

    # Cosine similarity inline (pgvector non dispo ici — calcul Python sur N<10 passages)

    def cosine_sim(a, b):
        if not a or not b:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        return dot / (norm_a * norm_b + 1e-9)

    ranked = sorted(
        [(passages_to_rank[i], cosine_sim(query_vector, passage_embeddings[i]))
         for i in range(len(passages_to_rank)) if passage_embeddings[i] is not None],
        key=lambda x: x[1],
        reverse=True
    )

    await log_finops(
        token_payload.get("sub", "unknown"),
        "rag_snippet",
        os.getenv("GEMINI_EMBEDDING_MODEL"),
        {"prompt_token_count": (len(query) + len(distilled)) // 4, "candidates_token_count": 0},
        auth_token=credentials.credentials
    )

    return {
        "user_id": user_id,
        "query": query,
        "snippets": [
            {"text": text, "relevance_score": round(score, 4)}
            for text, score in ranked[:top_k]
        ]
    }


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


@router.post("/search/mission-match")
async def match_mission_to_candidates(
    request: Request,
    mission_id: int = Query(..., description="ID de la mission à staffer"),
    limit: int = Query(default=10, le=50),
    agency: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    token_payload: dict = Depends(verify_jwt),
):
    """Matching direct mission → candidats via le semantic_embedding de la mission.
    Plus précis que search_best_candidates pour le staffing car utilise le contexte
    complet de la mission (description + compétences extraites). Zéro appel LLM.
    Requiert que la mission ait été analysée par l'IA (semantic_embedding alimenté).
    """
    auth_header = request.headers.get("Authorization")
    headers_downstream = {"Authorization": auth_header} if auth_header else {}
    inject(headers_downstream)

    # 1. Récupérer l'embedding de la mission depuis missions_api
    try:
        async with httpx.AsyncClient(timeout=10.0) as http_client:
            mission_res = await http_client.get(
                f"{MISSIONS_API_URL.rstrip('/')}/missions/{mission_id}",
                headers=headers_downstream
            )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"missions_api inaccessible: {e}")

    if mission_res.status_code == 404:
        raise HTTPException(status_code=404, detail=f"Mission {mission_id} introuvable.")
    if mission_res.status_code != 200:
        raise HTTPException(status_code=502, detail=f"missions_api erreur HTTP {mission_res.status_code}")

    # Récupérer l'embedding directement en base (missions_api ne l'expose pas via l'API REST)
    # On requête cv_api's DB pour la mission via missions_api internal
    async with httpx.AsyncClient(timeout=10.0) as http_client:
        emb_res = await http_client.get(
            f"{MISSIONS_API_URL.rstrip('/')}/missions/{mission_id}/embedding",
            headers=headers_downstream
        )

    mission_embedding = None
    if emb_res.status_code == 200:
        mission_embedding = emb_res.json().get("embedding")

    if not mission_embedding:
        raise HTTPException(
            status_code=422,
            detail=f"La mission {mission_id} n'a pas d'embedding vectoriel. Lancez une ré-analyse via missions_api d'abord."
        )

    # 2. Cosine search dans cv_profiles
    stmt = (
        select(CVProfile, CVProfile.semantic_embedding.cosine_distance(mission_embedding).label("distance"))
        .filter(CVProfile.semantic_embedding.is_not(None))
    )
    if agency:
        stmt = stmt.filter(CVProfile.source_tag.ilike(f"%{agency}%"))
    stmt = stmt.order_by("distance").limit(limit)

    rows = (await db.execute(stmt)).all()

    results = []
    async with httpx.AsyncClient(timeout=8.0) as http_client:
        for profile, distance in rows:
            entry = {
                "user_id": profile.user_id,
                "similarity_score": round(max(0.0, 1.0 - distance), 4),
                "current_role": profile.current_role,
                "years_of_experience": profile.years_of_experience,
                "source_tag": profile.source_tag,
            }
            try:
                u_res = await http_client.get(
                    f"{USERS_API_URL.rstrip('/')}/{profile.user_id}", headers=headers_downstream
                )
                if u_res.status_code == 200:
                    u_data = u_res.json()
                    entry["full_name"] = u_data.get("full_name")
                    entry["email"] = u_data.get("email")
            except Exception as e:
                logger.warning(f"[MISSION-MATCH] Enrichissement user {profile.user_id} échoué: {e}")
            results.append(entry)

    if not results:
        raise HTTPException(status_code=404, detail=f"Aucun candidat trouvé pour la mission {mission_id}.")
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Sprint C1 — Analytics : couverture des compétences corpus
# ─────────────────────────────────────────────────────────────────────────────

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


@router.post("/recalculate_tree/batch/start", summary="Lance le processus batch asynchrone (Map)")
async def recalculate_tree_batch_start(request: Request, user: dict = Depends(verify_jwt)):
    auth_header = request.headers.get("Authorization")
    latest_status = await tree_task_manager.get_latest_status()
    if latest_status and latest_status.get("status") == "running" and latest_status.get("batch_job_id"):
        # Vérifier l'état réel sur Vertex AI pour éviter un Redis bloqué à 'running'
        # si le job est déjà terminé (SUCCEEDED/FAILED) côté GCP.
        job_id_check = latest_status.get("batch_job_id")
        try:
            live_job = await asyncio.to_thread(vertex_batch_client.batches.get, name=job_id_check)
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
        if not vertex_batch_client:
            raise ValueError("Vertex AI client non initialisé (GCP_PROJECT_ID ou VERTEX_LOCATION manquant).")
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
            vertex_batch_client.batches.create,
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
        batch_job = await asyncio.to_thread(vertex_batch_client.batches.get, name=batch_job_id)
        if batch_job.state.name != "JOB_STATE_SUCCEEDED":
            if batch_job.state.name == "JOB_STATE_FAILED":
                try:
                    await asyncio.to_thread(vertex_batch_client.batches.delete, name=batch_job_id)
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
                            await asyncio.to_thread(vertex_batch_client.batches.cancel, name=batch_job_id)
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
                        client,
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
                        
                    # Init GCS client avant usage
                    gcs_client_reduce = gcs_storage.Client()
                    ts_reduce = int(datetime.utcnow().timestamp())
                    blob_reduce_name = f"taxonomy/input/reduce-{ts_reduce}.jsonl"
                    reduce_bucket = gcs_client_reduce.bucket(BATCH_GCS_BUCKET)
                    blob_reduce = reduce_bucket.blob(blob_reduce_name)
                    blob_reduce.upload_from_filename(temp_path, content_type="application/jsonl")
                    src_reduce_uri = f"gs://{BATCH_GCS_BUCKET}/{blob_reduce_name}"
                    dest_reduce_uri = f"gs://{BATCH_GCS_BUCKET}/taxonomy/output/reduce-{ts_reduce}/"

                    reduce_batch_job = await asyncio.to_thread(
                        vertex_batch_client.batches.create,
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
                        client,
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
        all_batches = await asyncio.to_thread(lambda: list(vertex_batch_client.batches.list()))
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
        await asyncio.to_thread(vertex_batch_client.batches.delete, name=full_job_id)
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
            await asyncio.to_thread(vertex_batch_client.batches.cancel, name=latest_status.get("batch_job_id"))
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
        and vertex_batch_client
    ):
        try:
            job = await asyncio.to_thread(
                vertex_batch_client.batches.get,
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
    if current and current.get("batch_job_id") and vertex_batch_client:
        try:
            await asyncio.to_thread(
                vertex_batch_client.batches.cancel,
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


