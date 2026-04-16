from fastapi import APIRouter, Depends, HTTPException, Request, Response, Query
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
import base64
import random
import string
import urllib.parse
import logging

from database import get_db
from src.auth import verify_jwt, security
from src.cvs.models import CVProfile
from src.cvs.schemas import CVImportRequest, CVImportStep, CVResponse, SearchCandidateResponse, SearchCandidateRequest, CVProfileResponse, CVFullProfileResponse, UserMergeRequest, RankedExperienceResponse
from .task_state import task_state_manager
from metrics import CV_PROCESSING_TOTAL, CV_MISSING_EMBEDDINGS
from src.gemini_retry import generate_content_with_retry, embed_content_with_retry

router = APIRouter(prefix="", tags=["CV Analysis"], dependencies=[Depends(verify_jwt)])
public_router = APIRouter(prefix="", tags=["CV_Public"])

USERS_API_URL = os.getenv("USERS_API_URL", "http://users_api:8000")
COMPETENCIES_API_URL = os.getenv("COMPETENCIES_API_URL", "http://competencies_api:8003")
PROMPTS_API_URL = os.getenv("PROMPTS_API_URL", "http://prompts_api:8000")
DRIVE_API_URL = os.getenv("DRIVE_API_URL", "http://drive_api:8006")
ITEMS_API_URL = os.getenv("ITEMS_API_URL", "http://items_api:8001")

# Initialize Gemini Client
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
MARKET_MCP_URL = os.getenv("MARKET_MCP_URL", "http://market_mcp:8008")

if not GEMINI_API_KEY:
    print("WARNING: GOOGLE_API_KEY is missing. RAG embeddings will fail.")
    client = None
else:
    client = genai.Client(api_key=GEMINI_API_KEY)

logger = logging.getLogger(__name__)

from typing import Any
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
async def import_and_analyze_cv(req: CVImportRequest, request: Request, db: AsyncSession = Depends(get_db), token_payload: dict = Depends(verify_jwt)):
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
        headers=headers,
        token_payload=token_payload,
        db=db,
        auth_token=auth_header.replace("Bearer ", "") if "Bearer " in auth_header else auth_header
    )

