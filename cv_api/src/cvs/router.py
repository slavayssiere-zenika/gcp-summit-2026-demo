from fastapi import APIRouter, Depends, HTTPException, Request, Response, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials
import json
import time
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
import httpx
import os
import re
import unicodedata
from typing import Any, Optional, List
from google import genai
from google.genai import types
from opentelemetry.propagate import inject
from jose import jwt as jose_jwt
from jose.exceptions import JWTError
import base64
import random
import string
import urllib.parse
import logging

from database import get_db
import database
from src.auth import verify_jwt, security, SECRET_KEY as _AUTH_SECRET_KEY
from src.cvs.models import CVProfile
from src.cvs.schemas import CVImportRequest, CVImportStep, CVResponse, SearchCandidateResponse, SearchCandidateRequest, CVProfileResponse, CVFullProfileResponse, UserMergeRequest, RankedExperienceResponse
from .task_state import task_state_manager, tree_task_manager
from metrics import CV_PROCESSING_TOTAL, CV_MISSING_EMBEDDINGS
from src.gemini_retry import generate_content_with_retry, embed_content_with_retry

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
MARKET_MCP_URL = os.getenv("MARKET_MCP_URL", "http://market_mcp:8008")

if not GEMINI_API_KEY:
    print("WARNING: GOOGLE_API_KEY is missing. RAG embeddings will fail.")
    client = None
else:
    client = genai.Client(api_key=GEMINI_API_KEY)

logger = logging.getLogger(__name__)

import asyncio
from datetime import datetime, timedelta

_COMP_CREATION_LOCK = asyncio.Lock()
_CV_CACHE = {
    "prompt": {"value": None, "expires": datetime.min},
    "tree_items": {"value": None, "expires": datetime.min},
    "tree_context": {"value": None, "expires": datetime.min}
}

async def _log_finops(user_email: str, action: str, model: str, usage_metadata: Any, metadata: dict = None, auth_token: str = None):
    """Utility to log consumption to BigQuery via Market MCP sidecar."""
    if not usage_metadata:
        return
    
    try:
        # Robust token extraction (handles objects or dicts)
        if hasattr(usage_metadata, 'prompt_token_count'):
            input_tokens = getattr(usage_metadata, 'prompt_token_count', 0)
        else:
            input_tokens = usage_metadata.get('prompt_token_count', 0) if isinstance(usage_metadata, dict) else 0

        if hasattr(usage_metadata, 'candidates_token_count'):
            output_tokens = getattr(usage_metadata, 'candidates_token_count', 0)
        else:
            output_tokens = usage_metadata.get('candidates_token_count', 0) if isinstance(usage_metadata, dict) else 0
        
        async with httpx.AsyncClient() as http_client:
            payload = {
                "name": "log_ai_consumption",
                "arguments": {
                    "user_email": user_email,
                    "action": action,
                    "model": model,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "metadata": metadata or {}
                }
            }
            # We don't want FinOps logging to block or fail the main request if Market is down
            try:
                headers = {}
                inject(headers)
                if auth_token:
                    headers["Authorization"] = f"Bearer {auth_token}"
                await http_client.post(f"{MARKET_MCP_URL.rstrip('/')}/mcp/call", json=payload, headers=headers, timeout=2.0)
            except Exception as ex:
                logger.warning(f"Market MCP unreachable for FinOps: {ex}")
    except Exception as e:
        logger.error(f"FinOps logging analysis failed: {e}")

async def _fetch_cv_content(url: str, google_token: Optional[str] = None) -> str:
    """Download the CV content. If Google Docs, map to raw export endpoint."""
    parsed = urllib.parse.urlparse(url)
    hostname = parsed.hostname or ""
    
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="Invalid URL scheme")
        
    forbidden_hosts = ["localhost", "127.0.0.1", "0.0.0.0"]
    if hostname in forbidden_hosts or hostname.endswith(".local") or hostname.endswith("_api"):
        raise HTTPException(status_code=400, detail="Internal URLs are not allowed")

    if "docs.google.com/document/d/" in url:
        # Map to export format if user pastes the browser URL
        doc_id = re.search(r"/d/([a-zA-Z0-9_-]+)", url)
        if doc_id:
            url = f"https://docs.google.com/document/d/{doc_id.group(1)}/export?format=txt"
    
    req_headers = {}
    if google_token:
        req_headers["Authorization"] = f"Bearer {google_token}"

    async with httpx.AsyncClient() as http_client:
        resp = await http_client.get(url, headers=req_headers, follow_redirects=True)
        if resp.status_code == 401 or resp.status_code == 403:
            raise HTTPException(status_code=400, detail="Accès refusé par Google Docs. Veuillez vérifier que le document est public ou autoriser l'accès.")
        resp.raise_for_status()
        return resp.text


@router.post("/import", response_model=CVResponse)
async def import_and_analyze_cv(req: CVImportRequest, request: Request, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db), token_payload: dict = Depends(verify_jwt)):
    # 1. Capture Authorization Context (Crucial per RULES[AGENTS.md])
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing Authorization via CV upload")
    
    headers = {"Authorization": auth_header}
    inject(headers)  # Mandatory Trace Span Propagation (Agent.md Rule 4)

    return await _process_cv_core(
        url=req.url,
        google_access_token=req.google_access_token,
        source_tag=req.source_tag,
        folder_name=req.folder_name,
        headers=headers,
        token_payload=token_payload,
        db=db,
        auth_token=auth_header.replace("Bearer ", "") if "Bearer " in auth_header else auth_header,
        background_tasks=background_tasks
    )


@public_router.post("/pubsub/import-cv")
async def handle_pubsub_cv_import(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Worker Pub/Sub push subscriber pour l'ingestion des CVs.

    Workflow :
    1. Validation OIDC du token Google (RS256) — vérifie que l'émetteur est bien le SA pubsub_invoker.
    2. Décodage base64 du payload Pub/Sub.
    3. Exécution SYNCHRONE du pipeline LLM + Compétences + Missions via _process_cv_core.
    4. Notification PATCH drive_api : IMPORTED_CV (succès) ou ERROR (échec).

    Sécurité : si le token OIDC est absent ou invalide → 401 (Pub/Sub va retenter).
    Idempotence : si le CV existe déjà (même email), mise à jour au lieu de création.
    """
    import base64
    from datetime import datetime
    from google.oauth2 import id_token as google_id_token
    from google.auth.transport import requests as google_requests

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
            audience = f"https://{request.headers.get('host', '')}{request.url.path}"
            decoded = google_id_token.verify_oauth2_token(
                oidc_token,
                google_requests.Request(),
                audience=audience
            )
            token_email = decoded.get("email", "")
            if token_email != invoker_sa_email:
                logger.warning(f"[PubSub] SA non autorisé: {token_email} (attendu: {invoker_sa_email})")
                raise HTTPException(status_code=401, detail="Unauthorized Pub/Sub invoker")
            logger.info(f"[PubSub] OIDC validé pour {token_email}")
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
    jwt = payload.get("jwt", "")

    if not url or not google_file_id:
        logger.error("[PubSub] Payload incomplet (url ou google_file_id manquant)")
        raise HTTPException(status_code=400, detail="Payload incomplet")

    headers = {"Authorization": f"Bearer {jwt}"}
    inject(headers)
    logger.info(f"[PubSub] Traitement de {google_file_id} ({url})")

    # ── 3. Mise à jour statut PROCESSING dans drive_api ─────────────────────
    drive_api_url = os.getenv("DRIVE_API_URL", "http://drive_api:8006")
    try:
        async with httpx.AsyncClient(timeout=10.0) as patch_client:
            await patch_client.patch(
                f"{drive_api_url.rstrip('/')}/files/{google_file_id}",
                json={"status": "PROCESSING"},
                headers=headers
            )
    except Exception as e:
        logger.warning(f"[PubSub] Impossible de notifier drive_api (PROCESSING): {e}")

    # ── 4. Décoder le JWT interne pour obtenir token_payload compatible ───────
    # Le JWT a été généré par drive_api (M2M token) et inclus dans le message Pub/Sub.
    # Il est nécessaire pour que _process_cv_core puisse appeler les services internes
    # (users_api, competencies_api, missions_api) avec une identité valide.
    # _AUTH_SECRET_KEY est la constante chargée au démarrage par src.auth (avant purge env)
    # On ne peut pas utiliser os.getenv("SECRET_KEY") ici car auth.py la purge de l'env
    # pour empêcher son extraction par un LLM (AGENTS.md §4 Rotation des secrets).
    if not _AUTH_SECRET_KEY:
        # Configuration cassée → 500 (Pub/Sub retentera, la DLQ capturera si persistant)
        logger.error("[PubSub] SECRET_KEY absente — impossible de valider le JWT interne.")
        raise HTTPException(status_code=500, detail="Configuration error: SECRET_KEY manquante")
    try:
        token_payload = jose_jwt.decode(jwt, _AUTH_SECRET_KEY, algorithms=["HS256"])
    except JWTError as e:
        # JWT corrompu ou expiré → 500 pour forcer le retry Pub/Sub avec un nouveau message
        logger.error(f"[PubSub] JWT interne invalide (corrompu ou expiré): {e}")
        raise HTTPException(status_code=500, detail=f"JWT interne invalide: {e}")

    # ── 5. Exécution du pipeline LLM synchrone ───────────────────────────────
    try:
        result = await _process_cv_core(
            url=url,
            google_access_token=google_access_token,
            source_tag=source_tag,
            folder_name=folder_name,
            headers=headers,
            token_payload=token_payload,
            db=db,
            auth_token=jwt,
            background_tasks=None  # BackgroundTasks désactivées en mode Pub/Sub : tout doit être synchrone
        )
        # ── 6. Notification succès → drive_api ──────────────────────────────
        try:
            async with httpx.AsyncClient(timeout=10.0) as patch_client:
                await patch_client.patch(
                    f"{drive_api_url.rstrip('/')}/files/{google_file_id}",
                    json={"status": "IMPORTED_CV", "user_id": result.user_id, "error_message": None},
                    headers=headers
                )
                logger.info(f"[PubSub] Import réussi pour {google_file_id} → user_id={result.user_id}")
        except Exception as e:
            logger.warning(f"[PubSub] Impossible de notifier drive_api (IMPORTED_CV): {e}")

        return {"status": "ok", "user_id": result.user_id}

    except HTTPException as he:
        error_detail = he.detail
        status = "IGNORED_NOT_CV" if ("Not a CV" in str(error_detail) or "LLM Parsing failed" in str(error_detail)) else "ERROR"
        logger.error(f"[PubSub] Échec pipeline pour {google_file_id}: {error_detail} → statut={status}")
        # Notification d'erreur → drive_api pour visibilité frontend
        try:
            async with httpx.AsyncClient(timeout=10.0) as patch_client:
                await patch_client.patch(
                    f"{drive_api_url.rstrip('/')}/files/{google_file_id}",
                    json={"status": status, "error_message": str(error_detail)},
                    headers=headers
                )
        except Exception as e:
            logger.warning(f"[PubSub] Impossible de notifier drive_api (ERROR): {e}")
        # Retourner 200 pour IGNORED_NOT_CV (ACK), 500 pour ERROR (retry Pub/Sub)
        if status == "IGNORED_NOT_CV":
            return {"status": "ignored", "detail": str(error_detail)}
        raise HTTPException(status_code=500, detail=str(error_detail))


async def _process_cv_core(url: str, google_access_token: Optional[str], source_tag: Optional[str], headers: dict, token_payload: dict, db: AsyncSession, auth_token: str = None, folder_name: Optional[str] = None, background_tasks: BackgroundTasks = None) -> CVResponse:
    """
    Pipeline principal d'ingéstion d'un CV en 8 étapes séquentielles.
    Retourne un CVResponse enrichi avec les étapes (steps) et les warnings non-bloquants.

    folder_name: nom du dossier Drive parent direct (ex: "Marie Dupont"), transmis par drive_api
    selon la nomenclature Zenika («Prénom Nom»). Fait foi pour la résolution d'identité si
    divergence avec l'analyse LLM.
    """
    pipeline_steps: List[CVImportStep] = []
    pipeline_warnings: List[str] = []

    def _step_ok(step: str, label: str, duration_ms: int, detail: str = None) -> CVImportStep:
        s = CVImportStep(step=step, label=label, status="success", duration_ms=duration_ms, detail=detail)
        pipeline_steps.append(s)
        logger.info(
            f"[CV_STEP] {label} — OK",
            extra={"step": step, "duration_ms": duration_ms, "cv_url": url, "detail": detail}
        )
        return s

    def _step_warn(step: str, label: str, duration_ms: int, detail: str = None) -> CVImportStep:
        s = CVImportStep(step=step, label=label, status="warning", duration_ms=duration_ms, detail=detail)
        pipeline_steps.append(s)
        pipeline_warnings.append(detail or label)
        logger.warning(
            f"[CV_STEP] {label} — WARN: {detail}",
            extra={"step": step, "duration_ms": duration_ms, "cv_url": url}
        )
        return s

    def _step_error(step: str, label: str, duration_ms: int, detail: str = None) -> CVImportStep:
        s = CVImportStep(step=step, label=label, status="error", duration_ms=duration_ms, detail=detail)
        pipeline_steps.append(s)
        logger.error(
            f"[CV_STEP] {label} — ERROR: {detail}",
            extra={"step": step, "duration_ms": duration_ms, "cv_url": url}
        )
        return s

    # ── Étape 1 : Téléchargement du document ─────────────────────────────────
    t0 = time.monotonic()
    try:
        logger.info(f"[CV_STEP] download — start", extra={"step": "download", "cv_url": url})
        raw_text = await _fetch_cv_content(url, google_access_token)
        dur = int((time.monotonic() - t0) * 1000)
        raw_len = len(raw_text)
        if raw_len > 100000:
            warn_msg = f"Document tronqué : {raw_len} caractères → limité à 100000 pour l'analyse IA"
            _step_warn("download", "Téléchargement du document", dur, warn_msg)
        else:
            _step_ok("download", "Téléchargement du document", dur, f"{raw_len} caractères")
    except HTTPException as he:
        dur = int((time.monotonic() - t0) * 1000)
        _step_error("download", "Téléchargement du document", dur, he.detail)
        logger.error(f"HTTPException while downloading CV: {he.detail}")
        raise
    except Exception as e:
        dur = int((time.monotonic() - t0) * 1000)
        _step_error("download", "Téléchargement du document", dur, str(e))
        logger.error(f"Failed downloading CV content: {e}", exc_info=True)
        CV_PROCESSING_TOTAL.labels(status="failure").inc()
        raise HTTPException(status_code=400, detail=f"Failed downloading CV content: {e}")

    if not client:
        logger.error("GenAI Client not configured.")
        raise HTTPException(status_code=500, detail="GenAI Client not configured.")

    # ── Étape 2 : Analyse IA — Extraction du profil ──────────────────────────
    t0 = time.monotonic()
    
    prompt = None
    if _CV_CACHE["prompt"]["expires"] > datetime.utcnow() and _CV_CACHE["prompt"]["value"]:
        logger.debug("[CV_STEP] llm_parse — fetching prompt from CACHE")
        prompt = _CV_CACHE["prompt"]["value"]
    else:
        try:
            logger.info("[CV_STEP] llm_parse — fetching prompt", extra={"step": "llm_parse", "cv_url": url})
            async with httpx.AsyncClient() as http_client:
                res_prompt = await http_client.get(f"{PROMPTS_API_URL.rstrip('/')}/cv_api.extract_cv_info", headers=headers, timeout=5.0)
                res_prompt.raise_for_status()
                prompt = res_prompt.json()["value"]
                _CV_CACHE["prompt"]["value"] = prompt
                _CV_CACHE["prompt"]["expires"] = datetime.utcnow() + timedelta(minutes=5)
        except Exception as e:
            logger.warning(f"Prompt cv_api.extract_cv_info indisponible (erreur: {e}). Fallback local.")
            if os.path.exists("cv_api.extract_cv_info.txt"):
                with open("cv_api.extract_cv_info.txt", "r", encoding="utf-8") as f:
                    prompt = f.read()
            else:
                logger.error("No fallback file cv_api.extract_cv_info.txt found.")
                raise HTTPException(status_code=500, detail=f"Cannot fetch generic prompt: {e}")

    tree_context = ""
    if _CV_CACHE["tree_context"]["expires"] > datetime.utcnow() and _CV_CACHE["tree_context"]["value"]:
        logger.debug("[CV_STEP] llm_parse — taxonomy context from CACHE")
        tree_context = _CV_CACHE["tree_context"]["value"]
    else:
        try:
            async with httpx.AsyncClient() as http_client:
                tree_res = await http_client.get(f"{COMPETENCIES_API_URL.rstrip('/')}/?limit=1000", headers=headers, timeout=2.0)
                if tree_res.status_code == 200:
                    items = tree_res.json().get('items', [])

                    def extract_mid_parents(nodes):
                        parents = []
                        for n in nodes:
                            subs = n.get("sub_competencies", [])
                            if subs:
                                has_leaf_child = any(not s.get("sub_competencies") for s in subs)
                                if has_leaf_child and n.get("parent_id") is not None and n.get("name"):
                                    parents.append(n.get("name"))
                                parents.extend(extract_mid_parents(subs))
                        return parents

                    parent_categories = extract_mid_parents(items)
                    tree_context = f"\n\nHere is the official list of parent capability domains for this company. Please try to map CV skills to these broad categories directly:\n{json.dumps(parent_categories)}"
                    logger.info(
                        f"[CV_STEP] llm_parse — taxonomy context injected",
                        extra={"step": "llm_parse", "categories_count": len(parent_categories), "cv_url": url}
                    )
                    _CV_CACHE["tree_context"]["value"] = tree_context
                    _CV_CACHE["tree_context"]["expires"] = datetime.utcnow() + timedelta(minutes=5)
                    _CV_CACHE["tree_items"]["value"] = items
                    _CV_CACHE["tree_items"]["expires"] = datetime.utcnow() + timedelta(minutes=5)
        except Exception as e:
            logger.warning(f"Failed to fetch competencies tree for context: {e}")

    final_prompt = prompt + tree_context

    try:
        response = await generate_content_with_retry(
            client,
            model=os.getenv("GEMINI_MODEL", "gemini-3-flash-preview"),
            contents=[final_prompt, f"RESUME:\n{raw_text[:100000]}"],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema={
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
                                    "aliases": {
                                        "type": "array",
                                        "items": {"type": "string"}
                                    }
                                },
                                "required": ["name"]
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
                                    "is_sensitive": {"type": "boolean", "description": "True if the project involves sensitive sectors like Defense, High Finance or confidential clients"},
                                    "competencies": {
                                        "type": "array",
                                        "items": {"type": "string"}
                                    }
                                },
                                "required": ["title", "competencies", "is_sensitive"]
                            }
                        },
                        "is_anonymous": {"type": "boolean"},
                        "trigram": {"type": "string"}
                    },
                    "required": ["is_cv", "first_name", "last_name", "email", "summary", "current_role", "years_of_experience", "competencies", "missions", "is_anonymous"]
                }
            )
        )
        parsed_data = response.text
        structured_cv = json.loads(parsed_data)

        # FinOps
        user_caller = token_payload.get("sub", "unknown")
        safe_meta = None
        try:
            safe_meta = response.usage_metadata
        except Exception as e:
            logger.warning(f"Metadata access failed for analyze_cv: {e}")
        await _log_finops(user_caller, "analyze_cv", os.getenv("GEMINI_MODEL", "gemini-3-flash-preview"), safe_meta, {"cv_url": url}, auth_token=auth_token)

        if not structured_cv.get("is_cv", False):
            dur = int((time.monotonic() - t0) * 1000)
            _step_error("llm_parse", "Analyse IA — Extraction du profil", dur, "Document non reconnu comme un CV")
            logger.warning("Document is not recognized as a CV")
            raise HTTPException(status_code=400, detail="Not a CV: The document does not appear to be a resume.")

        # Vérifications qualité IA
        nb_competencies = len(structured_cv.get("competencies", []))
        nb_missions = len(structured_cv.get("missions", []))
        summary_val = structured_cv.get("summary", "")
        dur = int((time.monotonic() - t0) * 1000)

        llm_detail = f"{nb_competencies} compétences, {nb_missions} missions détectées"
        input_tokens = getattr(safe_meta, 'prompt_token_count', None) if safe_meta else None
        if input_tokens:
            llm_detail += f", {input_tokens} tokens en entrée"

        if nb_competencies == 0:
            warn_cv = "Aucune compétence extraite par l'IA — vérifiez la qualité du document"
            _step_warn("llm_parse", "Analyse IA — Extraction du profil", dur, llm_detail)
            pipeline_warnings.append(warn_cv)
            logger.warning(f"[CV_STEP] llm_parse — zero competencies extracted", extra={"cv_url": url})
        elif not summary_val or summary_val.strip() == "":
            warn_cv = "Résumé de profil vide — l'IA n'a pas pu générer de synthèse"
            _step_warn("llm_parse", "Analyse IA — Extraction du profil", dur, llm_detail)
            pipeline_warnings.append(warn_cv)
        else:
            _step_ok("llm_parse", "Analyse IA — Extraction du profil", dur, llm_detail)

    except HTTPException:
        raise
    except Exception as e:
        dur = int((time.monotonic() - t0) * 1000)
        _step_error("llm_parse", "Analyse IA — Extraction du profil", dur, str(e))
        logger.error(f"LLM Parsing failed: {e}", exc_info=True)
        CV_PROCESSING_TOTAL.labels(status="failure").inc()
        raise HTTPException(status_code=500, detail=f"LLM Parsing failed: {e}")

    # ── Étape 3 : Résolution d'identité ──────────────────────────────────────
    t0 = time.monotonic()

    def sanitize_field(val: Any) -> Optional[str]:
        if val is None: return None
        s = str(val).strip()
        if s.lower() in ("null", "none", "", "unknown"): return None
        return s

    def normalize_str(s: str) -> str:
        if not s: return ""
        return unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('utf-8').lower()

    NAME_REGEX = r"^[A-Za-zÀ-ÿ\s\-\']+$"

    def is_valid_name(n: Optional[str]) -> bool:
        return bool(n and re.match(NAME_REGEX, n))

    EMAIL_REGEX = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
    def is_valid_email(e: Optional[str]) -> bool:
        return bool(e and re.match(EMAIL_REGEX, e))

    raw_email = sanitize_field(structured_cv.get("email"))
    llm_first_name = sanitize_field(structured_cv.get("first_name"))
    llm_last_name = sanitize_field(structured_cv.get("last_name"))
    is_anonymous = structured_cv.get("is_anonymous", False)
    trigram = sanitize_field(structured_cv.get("trigram"))

    # STAFF-SEC : Valider les noms LLM (rejet si format invalide — anti hallucination)
    if llm_first_name and not is_valid_name(llm_first_name):
        logger.warning(f"Invalid first_name format rejected from LLM: {llm_first_name}")
        llm_first_name = None
    if llm_last_name and not is_valid_name(llm_last_name):
        logger.warning(f"Invalid last_name format rejected from LLM: {llm_last_name}")
        llm_last_name = None

    # ── Résolution prioritaire via folder_name (nomenclature Zenika "Prénom Nom") ──
    # Le folder_name transmis par drive_api fait foi.
    folder_first_name: Optional[str] = None
    folder_last_name: Optional[str] = None

    if folder_name and folder_name.strip():
        parts = folder_name.strip().split(None, 1)  # Split sur le premier espace
        if len(parts) == 2:
            folder_first_name = sanitize_field(parts[0])
            folder_last_name = sanitize_field(parts[1])
            if not is_valid_name(folder_first_name):
                folder_first_name = None
            if not is_valid_name(folder_last_name):
                folder_last_name = None
            logger.info(
                f"[folder_name] Nomenclature Zenika détectée : "
                f"'{folder_first_name}' '{folder_last_name}' (depuis '{folder_name}')"
            )
        elif len(parts) == 1:
            # Dossier avec un seul mot (ex: trigramme ou alias) — ignorer pour identité
            logger.info(f"[folder_name] Nom de dossier mono-composant '{folder_name}' — ignoré pour résolution identité.")

    # Détection de divergence LLM vs folder_name (folder fait foi)
    first_name = folder_first_name or llm_first_name
    last_name = folder_last_name or llm_last_name

    if folder_first_name and folder_last_name:
        if llm_first_name and llm_last_name:
            fn_match = normalize_str(folder_first_name) == normalize_str(llm_first_name)
            ln_match = normalize_str(folder_last_name) == normalize_str(llm_last_name)
            if not (fn_match and ln_match):
                warn_folder = (
                    f"⚠️ Divergence d'identité — Dossier Drive : '{folder_first_name} {folder_last_name}' "
                    f"/ LLM : '{llm_first_name} {llm_last_name}'. "
                    f"Le nom du dossier fait foi."
                )
                logger.warning(warn_folder)
                # Warning visible dans l'UI de synchronisation ET de resynchronisation
                _step_warn(
                    "folder_identity",
                    "Résolution identité — Divergence dossier vs LLM",
                    0,
                    warn_folder
                )
                pipeline_warnings.append(warn_folder)
                # Le folder_name fait foi → on utilise folder_first/last_name
                first_name = folder_first_name
                last_name = folder_last_name

    if not is_valid_name(first_name):
        first_name = None
    if not is_valid_name(last_name):
        last_name = None

    if not is_valid_email(raw_email):
        if first_name and last_name:
            clean_f = normalize_str(first_name).replace(" ", "")
            clean_l = normalize_str(last_name).replace(" ", "")
            email = f"{clean_f}.{clean_l}@zenika.com"
            logger.info(f"Email absent/invalide dans le CV. Généré : {email}")
            pipeline_warnings.append(f"Email absent ou invalide dans le CV — email généré : {email}")
        else:
            is_anonymous = True
            trigram = trigram or ''.join(random.choices(string.ascii_uppercase, k=3))
            first_name = "Anon"
            last_name = trigram
            email = f"anon.{trigram.lower()}@anonymous.zenika.com"
            logger.warning(f"Identité totalement absente. Profil anonymisé : {email}")
            pipeline_warnings.append("Identité introuvable dans le CV — profil anonymisé automatiquement")
    else:
        email = raw_email

    ext_full_norm = f"{normalize_str(first_name)} {normalize_str(last_name)}"

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        user_id = None
        importer_id = None

        # Recherche prioritaire par folder_name (nomenclature Zenika) si disponible
        if folder_first_name and folder_last_name:
            folder_search_q = f"{folder_first_name} {folder_last_name}"
            logger.info(f"[folder_name] Recherche utilisateur prioritaire par dossier : '{folder_search_q}'")
            fn_res = await http_client.get(
                f"{USERS_API_URL.rstrip('/')}/search",
                params={"query": folder_search_q, "limit": 10},
                headers=headers
            )
            if fn_res.status_code == 200:
                for u in fn_res.json().get("items", []):
                    if (
                        normalize_str(u.get("first_name")) == normalize_str(folder_first_name)
                        and normalize_str(u.get("last_name")) == normalize_str(folder_last_name)
                    ):
                        user_id = u["id"]
                        logger.info(
                            f"[folder_name] Utilisateur trouvé par dossier Drive : "
                            f"'{folder_search_q}' → ID {user_id}"
                        )
                        break

        # Fallback : recherche par email (si pas trouvé par folder_name)
        if not user_id and email:
            search_res = await http_client.get(
                f"{USERS_API_URL.rstrip('/')}/search",
                params={"query": email, "limit": 10},
                headers=headers
            )
            if search_res.status_code == 200:
                for u in search_res.json().get("items", []):
                    if u.get("email", "").lower() == email.lower():
                        u_full_norm = normalize_str(
                            u.get("full_name") or f"{u.get('first_name')} {u.get('last_name')}"
                        )
                        if ext_full_norm and ext_full_norm.strip():
                            if ext_full_norm not in u_full_norm and u_full_norm not in ext_full_norm:
                                logger.warning(
                                    f"Email {email} trouvé mais nom divergent : "
                                    f"extrait='{ext_full_norm}' / système='{u_full_norm}'. Détachement."
                                )
                                continue
                        user_id = u["id"]
                        logger.info(f"Utilisateur trouvé par email : {email} → ID {user_id}")
                        break

        # Fallback sémantique par nom LLM (si ni folder_name ni email n'ont matchés)
        if not user_id and first_name and last_name:
            logger.info(
                f"Identité non trouvée. Fallback sémantique LLM : '{first_name} {last_name}'."
            )
            search_q = f"{first_name} {last_name}"
            name_res = await http_client.get(
                f"{USERS_API_URL.rstrip('/')}/search",
                params={"query": search_q, "limit": 10},
                headers=headers
            )
            if name_res.status_code == 200:
                for u in name_res.json().get("items", []):
                    if (
                        normalize_str(u.get("first_name")) == normalize_str(first_name)
                        and normalize_str(u.get("last_name")) == normalize_str(last_name)
                    ):
                        user_id = u["id"]
                        logger.info(f"Utilisateur trouvé par nom sémantique → ID {user_id}")
                        break

        importer_username = token_payload.get("sub")
        if importer_username:
            importer_res = await http_client.get(
                f"{USERS_API_URL.rstrip('/')}/search",
                params={"query": importer_username, "limit": 10},
                headers=headers
            )
            if importer_res.status_code == 200:
                for u in importer_res.json().get("items", []):
                    if u.get("username", "").lower() == importer_username.lower():
                        importer_id = u["id"]
                        break

        filename = os.path.basename(url).lower()
        if not is_anonymous:
            if "annonym" in filename or "anon" in filename or "abc" in filename:
                logger.info("Anonymité détectée d'après le nom du fichier.")
                is_anonymous = True
                if first_name != "Anon":
                    trigram = trigram or ''.join(random.choices(string.ascii_uppercase, k=3))
                    first_name = "Anon"
                    last_name = trigram
                    email = f"anon.{trigram.lower()}@anonymous.zenika.com"

        extracted_info = {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "is_anonymous": is_anonymous,
            "folder_name": folder_name,
        }

        if user_id and is_anonymous:
            user_info_res = await http_client.get(
                f"{USERS_API_URL.rstrip('/')}/{user_id}", headers=headers
            )
            if user_info_res.status_code == 200:
                user_data = user_info_res.json()
                if not user_data.get("is_anonymous", False):
                    warn_msg = f"🛡️ CV anonyme détecté sur un compte réel (User {user_id}). DÉTACHEMENT du profil."
                    logger.info(warn_msg)
                    await task_state_manager.update_progress(new_log=warn_msg)
                    user_id = None
                else:
                    logger.info(f"CV anonyme sur User déjà anonyme {user_id}. Maintenu.")

        if not user_id:
            logger.info(f"Utilisateur non trouvé — création {'anonyme ' if is_anonymous else ''}...")
            new_u = {
                "username": f"{first_name[0].lower()}{last_name.lower()}{random.randint(100, 999)}",
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
                "full_name": f"{first_name} {last_name}",
                "password": "zenikacv123",
                "is_anonymous": is_anonymous
            }
            create_res = await http_client.post(
                f"{USERS_API_URL.rstrip('/')}/", json=new_u, headers=headers
            )

            if create_res.status_code == 409 or (
                create_res.status_code >= 400 and "already exists" in create_res.text.lower()
            ):
                host = email.split('@')[1] if '@' in email else "zenika.com"
                prefix = email.split('@')[0] if '@' in email else "conflict"
                conflict_email = f"{prefix}.conflict.{random.randint(1000, 9999)}@{host}"
                logger.warning(f"Conflit email {email}. Détachement vers {conflict_email}")
                pipeline_warnings.append(f"Conflit d'email ({email}) — identité détachée vers {conflict_email}")
                new_u["email"] = conflict_email
                create_res = await http_client.post(
                    f"{USERS_API_URL.rstrip('/')}/", json=new_u, headers=headers
                )

            if create_res.status_code >= 400:
                dur = int((time.monotonic() - t0) * 1000)
                err_detail = f"Création utilisateur échouée (HTTP {create_res.status_code})"
                _step_error("user_resolve", "Résolution & création d'identité", dur, err_detail)
                logger.error(f"User creation failed: status={create_res.status_code}, detail={create_res.text}")
                raise HTTPException(status_code=500, detail=f"User creation failed: {create_res.text}")

            user_id = create_res.json()["id"]
            logger.info(f"[user_resolve] Utilisateur créé avec ID {user_id}")
        dur = int((time.monotonic() - t0) * 1000)
        _step_ok("user_resolve", "Résolution & création d'identité", dur, f"User ID {user_id}")
        # ── Étape 4 & 5 : Traitement asynchrone (Background Task) ─────────────────
        # On délègue la création des compétences et des missions pour ne pas bloquer 
        # le timeout de la réponse HTTP vers `drive_api`.
        async def _bg_process_competencies_and_missions(bg_user_id, bg_structured_cv, bg_headers, bg_url):
            logger.info(f"[BG_TASK] Démarrage traitement asynchrone pour CV {bg_url}")
            bg_errors = []
            async with httpx.AsyncClient(timeout=120.0) as bg_http_client:
                # ── Étape 4 : Mapping des compétences ─────────────────────────────────
                try:
                    comp_res = await bg_http_client.get(f"{COMPETENCIES_API_URL.rstrip('/')}/?limit=1000", headers=bg_headers)
                    comp_data = comp_res.json()
                    all_comps = comp_data.get("items", []) if isinstance(comp_data, dict) else comp_data

                    def normalize_comp(text):
                        if not text: return ""
                        text = text.strip().lower()
                        return "".join(c for c in unicodedata.normalize('NFKD', text) if unicodedata.category(c) != 'Mn')

                    def find_comp_id(node_list, t_name):
                        t_norm = normalize_comp(t_name)
                        for n in node_list:
                            if normalize_comp(n['name']) == t_norm: return n['id']
                            found = find_comp_id(n.get('sub_competencies', []), t_name)
                            if found: return found
                        return None

                    async def process_competency(comp):
                        name = comp["name"]
                        parent = comp.get("parent")
                        try:
                            c_id = find_comp_id(all_comps, name)
                            if not c_id:
                                p_id = None
                                if parent:
                                    async with _COMP_CREATION_LOCK:
                                        p_id = find_comp_id(all_comps, parent)
                                        if not p_id:
                                            p_res = await bg_http_client.post(f"{COMPETENCIES_API_URL.rstrip('/')}/", json={"name": parent, "description": "Auto-identified from CV"}, headers=bg_headers)
                                            if p_res.status_code < 400:
                                                p_id = p_res.json()["id"]
                                                all_comps.append(p_res.json())

                                aliases_str = ", ".join(comp.get("aliases", [])) if comp.get("aliases") else None
                                leaf_data = {"name": name, "description": "Candidate CV Skill", "aliases": aliases_str}
                                if p_id: leaf_data["parent_id"] = p_id

                                async with _COMP_CREATION_LOCK:
                                    c_id = find_comp_id(all_comps, name)
                                    if not c_id:
                                        c_res = await bg_http_client.post(f"{COMPETENCIES_API_URL.rstrip('/')}/", json=leaf_data, headers=bg_headers)
                                        if c_res.status_code < 400:
                                            c_id = c_res.json()["id"]
                                            all_comps.append(c_res.json())

                            if c_id:
                                assign_res = await bg_http_client.post(f"{COMPETENCIES_API_URL.rstrip('/')}/user/{bg_user_id}/assign/{c_id}", headers=bg_headers)
                                if assign_res.status_code < 400:
                                    return True
                                return f"Échec d'assignation de '{name}' (HTTP {assign_res.status_code}: {assign_res.text})"
                        except Exception as e:
                            logger.warning(f"[BG_TASK] failed to assign '{name}': {e}", extra={"cv_url": bg_url})
                            return f"Erreur inattendue sur '{name}': {e}"
                        return f"Impossible de résoudre ou de créer la compétence '{name}'"

                    comp_tasks = [process_competency(c) for c in bg_structured_cv.get("competencies", [])]
                    comp_results = await asyncio.gather(*comp_tasks, return_exceptions=True)
                    for res in comp_results:
                        if res is not True:
                            if isinstance(res, str):
                                bg_errors.append(res)
                            elif isinstance(res, Exception):
                                bg_errors.append(f"Exception asynchrone (compétence): {res}")
                            else:
                                bg_errors.append("Erreur inconnue lors d'une assignation de compétence.")
                except Exception as e:
                    logger.error(f"[BG_TASK] Erreur critique compétences: {e}")
                    bg_errors.append(f"Crash module compétences: {e}")

                # ── Étape 5 : Extraction des missions ─────────────────────────────────
                try:
                    missions_list = bg_structured_cv.get("missions", [])
                    cat_res = await bg_http_client.get(f"{ITEMS_API_URL.rstrip('/')}/categories", headers=bg_headers)
                    categories = cat_res.json() if cat_res.status_code == 200 else []

                    def find_cat_id(name):
                        for c in categories:
                            if c["name"].lower() == name.lower(): return c["id"]
                        return None

                    mission_cat_id = find_cat_id("Missions")
                    if not mission_cat_id:
                        m_res = await bg_http_client.post(f"{ITEMS_API_URL.rstrip('/')}/categories", json={"name": "Missions", "description": "Professional experiences extracted from CVs"}, headers=bg_headers)
                        if m_res.status_code < 400: mission_cat_id = m_res.json()["id"]

                    sensitive_cat_id = find_cat_id("Restricted")
                    if not sensitive_cat_id:
                        s_res = await bg_http_client.post(f"{ITEMS_API_URL.rstrip('/')}/categories", json={"name": "Restricted", "description": "Sensitive or confidential missions"}, headers=bg_headers)
                        if s_res.status_code < 400: sensitive_cat_id = s_res.json()["id"]
                    
                    async def process_mission(m):
                        try:
                            cat_ids = [mission_cat_id] if mission_cat_id else []
                            if m.get("is_sensitive") and sensitive_cat_id:
                                cat_ids.append(sensitive_cat_id)

                            item_data = {
                                "name": m["title"],
                                "description": m.get("description", ""),
                                "user_id": bg_user_id,
                                "category_ids": cat_ids,
                                "metadata_json": {
                                    "company": m.get("company"),
                                    "competencies": m.get("competencies", []),
                                    "is_sensitive": m.get("is_sensitive", False),
                                    "source": "CV Analysis"
                                }
                            }
                            m_post = await bg_http_client.post(f"{ITEMS_API_URL.rstrip('/')}/", json=item_data, headers=bg_headers)
                            if m_post.status_code >= 400:
                                logger.warning(f"[BG_TASK] missions — failed to create item '{m['title']}': HTTP {m_post.status_code}")
                                return f"Création de la mission '{m['title']}' échouée (HTTP {m_post.status_code}: {m_post.text})"
                            return True
                        except Exception as e:
                            return f"Erreur sur la mission '{m.get('title', 'Inconnue')}': {e}"

                    mission_tasks = [process_mission(m) for m in missions_list]
                    mission_results = await asyncio.gather(*mission_tasks, return_exceptions=True)
                    for res in mission_results:
                        if res is not True:
                            if isinstance(res, str):
                                bg_errors.append(res)
                            elif isinstance(res, Exception):
                                bg_errors.append(f"Exception asynchrone (mission): {res}")
                            else:
                                bg_errors.append("Erreur inconnue lors d'une création de mission.")
                except Exception as e:
                    logger.error(f"[BG_TASK] Erreur critique missions: {e}")
                    bg_errors.append(f"Crash module missions: {e}")
            
            if bg_errors:
                try:
                    import re, os
                    drive_api_url = os.getenv("DRIVE_API_URL", "http://drive_api:8006")
                    doc_id_match = re.search(r"/d/([a-zA-Z0-9_-]+)", bg_url)
                    if doc_id_match:
                        doc_id = doc_id_match.group(1)
                        # Remove duplicates in errors for concise message
                        unique_errors = list(dict.fromkeys(bg_errors))
                        err_str = " | ".join(unique_errors)
                        logger.warning(f"[BG_TASK] Notification webhook d'erreur drive_api pour {doc_id}: {err_str}")
                        async with httpx.AsyncClient(timeout=10.0) as webhook_client:
                            await webhook_client.patch(
                                f"{drive_api_url.rstrip('/')}/files/{doc_id}",
                                json={"status": "ERROR", "error_message": err_str},
                                headers=bg_headers
                            )
                except Exception as patch_e:
                    logger.error(f"[BG_TASK] Impossible d'alerter drive_api: {patch_e}")

            logger.info(f"[BG_TASK] Fin traitement asynchrone pour CV {bg_url}")

        if background_tasks:
            background_tasks.add_task(_bg_process_competencies_and_missions, user_id, structured_cv, headers, url)
            _step_ok("competencies_missions", "Mapping RAG et Extraction", 0, "Délégué en Background Task (Asynchrone)")
            assigned_count = 0  # Sera calculé en arrière-plan
        else:
            # Fallback synchrone classique si appelé sans BackgroundTasks
            await _bg_process_competencies_and_missions(user_id, structured_cv, headers, url)
            assigned_count = 0
            
    # hors du bloc httpx
    # ── Étape 6 : Génération des embeddings vectoriels ────────────────────────
    t0 = time.monotonic()
    comp_keywords = [c.get("name") for c in structured_cv.get("competencies", []) if c.get("name")]

    distilled_content = (
        f"Role: {structured_cv.get('current_role', 'Unknown')}\n"
        f"Experience: {structured_cv.get('years_of_experience', 0)} years\n"
        f"Summary: {structured_cv.get('summary', '')}\n"
        f"Competencies: {', '.join(comp_keywords)}\n\n"
        f"--- RAW CV CONTENT ---\n"
        f"{raw_text[:6000]}"
    )

    vector_data = None
    try:
        emb_res = await embed_content_with_retry(
            client,
            model=os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"),
            contents=distilled_content
        )
        vector_data = emb_res.embeddings[0].values
        dur = int((time.monotonic() - t0) * 1000)
        _step_ok("embedding", "Génération des embeddings vectoriels", dur, f"{len(vector_data)} dimensions")
    except Exception as e:
        dur = int((time.monotonic() - t0) * 1000)
        _step_warn("embedding", "Génération des embeddings vectoriels", dur, f"Embedding échoué : {e} — profil non recherchable")
        pipeline_warnings.append("Embedding vectoriel échoué — ce profil ne sera pas retrouvable par recherche sémantique")
        logger.error(f"Embedding failed: {e}", exc_info=True)

    # ── Étape 7 : Sauvegarde en base de données ───────────────────────────────
    t0 = time.monotonic()
    try:
        from sqlalchemy import delete
        await db.execute(delete(CVProfile).where(CVProfile.source_url == url))

        cv_record = CVProfile(
            user_id=user_id,
            source_url=url,
            source_tag=source_tag,
            extracted_competencies=structured_cv.get("competencies", []),
            current_role=structured_cv.get("current_role"),
            years_of_experience=structured_cv.get("years_of_experience"),
            summary=structured_cv.get("summary"),
            competencies_keywords=comp_keywords,
            missions=structured_cv.get("missions", []),
            raw_content=raw_text,
            semantic_embedding=vector_data,
            imported_by_id=importer_id
        )
        db.add(cv_record)
        await db.commit()
        dur = int((time.monotonic() - t0) * 1000)
        _step_ok("db_save", "Sauvegarde en base de données", dur, f"CV ID utilisateur {user_id}")
    except Exception as e:
        dur = int((time.monotonic() - t0) * 1000)
        _step_error("db_save", "Sauvegarde en base de données", dur, str(e))
        logger.error(f"DB save failed: {e}", exc_info=True)
        CV_PROCESSING_TOTAL.labels(status="failure").inc()
        raise HTTPException(status_code=500, detail=f"Database save failed: {e}")

    logger.info(
        f"[CV_STEP] pipeline_complete — success",
        extra={
            "step": "pipeline_complete",
            "cv_url": url,
            "user_id": user_id,
            "competencies_assigned": assigned_count,
            "warnings_count": len(pipeline_warnings),
            "steps_count": len(pipeline_steps)
        }
    )
    CV_PROCESSING_TOTAL.labels(status="success").inc()

    # ── Hook : Scoring IA automatique des compétences (BackgroundTask) ─────────
    # Déclenché à chaque import/réanalyse CV pour recalculer les notes IA.
    if user_id:
        try:
            async with httpx.AsyncClient(timeout=5.0) as _bg_client:
                _bg_headers = dict(headers)
                inject(_bg_headers)
                await _bg_client.post(
                    f"{COMPETENCIES_API_URL.rstrip('/')}/evaluations/user/{user_id}/ai-score-all",
                    headers=_bg_headers,
                    timeout=5.0
                )
            logger.info(f"[CV_STEP] ai_scoring_triggered — user_id={user_id}")
        except Exception as _e:
            logger.warning(f"[CV_STEP] ai_scoring_trigger_failed — {_e} (non-bloquant)")

    return CVResponse(
        message=f"Success! Processed '{structured_cv['first_name']}' and mapped {assigned_count} RAG competencies.",
        user_id=user_id,
        competencies_assigned=assigned_count,
        extracted_info=extracted_info,
        steps=pipeline_steps,
        warnings=pipeline_warnings
    )

async def _execute_search(
    request: Request,
    response: Response,
    query: str, 
    limit: int, 
    skills: List[str],
    db: AsyncSession,
    token_payload: dict,
    credentials: HTTPAuthorizationCredentials
):
    """
    Recherche sémantique (RAG) du meilleur candidat via pgvector cosine distance.
    L'agent interroge cette route lorsqu'il cherche des consultants par mots-clés ou description de projet.
    """
    if not client:
        raise HTTPException(status_code=500, detail="GenAI Client not configured.")
        
    # 0. Pre-filtrage AI (uniquement si non fourni par l'API appelante): Extract mandatory skills from query
    filter_res = None
    if skills is not None and len(skills) > 0:
        required_skills = skills
    else:
        try:
            filter_prompt = f"Extract a JSON list of strictly required technical competencies from this search query. Return ONLY a JSON array of strings (e.g. ['Python', 'AWS']), or an empty array if none are strictly required.\nQuery: '{query}'"
            filter_res = await generate_content_with_retry(
                client,
                model=os.getenv("GEMINI_MODEL", "gemini-3-flash-preview"),
                contents=filter_prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            required_skills = json.loads(filter_res.text)
            if not isinstance(required_skills, list):
                required_skills = []
        except Exception as e:
            logger.warning(f"Skill extraction failed, proceeding without pre-filter: {e}")
            required_skills = []

    try:
        # 1. Convert Prompt Query into 3072-D Matrix
        safe_embed_query = query[:3000] if query and len(query) > 3000 else query
        emb_res = await embed_content_with_retry(
            client,
            model=os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"),
            contents=safe_embed_query
        )
        search_vector = emb_res.embeddings[0].values
        
        # FinOps Logging (Filter + Embedding) - Safe access to metadata
        user_caller = token_payload.get("sub", "unknown")
        
        # Log generation tokens from filter (Safely)
        f_meta = None
        try:
            if filter_res:
                f_meta = filter_res.usage_metadata
        except Exception as e:
            logger.warning(f"Metadata access failed for search filter: {e}")
        if filter_res:
            await _log_finops(user_caller, "search_filter_extraction", os.getenv("GEMINI_MODEL", "gemini-3-flash-preview"), f_meta, {"query": query}, auth_token=credentials.credentials)
        
        # Log embedding (rough estimate)
        # We use a simple dict to avoid Pydantic validation issues with the official UsageMetadata type
        await _log_finops(user_caller, "search_embedding", os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"), {"prompt_token_count": len(query)//4, "candidates_token_count": 0}, auth_token=credentials.credentials)
    except Exception as e:
        logger.error(f"Erreur d'embedding API Gemini (query length={len(query)}): {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Embedding search query failed: {e}")

    # 2. Vector Postgres Search Operator (Cosine Distance <=>)
    stmt = select(
        CVProfile, 
        CVProfile.semantic_embedding.cosine_distance(search_vector).label('distance')
    ).filter(CVProfile.semantic_embedding.is_not(None))
    
    # Check missing embeddings anomaly
    try:
        missing_count_stmt = select(func.count(CVProfile.user_id)).filter(CVProfile.semantic_embedding.is_(None))
        missing_count = (await db.execute(missing_count_stmt)).scalar() or 0
        CV_MISSING_EMBEDDINGS.set(missing_count)
        
        if missing_count > 0:
            logger.warning(f"Data Anomaly: {missing_count} CV profiles ignored due to missing embeddings!")
            if response:
                response.headers["X-Missing-Embeddings-Count"] = str(missing_count)
    except Exception as e:
        logger.error(f"Failed to calculate missing embeddings: {e}")
    
    fallback_scan = False
    
    if required_skills:
        approved_user_ids = set()
        auth_header = f"Bearer {credentials.credentials}" if credentials else ""
        headers_downstream = {"Authorization": auth_header} if auth_header else {}
        
        try:
            async with httpx.AsyncClient() as http_client:
                for skill in required_skills:
                    # 1. Search for this skill canonically
                    search_res = await http_client.get(
                        f"{COMPETENCIES_API_URL.rstrip('/')}/search", 
                        params={"query": skill, "limit": 1}, 
                        headers=headers_downstream
                    )
                    
                    if search_res.status_code == 200:
                        items = search_res.json().get("items", [])
                        if items:
                            canonical_id = items[0]["id"]
                            # 2. Get users holding this skill OR any sub-skill
                            users_res = await http_client.get(
                                f"{COMPETENCIES_API_URL.rstrip('/')}/{canonical_id}/users",
                                headers=headers_downstream
                            )
                            if users_res.status_code == 200:
                                user_ids = users_res.json()
                                approved_user_ids.update(user_ids)
        except Exception as e:
            logger.warning(f"Canonical competencies resolution failed: {e}")
            
        if approved_user_ids:
            stmt_filtered = stmt.filter(CVProfile.user_id.in_(list(approved_user_ids)))
            query_results = (await db.execute(stmt_filtered.order_by('distance').limit(limit * 2))).all()
            if not query_results:
                fallback_scan = True
                query_results = (await db.execute(stmt.order_by('distance').limit(limit * 2))).all()
        else:
            fallback_scan = True
            query_results = (await db.execute(stmt.order_by('distance').limit(limit * 2))).all()
    else:
        query_results = (await db.execute(stmt.order_by('distance').limit(limit * 2))).all()

    if response:
        response.headers["X-Fallback-Full-Scan"] = str(fallback_scan).lower()
                
    mapped_results = []
    seen_users = set()
    
    for row, distance in query_results:
        if row.user_id not in seen_users:
            seen_users.add(row.user_id)
            score = 1.0 - (distance if distance is not None else 0.0)
            mapped_results.append({
                "user_id": row.user_id,
                "similarity_score": round(score, 4)
            })
            if len(mapped_results) >= limit:
                break

    # 3. Enrich Candidates with Users API properties (Composition Pattern)
    auth_header = request.headers.get("Authorization") if request else None
    headers_downstream = {"Authorization": auth_header} if auth_header else {}
    inject(headers_downstream)  # Mandatory Trace Span Propagation (Agent.md Rule 4)
    
    async with httpx.AsyncClient(timeout=10.0) as http_client:
        async def fetch_user(res):
            try:
                u_res = await http_client.get(f"{USERS_API_URL.rstrip('/')}/{res['user_id']}", headers=headers_downstream)
                if u_res.status_code == 200:
                    u_data = u_res.json()
                    res["full_name"] = u_data.get("full_name")
                    res["email"] = u_data.get("email")
                    res["username"] = u_data.get("username")
                    res["is_active"] = u_data.get("is_active")
                    res["is_anonymous"] = u_data.get("is_anonymous", False)
            except Exception as e:
                print(f"HTTP Enrichment failed for user {res['user_id']}: {e}")

        # Run all users_api fetches concurrently
        import asyncio
        await asyncio.gather(*(fetch_user(res) for res in mapped_results))
    
    if not mapped_results:
        raise HTTPException(
            status_code=404, 
            detail="Aucun collaborateur correspondant à ces critères (compétences/expérience) n'a été trouvé dans la base de CVs Zenika."
        )

    return mapped_results

@router.get("/search", response_model=List[SearchCandidateResponse])
async def search_candidates(
    request: Request,
    response: Response,
    query: str, 
    limit: int = 5, 
    skills: List[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    token_payload: dict = Depends(verify_jwt),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    return await _execute_search(request, response, query, limit, skills, db, token_payload, credentials)

@router.post("/search", response_model=List[SearchCandidateResponse])
async def search_candidates_post(
    req_body: SearchCandidateRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    token_payload: dict = Depends(verify_jwt),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    return await _execute_search(request, response, req_body.query, req_body.limit, req_body.skills, db, token_payload, credentials)

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
        except: pass

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
    profiles = (await db.execute(select(CVProfile.user_id, CVProfile.source_tag).filter(CVProfile.source_tag.is_not(None)))).all()
    # On renvoie le tag sous la forme du tag le plus récent si multiples (ici l'ordre n'est pas garanti mais en prod on a 1 CV/user)
    return {str(p.user_id): p.source_tag for p in profiles}

@router.get("/users/tag/{tag}", response_model=List[CVProfileResponse])
async def get_users_by_tag(tag: str, request: Request = None, db: AsyncSession = Depends(get_db)):
    """
    Récupère les profils CV (et user_ids) associés à un tag spécifique (ex: localisation 'Niort').
    Sans redondance par utilisateur (déduplication).
    """
    profiles = (await db.execute(select(CVProfile).filter(CVProfile.source_tag.ilike(tag)).order_by(CVProfile.created_at.desc()))).scalars().all()
    
    seen_users = set()
    unique_profiles = []
    
    for p in profiles:
        if p.user_id not in seen_users:
            seen_users.add(p.user_id)
            unique_profiles.append(p)
    # Group by user for bulk enrichment
    user_ids = list(seen_users)
    user_anon_map = {}
    auth_header = request.headers.get("Authorization") if request else None
    headers_downstream = {"Authorization": auth_header} if auth_header else {}
    inject(headers_downstream)
    
    async with httpx.AsyncClient(timeout=10.0) as http_client:
        for u_id in user_ids:
            try:
                u_res = await http_client.get(f"{USERS_API_URL.rstrip('/')}/{u_id}", headers=headers_downstream)
                if u_res.status_code == 200:
                    user_anon_map[u_id] = u_res.json().get("is_anonymous", False)
            except: pass

    return [
        CVProfileResponse(
            user_id=p.user_id,
            source_url=p.source_url,
            source_tag=p.source_tag,
            imported_by_id=p.imported_by_id,
            is_anonymous=user_anon_map.get(p.user_id, False)
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
    
    # On renvoie les missions du CV le plus récent
    return {"user_id": user_id, "missions": profiles[0].missions or []}

@router.get("/user/{user_id}/details", response_model=CVFullProfileResponse)
async def get_user_cv_details(user_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """
    Récupère le profil sémantique complet d'un utilisateur (RAG Context).
    """
    profile = (await db.execute(
        select(CVProfile)
        .filter(CVProfile.user_id == user_id)
        .order_by(CVProfile.created_at.desc())
    )).scalars().first()
    
    if not profile:
        raise HTTPException(status_code=404, detail="Profil sémantique introuvable pour cet utilisateur.")
        
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
    years = profile.years_of_experience or 0
    if years >= 8:
        inferred_seniority = "Senior"
    elif years >= 3:
        inferred_seniority = "Mid"
    elif years > 0:
        inferred_seniority = "Junior"
    else:
        inferred_seniority = None

    return CVFullProfileResponse(
        user_id=profile.user_id,
        summary=profile.summary,
        current_role=profile.current_role,
        seniority=inferred_seniority,
        years_of_experience=profile.years_of_experience,
        competencies_keywords=profile.competencies_keywords or [],
        missions=profile.missions or [],
        is_anonymous=is_anon
    )

@router.get("/ranking/experience", response_model=List[RankedExperienceResponse])
async def get_consultants_experience_ranking(limit: int = 5, request: Request = None, db: AsyncSession = Depends(get_db)):
    """
    Retourne la liste des consultants les plus expérimentés basés sur les années d'expérience extraites des CVs.
    """
    # 1. Query candidates by years_of_experience descending
    stmt = (
        select(CVProfile)
        .filter(CVProfile.years_of_experience.is_not(None))
        .order_by(CVProfile.years_of_experience.desc())
        .limit(limit)
    )
    
    profiles = (await db.execute(stmt)).scalars().all()
    
    # 2. Enrich with User details
    auth_header = request.headers.get("Authorization") if request else None
    headers_downstream = {"Authorization": auth_header} if auth_header else {}
    inject(headers_downstream)
    
    results = []
    async with httpx.AsyncClient(timeout=10.0) as http_client:
        for p in profiles:
            item = {
                "user_id": p.user_id,
                "years_of_experience": p.years_of_experience,
            }
            results.append(item)
    return results

async def _recalculate_bg(auth_header: str, user_caller: str):
    try:
        if not client:
            await tree_task_manager.update_progress(error="Gemini SDK non configuré (Google API Key manquante).", status="error")
            return

        await tree_task_manager.update_progress(new_log="Extraction des CVs de la base de données...")
        async with database.SessionLocal() as db:
            profiles = (await db.execute(select(CVProfile))).scalars().all()
            
        if not profiles:
            await tree_task_manager.update_progress(error="Aucun CV dans la base pour générer un arbre.", status="error")
            return

        combined_text = "\n\n--- CV SUIVANT ---\n\n".join([p.raw_content for p in profiles])
        
        await tree_task_manager.update_progress(new_log="Récupération du prompt de taxonomie...")
        try:
            async with httpx.AsyncClient() as http_client:
                headers_downstream = {"Authorization": auth_header}
                res_prompt = await http_client.get(f"{PROMPTS_API_URL.rstrip('/')}/cv_api.generate_taxonomy_tree", headers=headers_downstream, timeout=5.0)
                res_prompt.raise_for_status()
                instruction = res_prompt.json()["value"]
        except Exception as e:
            logger.warning(f"Prompt cv_api.generate_taxonomy_tree indisponible (erreur: {e}). Fallback local.")
            if os.path.exists("cv_api.generate_taxonomy_tree.txt"):
                with open("cv_api.generate_taxonomy_tree.txt", "r", encoding="utf-8") as f:
                    instruction = f.read()
            else:
                await tree_task_manager.update_progress(error=f"Cannot fetch taxonomy prompt and no fallback: {e}", status="error")
                return

        await tree_task_manager.update_progress(new_log="Récupération des compétences existantes...")
        try:
            async with httpx.AsyncClient() as http_client:
                headers = {"Authorization": auth_header}
                all_comps = []
                skip = 0
                limit = 100
                while True:
                    comp_res = await http_client.get(
                        f"{COMPETENCIES_API_URL.rstrip('/')}/", 
                        params={"skip": skip, "limit": limit}, 
                        headers=headers,
                        timeout=10.0
                    )
                    comp_res.raise_for_status()
                    comp_data = comp_res.json()
                    
                    items = comp_data.get("items", []) if isinstance(comp_data, dict) else comp_data
                    all_comps.extend(items)
                    
                    if isinstance(comp_data, dict) and "total" in comp_data:
                        if len(all_comps) >= comp_data["total"]:
                            break
                    elif len(items) < limit:
                        break
                    skip += limit
                
                def get_all_names(nodes):
                    names = []
                    for n in nodes:
                        names.append(n["name"])
                        if "sub_competencies" in n and n["sub_competencies"]:
                            names.extend(get_all_names(n["sub_competencies"]))
                    return names
                
                existing_names = get_all_names(all_comps)
                skills_str = ", ".join(existing_names) if existing_names else "Aucune compétence existante"
                instruction = instruction.replace("{{EXISTING_COMPETENCIES}}", skills_str)
        except Exception as e:
            msg = f"Failed to inject existing competencies: {e}"
            print(msg)
            await tree_task_manager.update_progress(new_log=msg)

        await tree_task_manager.update_progress(new_log="Lancement du modèle Gemini...")
        response = await generate_content_with_retry(
            client,
            model=os.getenv("GEMINI_PRO_MODEL", "gemini-3-pro-preview"),
            contents=[instruction, combined_text],
            config=types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json",
            )
        )
        
        # FinOps Logging
        r_meta = None
        try:
            r_meta = response.usage_metadata
        except Exception as e:
            logger.warning(f"Metadata access failed for recalculate_tree: {e}")
        auth_token = auth_header.replace("Bearer ", "") if auth_header and "Bearer " in auth_header else auth_header
        await _log_finops(user_caller, "recalculate_tree", os.getenv("GEMINI_PRO_MODEL", "gemini-3-pro-preview"), r_meta, auth_token=auth_token)

        estimated_cost_usd = 0
        if r_meta:
            input_tokens = getattr(r_meta, 'prompt_token_count', 0)
            output_tokens = getattr(r_meta, 'candidates_token_count', 0)
            estimated_cost_usd = (input_tokens * 1.25 + output_tokens * 5.0) / 1000000

        res_tree = json.loads(response.text)
        await tree_task_manager.update_progress(
            new_log="Calcul terminé avec succès.",
            tree=res_tree,
            usage={"estimated_cost_usd": estimated_cost_usd},
            status="completed"
        )
    except Exception as e:
        await tree_task_manager.update_progress(error=f"Erreur Gemini: {str(e)}", status="error")

@router.post("/recalculate_tree")
async def recalculate_competencies_tree(
    request: Request,
    background_tasks: BackgroundTasks,
    token_payload: dict = Depends(verify_jwt)
):
    """
    (Admin Only) Lance le recalcul asynchrone de l'arbre de compétences.
    """
    if token_payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Opération refusée: privilèges administrateur requis.")
    
    if await tree_task_manager.is_task_running():
        return {"message": "Un calcul de l'arbre est déjà en cours", "status": "running"}

    auth_header = request.headers.get("Authorization")
    user_caller = token_payload.get("sub", "unknown")
    
    await tree_task_manager.initialize_task()
    background_tasks.add_task(_recalculate_bg, auth_header, user_caller)

    return {"message": "Calcul de l'arbre lancé", "status": "running"}

@router.get("/recalculate_tree/status")
async def get_recalculate_tree_status():
    """Récupère le statut du recalcul de l'arbre."""
    status = await tree_task_manager.get_latest_status()
    if not status:
        return {"status": "idle", "message": "Aucune tâche lancée récemment."}
    return status
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
                f"{USERS_API_URL.rstrip('/')}/auth/internal/service-token",
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
        
    from sqlalchemy import update
    stmt = update(CVProfile).where(CVProfile.user_id == req.source_id).values(user_id=req.target_id)
    await db.execute(stmt)
    
    stmt2 = update(CVProfile).where(CVProfile.imported_by_id == req.source_id).values(imported_by_id=req.target_id)
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
                from sqlalchemy import update
                # Update profiles owned by the user
                stmt = update(CVProfile).where(CVProfile.user_id == source_id).values(user_id=target_id)
                await db.execute(stmt)
                
                # Update profiles imported BY the user
                stmt2 = update(CVProfile).where(CVProfile.imported_by_id == source_id).values(imported_by_id=target_id)
                await db.execute(stmt2)
                
                await db.commit()
        
        return {"status": "processed"}
    except Exception as e:
        logger.error(f"Error processing Pub/Sub event: {e}")
        return {"status": "error", "detail": str(e)}