async def _process_cv_core(url: str, google_access_token: Optional[str], source_tag: Optional[str], headers: dict, token_payload: dict, db: AsyncSession, auth_token: str = None) -> CVResponse:
    """
    Pipeline principal d'ingestion d'un CV en 8 étapes séquentielles.
    Retourne un CVResponse enrichi avec les étapes (steps) et les warnings non-bloquants.
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
        if raw_len > 8000:
            warn_msg = f"Document tronqué : {raw_len} caractères → limité à 8000 pour l'analyse IA"
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
    try:
        logger.info("[CV_STEP] llm_parse — fetching prompt", extra={"step": "llm_parse", "cv_url": url})
        async with httpx.AsyncClient() as http_client:
            res_prompt = await http_client.get(f"{PROMPTS_API_URL.rstrip('/')}/cv_api.extract_cv_info", headers=headers, timeout=5.0)
            res_prompt.raise_for_status()
            prompt = res_prompt.json()["value"]
    except Exception as e:
        logger.warning(f"Prompt cv_api.extract_cv_info indisponible (erreur: {e}). Fallback local.")
        if os.path.exists("cv_api.extract_cv_info.txt"):
            with open("cv_api.extract_cv_info.txt", "r", encoding="utf-8") as f:
                prompt = f.read()
        else:
            logger.error("No fallback file cv_api.extract_cv_info.txt found.")
            raise HTTPException(status_code=500, detail=f"Cannot fetch generic prompt: {e}")

    try:
        tree_context = ""
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
        except Exception as e:
            logger.warning(f"Failed to fetch competencies tree for context: {e}")

        final_prompt = prompt + tree_context

        response = await generate_content_with_retry(
            client,
            model=os.getenv("GEMINI_MODEL", "gemini-3-flash-preview"),
            contents=[final_prompt, f"RESUME:\n{raw_text[:8000]}"],
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

    raw_email = sanitize_field(structured_cv.get("email"))
    first_name = sanitize_field(structured_cv.get("first_name"))
    last_name = sanitize_field(structured_cv.get("last_name"))
    is_anonymous = structured_cv.get("is_anonymous", False)
    trigram = sanitize_field(structured_cv.get("trigram"))

    EMAIL_REGEX = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
    def is_valid_email(e: Optional[str]) -> bool:
        return bool(e and re.match(EMAIL_REGEX, e))

    def normalize_str(s: str) -> str:
        if not s: return ""
        return unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('utf-8').lower()

    if not is_valid_email(raw_email):
        if first_name and last_name:
            clean_f = normalize_str(first_name).replace(" ", "")
            clean_l = normalize_str(last_name).replace(" ", "")
            email = f"{clean_f}.{clean_l}@zenika.com"
            logger.info(f"Invalid/Missing email in CV. Generated: {email}")
            pipeline_warnings.append(f"Email absent ou invalide dans le CV — email généré : {email}")
        else:
            is_anonymous = True
            trigram = trigram or ''.join(random.choices(string.ascii_uppercase, k=3))
            first_name = "Anon"
            last_name = trigram
            email = f"anon.{trigram.lower()}@anonymous.zenika.com"
            logger.warning(f"Total identity absence. Generated random: {email}")
            pipeline_warnings.append("Identité introuvable dans le CV — profil anonymisé automatiquement")
    else:
        email = raw_email

    ext_full_norm = f"{normalize_str(first_name)} {normalize_str(last_name)}"

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        user_id = None
        importer_id = None

        if email:
            search_res = await http_client.get(f"{USERS_API_URL.rstrip('/')}/search", params={"query": email, "limit": 10}, headers=headers)
            if search_res.status_code == 200:
                for u in search_res.json().get("items", []):
                    if u.get("email", "").lower() == email.lower():
                        u_full_norm = normalize_str(u.get("full_name") or f"{u.get('first_name')} {u.get('last_name')}")
                        if ext_full_norm and ext_full_norm.strip():
                            if ext_full_norm not in u_full_norm and u_full_norm not in ext_full_norm:
                                logger.warning(f"Email {email} found but name mismatch: Extracted '{ext_full_norm}' vs System '{u_full_norm}'. Detaching.")
                                continue
                        user_id = u["id"]
                        logger.info(f"User matched by identity: {email} -> ID: {user_id}")
                        break

        if not user_id and first_name and last_name:
            logger.info(f"Identity {email} not matched in system. Attempting semantic fallback on name: {first_name} {last_name}.")
            search_q = f"{first_name} {last_name}"
            name_res = await http_client.get(f"{USERS_API_URL.rstrip('/')}/search", params={"query": search_q, "limit": 10}, headers=headers)
            if name_res.status_code == 200:
                for u in name_res.json().get("items", []):
                    if normalize_str(u.get("first_name")) == normalize_str(first_name) and normalize_str(u.get("last_name")) == normalize_str(last_name):
                        user_id = u["id"]
                        logger.info(f"User matched semantically by name -> ID: {user_id}")
                        break

        importer_username = token_payload.get("sub")
        if importer_username:
            importer_res = await http_client.get(f"{USERS_API_URL.rstrip('/')}/search", params={"query": importer_username, "limit": 10}, headers=headers)
            if importer_res.status_code == 200:
                for u in importer_res.json().get("items", []):
                    if u.get("username", "").lower() == importer_username.lower():
                        importer_id = u["id"]
                        break

        filename = os.path.basename(url).lower()
        if not is_anonymous:
            if "annonym" in filename or "anon" in filename or "abc" in filename:
                logger.info("Anonymity detected based on filename.")
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
            "is_anonymous": is_anonymous
        }

        if user_id and is_anonymous:
            user_info_res = await http_client.get(f"{USERS_API_URL.rstrip('/')}/{user_id}", headers=headers)
            if user_info_res.status_code == 200:
                user_data = user_info_res.json()
                if not user_data.get("is_anonymous", False):
                    warn_msg = f"🛡️ CV anonyme détecté sur un compte réel (User {user_id}). DÉTACHEMENT du profil."
                    logger.info(warn_msg)
                    await task_state_manager.update_progress(new_log=warn_msg)
                    user_id = None
                else:
                    logger.info(f"CV is anonymous and User {user_id} is already anonymous. Keeping link.")

        if not user_id:
            logger.info(f"User not found, creating {'anonymous ' if is_anonymous else ''}user...")
            new_u = {
                "username": f"{first_name[0].lower()}{last_name.lower()}{random.randint(100, 999)}",
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
                "full_name": f"{first_name} {last_name}",
                "password": "zenikacv123",
                "is_anonymous": is_anonymous
            }
            create_res = await http_client.post(f"{USERS_API_URL.rstrip('/')}/", json=new_u, headers=headers)

            if create_res.status_code == 409 or (create_res.status_code >= 400 and "already exists" in create_res.text.lower()):
                host = email.split('@')[1] if '@' in email else "zenika.com"
                prefix = email.split('@')[0] if '@' in email else "conflict"
                conflict_email = f"{prefix}.conflict.{random.randint(1000, 9999)}@{host}"
                logger.warning(f"Email conflict for {email}. Detaching identity via {conflict_email}")
                pipeline_warnings.append(f"Conflit d'email ({email}) — identité détachée vers {conflict_email}")
                new_u["email"] = conflict_email
                create_res = await http_client.post(f"{USERS_API_URL.rstrip('/')}/", json=new_u, headers=headers)

            if create_res.status_code >= 400:
                dur = int((time.monotonic() - t0) * 1000)
                err_detail = f"Création utilisateur échouée (HTTP {create_res.status_code})"
                _step_error("user_resolve", "Résolution & création d'identité", dur, err_detail)
                logger.error(f"User creation failed: status={create_res.status_code}, detail={create_res.text}")
                raise HTTPException(status_code=500, detail=f"User creation failed: {create_res.text}")

            user_id = create_res.json()["id"]
            logger.info(f"User created with ID {user_id}")

        dur = int((time.monotonic() - t0) * 1000)
        mode = "anonyme" if is_anonymous else f"email={email}"
        _step_ok("user_resolve", "Résolution & création d'identité", dur, f"User ID {user_id} ({mode})")

        # ── Étape 4 : Mapping des compétences ─────────────────────────────────
        t0 = time.monotonic()
        comp_res = await http_client.get(f"{COMPETENCIES_API_URL.rstrip('/')}/?limit=1000", headers=headers)
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

        assigned_count = 0
        comp_errors = 0
        logger.info(f"[CV_STEP] competencies — start", extra={"step": "competencies", "count": nb_competencies, "cv_url": url})
        for comp in structured_cv.get("competencies", []):
            name = comp["name"]
            parent = comp.get("parent")

            try:
                c_id = find_comp_id(all_comps, name)
                if not c_id:
                    p_id = None
                    if parent:
                        p_id = find_comp_id(all_comps, parent)
                        if not p_id:
                            p_res = await http_client.post(f"{COMPETENCIES_API_URL.rstrip('/')}/", json={"name": parent, "description": "Auto-identified from CV"}, headers=headers)
                            if p_res.status_code < 400:
                                p_id = p_res.json()["id"]
                                all_comps.append(p_res.json())

                    aliases_str = ", ".join(comp.get("aliases", [])) if comp.get("aliases") else None
                    leaf_data = {"name": name, "description": "Candidate CV Skill", "aliases": aliases_str}
                    if p_id: leaf_data["parent_id"] = p_id

                    c_res = await http_client.post(f"{COMPETENCIES_API_URL.rstrip('/')}/", json=leaf_data, headers=headers)
                    if c_res.status_code < 400:
                        c_id = c_res.json()["id"]
                        all_comps.append(c_res.json())

                if c_id:
                    assign_res = await http_client.post(f"{COMPETENCIES_API_URL.rstrip('/')}/user/{user_id}/assign/{c_id}", headers=headers)
                    if assign_res.status_code < 400:
                        assigned_count += 1
            except Exception as e:
                comp_errors += 1
                logger.warning(f"[CV_STEP] competencies — failed to assign '{name}': {e}", extra={"step": "competencies", "cv_url": url})

        dur = int((time.monotonic() - t0) * 1000)
        comp_detail = f"{assigned_count}/{nb_competencies} compétences assignées"
        if comp_errors > 0:
            comp_detail += f", {comp_errors} erreurs d'assignation"
            pipeline_warnings.append(f"{comp_errors} compétence(s) n'ont pas pu être assignées")
            _step_warn("competencies", "Mapping des compétences RAG", dur, comp_detail)
        else:
            _step_ok("competencies", "Mapping des compétences RAG", dur, comp_detail)

        # ── Étape 5 : Extraction des missions ─────────────────────────────────
        t0 = time.monotonic()
        missions_list = structured_cv.get("missions", [])
        logger.info(f"[CV_STEP] missions — start", extra={"step": "missions", "count": len(missions_list), "cv_url": url})

        cat_res = await http_client.get(f"{ITEMS_API_URL.rstrip('/')}/categories", headers=headers)
        categories = cat_res.json() if cat_res.status_code == 200 else []

        def find_cat_id(name):
            for c in categories:
                if c["name"].lower() == name.lower(): return c["id"]
            return None

        mission_cat_id = find_cat_id("Missions")
        if not mission_cat_id:
            m_res = await http_client.post(f"{ITEMS_API_URL.rstrip('/')}/categories", json={"name": "Missions", "description": "Professional experiences extracted from CVs"}, headers=headers)
            if m_res.status_code < 400: mission_cat_id = m_res.json()["id"]

        sensitive_cat_id = find_cat_id("Restricted")
        if not sensitive_cat_id:
            s_res = await http_client.post(f"{ITEMS_API_URL.rstrip('/')}/categories", json={"name": "Restricted", "description": "Sensitive or confidential missions"}, headers=headers)
            if s_res.status_code < 400: sensitive_cat_id = s_res.json()["id"]

        mission_errors = 0
        mission_ok = 0
        for m in missions_list:
            try:
                cat_ids = [mission_cat_id] if mission_cat_id else []
                if m.get("is_sensitive") and sensitive_cat_id:
                    cat_ids.append(sensitive_cat_id)

                item_data = {
                    "name": m["title"],
                    "description": m.get("description", ""),
                    "user_id": user_id,
                    "category_ids": cat_ids,
                    "metadata_json": {
                        "company": m.get("company"),
                        "competencies": m.get("competencies", []),
                        "is_sensitive": m.get("is_sensitive", False),
                        "source": "CV Analysis"
                    }
                }
                m_post = await http_client.post(f"{ITEMS_API_URL.rstrip('/')}/", json=item_data, headers=headers)
                if m_post.status_code < 400:
                    mission_ok += 1
                else:
                    mission_errors += 1
                    logger.warning(f"[CV_STEP] missions — failed to create item '{m['title']}': HTTP {m_post.status_code}", extra={"step": "missions", "cv_url": url})
            except Exception as e:
                mission_errors += 1
                logger.error(f"Failed to offload mission '{m['title']}': {e}")

        dur = int((time.monotonic() - t0) * 1000)
        mission_detail = f"{mission_ok}/{len(missions_list)} missions créées"
        if mission_errors > 0:
            mission_detail += f", {mission_errors} erreurs"
            pipeline_warnings.append(f"{mission_errors} mission(s) n'ont pas pu être créées dans Items API")
            _step_warn("missions", "Extraction & indexation des missions", dur, mission_detail)
        else:
            _step_ok("missions", "Extraction & indexation des missions", dur, mission_detail)

    # hors du bloc httpx
    # ── Étape 6 : Génération des embeddings vectoriels ────────────────────────
    t0 = time.monotonic()
    comp_keywords = [c.get("name") for c in structured_cv.get("competencies", []) if c.get("name")]

    distilled_content = (
        f"Role: {structured_cv.get('current_role', 'Unknown')}\n"
        f"Experience: {structured_cv.get('years_of_experience', 0)} years\n"
        f"Summary: {structured_cv.get('summary', '')}\n"
        f"Competencies: {', '.join(comp_keywords)}\n"
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
                "current_role": p.current_role,
                "is_anonymous": False
            }
            try:
                u_res = await http_client.get(f"{USERS_API_URL.rstrip('/')}/{p.user_id}", headers=headers_downstream)
                if u_res.status_code == 200:
                    u_data = u_res.json()
                    item["full_name"] = u_data.get("full_name")
                    item["email"] = u_data.get("email")
                    item["is_anonymous"] = u_data.get("is_anonymous", False)
            except Exception as e:
                logger.warning(f"Failed to enrich user info for {p.user_id}: {e}")
            
            results.append(RankedExperienceResponse(**item))
            
    return results

@router.post("/recalculate_tree")
async def recalculate_competencies_tree(
    request: Request, 
    db: AsyncSession = Depends(get_db), 
    token_payload: dict = Depends(verify_jwt)
):
    """
    (Admin Only) Lit tous les CVs de la base et donne à Gemini la mission de synthétiser 
    le modèle hiérarchique optimal pour l'entreprise (Catégories -> Spécialités -> Compétences).
    """
    if token_payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Opération refusée: privilèges administrateur requis.")
    
    auth_header = request.headers.get("Authorization")
             
    if not client:
        raise HTTPException(status_code=500, detail="Gemini SDK non configuré (Google API Key manquante).")

    profiles = (await db.execute(select(CVProfile))).scalars().all()
    if not profiles:
        raise HTTPException(status_code=404, detail="Aucun CV dans la base pour générer un arbre.")

    combined_text = "\n\n--- CV SUIVANT ---\n\n".join([p.raw_content for p in profiles])
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
            raise HTTPException(status_code=500, detail=f"Cannot fetch taxonomy prompt and no fallback: {e}")

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
                
                # Handling both direct list and PaginationResponse
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
        print(f"WARNING: Failed to inject existing competencies: {e}")

    try:
        response = await generate_content_with_retry(
            client,
            model=os.getenv("GEMINI_PRO_MODEL", "gemini-3-pro-preview"),
            contents=[instruction, combined_text],
            config=types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json",
            )
        )
        
        # FinOps Logging (Safe access)
        user_caller = token_payload.get("sub", "unknown")
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
            # Prix Gemini Pro : ~1.25$ / 1M in, 5.00$ / 1M out
            estimated_cost_usd = (input_tokens * 1.25 + output_tokens * 5.0) / 1000000

        # Parse JSON string from model implicitly as it's guaranteed to be valid by `response_mime_type`
        return {
            "tree": json.loads(response.text),
            "usage": {
                "estimated_cost_usd": estimated_cost_usd
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur Gemini: {str(e)}")

@router.get("/reanalyze/status")
async def get_reanalyze_status():
    """Récupère le statut de la dernière tâche de réanalyse."""
    status = await task_state_manager.get_latest_status()
    if not status:
        return {"status": "idle", "message": "Aucune tâche lancée récemment."}
    return status

@router.post("/reanalyze")
async def reanalyze_cvs(
    request: Request,
    tag: Optional[str] = None,
    user_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    token_payload: dict = Depends(verify_jwt)
):
    """
    (Admin Only) Relance le pipeline d'extraction Gemini sur un ensemble de CVs.
    Identifie également les erreurs d'assignation d'identité.
    """
    if token_payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Privilèges administrateur requis.")
    
    # Vérifier si une tâche est déjà en cours
    if await task_state_manager.is_task_running():
        return {"message": "Une tâche de réanalyse est déjà en cours.", "status": "running"}

    auth_header = request.headers.get("Authorization")
    headers = {"Authorization": auth_header} if auth_header else {}
    auth_token = auth_header.replace("Bearer ", "") if auth_header and "Bearer " in auth_header else auth_header
    inject(headers)

    # 1. Fetch CVs to re-process
    stmt = select(CVProfile)
    f_type = "all"
    f_val = ""
    if tag:
        stmt = stmt.filter(CVProfile.source_tag == tag)
        f_type = "tag"
        f_val = tag
    if user_id:
        stmt = stmt.filter(CVProfile.user_id == user_id)
        f_type = "user"
        f_val = str(user_id)
        
    cvs = (await db.execute(stmt)).scalars().all()
    if not cvs:
        return {"message": "Aucun CV trouvé pour ces filtres.", "count": 0}

    # Initialiser l'état dans Redis
    await task_state_manager.initialize_task(len(cvs), f_type, f_val)

    # Dedoublonner les user_ids pour nettoyer les compétences une seule fois par utilisateur
    user_ids_to_clear = {cv.user_id for cv in cvs}
    
    async def generate():
        async with httpx.AsyncClient(timeout=60.0) as http_client:
            # 1.5 Get Google token
            google_access_token = None
            try:
                tok_res = await http_client.get(f"{DRIVE_API_URL.rstrip('/')}/tokens/google", headers=headers, timeout=5.0)
                if tok_res.status_code == 200:
                    google_access_token = tok_res.json().get("access_token")
                    msg = "Successfully acquired Google Access Token."
                    await task_state_manager.update_progress(new_log=msg)
                    yield json.dumps({"status": "info", "message": msg}) + "\n"
                else:
                    msg = f"Could not fetch Google Token (status {tok_res.status_code}). Proceeding as public."
                    await task_state_manager.update_progress(new_log=msg)
                    yield json.dumps({"status": "warn", "message": msg}) + "\n"
            except Exception as e:
                msg = f"Error fetching Google Token: {str(e)}"
                await task_state_manager.update_progress(new_log=msg)
                yield json.dumps({"status": "error", "message": msg}) + "\n"

            # 2. Clear user competencies
            for uid in user_ids_to_clear:
                try:
                    clear_res = await http_client.delete(f"{COMPETENCIES_API_URL.rstrip('/')}/user/{uid}/clear", headers=headers)
                    clear_res.raise_for_status()
                    msg = f"Cleared competencies for user {uid}"
                    await task_state_manager.update_progress(new_log=msg)
                    yield json.dumps({"status": "info", "message": msg}) + "\n"
                except Exception as e:
                    msg = f"Failed to clear competencies for user {uid}: {str(e)}"
                    await task_state_manager.update_progress(new_log=msg, error_msg=msg)
                    yield json.dumps({"status": "error", "message": msg}) + "\n"

            # 3. Process each CV
            total_cvs = len(cvs)
            
            for index, cv in enumerate(cvs):
                try:
                    url = cv.source_url
                    s_tag = cv.source_tag
                    u_id = cv.user_id
                    
                    msg = f"Processing CV {index+1}/{total_cvs} (User ID: {u_id})..."
                    await task_state_manager.update_progress(new_log=msg)
                    yield json.dumps({"status": "processing", "message": msg, "url": url}) + "\n"
                    
                    # 3.1 Fetch current user name for identity check
                    user_name = "Inconnu"
                    try:
                        u_info = await http_client.get(f"{USERS_API_URL.rstrip('/')}/{u_id}", headers=headers)
                        if u_info.status_code == 200:
                            u_data = u_info.json()
                            user_name = u_data.get("full_name") or u_data.get("username")
                    except: pass

                    # 3.2 Re-process
                    process_res = await _process_cv_core(
                        url=url,
                        google_access_token=google_access_token,
                        source_tag=s_tag,
                        headers=headers,
                        token_payload=token_payload,
                        db=db,
                        auth_token=auth_token
                    )
                    
                    # 3.3 Identity Verification logic
                    ext = process_res.extracted_info
                    if ext and not ext.get("is_anonymous"):
                        def normalize(s):
                            if not s: return ""
                            return unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('utf-8').lower()
                        
                        ext_full = f"{normalize(ext.get('first_name'))} {normalize(ext.get('last_name'))}"
                        cur_full = normalize(user_name)
                        
                        # Simple inclusion/match check
                        if ext_full not in cur_full and cur_full not in ext_full:
                            new_u_id = process_res.user_id
                            warn_msg = f"⚠️ ALERTE IDENTITÉ CV #{cv.id}: Extrait='{ext.get('first_name')} {ext.get('last_name')}' (ID:{new_u_id}) vs Actuel='{user_name}' (ID:{u_id})"
                            
                            # Update Drive API to fix the link in Scanner page
                            doc_id_match = re.search(r"/d/([a-zA-Z0-9_-]+)", url)
                            if doc_id_match:
                                g_id = doc_id_match.group(1)
                                try:
                                    await http_client.patch(
                                        f"{DRIVE_API_URL.rstrip('/')}/files/{g_id}", 
                                        json={"user_id": new_u_id},
                                        headers=headers
                                    )
                                    warn_msg += " -> Synchronisation Drive effectuée."
                                except Exception as e:
                                    logger.error(f"Failed to sync drive identity for {g_id}: {e}")
                                    warn_msg += f" (Synchro Drive échouée)"
                            
                            await task_state_manager.update_progress(new_log=warn_msg, mismatch_inc=1)
                            yield json.dumps({"status": "warn", "message": warn_msg}) + "\n"

                    msg_fin = f"Finished re-processing CV {index+1}/{total_cvs}"
                    await task_state_manager.update_progress(processed_inc=1, new_log=msg_fin)
                    yield json.dumps({"status": "success", "message": msg_fin, "url": url}) + "\n"

                except Exception as e:
                    err_msg = f"CV {cv.id}: {str(e)}"
                    await task_state_manager.update_progress(error_inc=1, new_log=f"ERREUR: {err_msg}", error_msg=err_msg)
                    yield json.dumps({"status": "error", "message": f"Failed CV {index+1}/{total_cvs}: {err_msg}"}) + "\n"

            final_status = await task_state_manager.get_latest_status()
            yield json.dumps({
                "status": "completed", 
                "message": f"Réanalyse terminée. {final_status['processed_count']} succès, {final_status['error_count']} erreurs, {final_status['mismatch_count']} alertes.",
                "count": final_status["processed_count"],
                "errors": final_status["errors"]
            }) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")

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
