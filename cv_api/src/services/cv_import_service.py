import logging
import math
import os
import re
import time
from typing import List, Optional

import httpx
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from src.cvs.schemas import CVImportStep, CVResponse
from src.gemini_retry import embed_content_with_retry
from src.services.cv_extraction_service import CVExtractionService
from src.services.cv_storage_service import CVStorageService
from src.services.finops import log_finops
from src.services.utils import _build_distilled_content
from metrics import CV_PROCESSING_TOTAL

logger = logging.getLogger(__name__)

EXTRACTION_RELIABILITY_THRESHOLD = int(os.getenv("EXTRACTION_RELIABILITY_THRESHOLD", "75"))
_GDOC_ID_RE = re.compile(r"/document/d/([a-zA-Z0-9_-]+)")


async def _notify_blacklist_attempt(source_url: str, headers: dict) -> None:
    """
    Notifie drive_api d'une tentative d'extraction échouée (score < seuil).
    Best-effort : ne bloque jamais le pipeline CV si drive_api est indisponible.
    Ignore silencieusement les CVs sans URL Google Drive (imports manuels).
    """
    m = _GDOC_ID_RE.search(source_url or "")
    if not m:
        return
    google_file_id = m.group(1)
    drive_api_url = os.getenv("DRIVE_API_URL", "http://drive_api:8006")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{drive_api_url.rstrip('/')}/files/{google_file_id}/blacklist-attempt",
                headers={k: v for k, v in headers.items() if k.lower() == "authorization"},
            )
        if resp.status_code not in (200, 201, 404):
            logger.warning(
                "[BLACKLIST_NOTIFY] drive_api HTTP %d pour le fichier %s",
                resp.status_code, google_file_id,
            )
        else:
            result = resp.json()
            if result.get("blacklisted"):
                logger.warning(
                    "[EXTRACTION_BLACKLISTED] Fichier %s blacklisté après %d tentatives (score < %d).",
                    google_file_id, result.get("extraction_attempt_count", "?"), EXTRACTION_RELIABILITY_THRESHOLD,
                )
    except Exception as e:
        logger.warning("[BLACKLIST_NOTIFY] Erreur best-effort lors de la notification drive_api : %s", e)


async def process_cv_core(
    url: str,
    google_access_token: Optional[str],
    source_tag: Optional[str],
    headers: dict,
    token_payload: dict,
    db: Optional[AsyncSession] = None,
    auth_token: str = None,
    folder_name: Optional[str] = None,
    file_type: str = "google_doc",
    background_tasks: BackgroundTasks = None,
    genai_client=None,
) -> CVResponse:
    """
    Pipeline principal d'ingestion d'un CV.
    Délégué à CVExtractionService (LLM/Gemini) et CVStorageService (DB/APIs).
    """
    pipeline_steps: List[CVImportStep] = []
    pipeline_warnings: List[str] = []

    def _step_ok(step: str, label: str, duration_ms: int, detail: str = None) -> CVImportStep:
        s = CVImportStep(step=step, label=label, status="success", duration_ms=duration_ms, detail=detail)
        pipeline_steps.append(s)
        logger.info(f"[CV_STEP] {label} — OK", extra={"step": step,
                    "duration_ms": duration_ms, "cv_url": url, "detail": detail})
        return s

    def _step_warn(step: str, label: str, duration_ms: int, detail: str = None) -> CVImportStep:
        s = CVImportStep(step=step, label=label, status="warning", duration_ms=duration_ms, detail=detail)
        pipeline_steps.append(s)
        pipeline_warnings.append(detail or label)
        logger.warning(f"[CV_STEP] {label} — WARN: {detail}", extra={
                       "step": step, "duration_ms": duration_ms, "cv_url": url})
        return s

    def _step_error(step: str, label: str, duration_ms: int, detail: str = None) -> CVImportStep:
        s = CVImportStep(step=step, label=label, status="error", duration_ms=duration_ms, detail=detail)
        pipeline_steps.append(s)
        logger.error(f"[CV_STEP] {label} — ERROR: {detail}", extra={
                     "step": step, "duration_ms": duration_ms, "cv_url": url})
        return s

    # ── Étape 1 : Téléchargement du document ─────────────────────────────────
    t0 = time.monotonic()
    try:
        raw_text = await CVExtractionService.fetch_cv_content(url, google_access_token, file_type=file_type)
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
        raise
    except Exception as e:
        dur = int((time.monotonic() - t0) * 1000)
        _step_error("download", "Téléchargement du document", dur, repr(e))
        CV_PROCESSING_TOTAL.labels(status="failure").inc()
        raise HTTPException(status_code=400, detail=f"Failed downloading CV content: {e!r}")

    # ── Étape 2 : Analyse IA — Extraction du profil ──────────────────────────
    t0 = time.monotonic()
    if not genai_client:
        raise HTTPException(status_code=500, detail="GenAI Client not configured.")

    try:
        structured_cv, safe_meta = await CVExtractionService.analyze_cv_with_llm(
            raw_text=raw_text,
            headers=headers,
            genai_client=genai_client,
        )
        user_caller = token_payload.get("sub", "unknown")
        await log_finops(
            user_caller,
            "analyze_cv",
            os.getenv("GEMINI_CV_MODEL", os.getenv("GEMINI_MODEL")),
            safe_meta,
            {"cv_url": url},
            auth_token=auth_token
        )

        if not structured_cv.get("is_cv", False):
            dur = int((time.monotonic() - t0) * 1000)
            _step_error("llm_parse", "Analyse IA — Extraction du profil", dur, "Document non reconnu comme un CV")
            raise HTTPException(status_code=400, detail="Not a CV: The document does not appear to be a resume.")

        nb_competencies = len(structured_cv.get("competencies", []))
        nb_missions = len(structured_cv.get("missions", []))
        summary_val = structured_cv.get("summary", "")
        dur = int((time.monotonic() - t0) * 1000)

        llm_detail = f"{nb_competencies} compétences, {nb_missions} missions détectées"
        if nb_competencies == 0:
            warn_cv = "Aucune compétence extraite par l'IA — vérifiez la qualité du document"
            _step_warn("llm_parse", "Analyse IA — Extraction du profil", dur, llm_detail)
            pipeline_warnings.append(warn_cv)
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
        CV_PROCESSING_TOTAL.labels(status="failure").inc()
        raise HTTPException(status_code=500, detail=f"LLM Parsing failed: {e}")

    # ── Étape 3, 4 et 5 : Résolution, Création utilisateur et missions ───────
    t0 = time.monotonic()
    try:
        from database import SessionLocal
        if db is None:
            async with SessionLocal() as local_db:
                result = await CVStorageService.resolve_identity_and_user(
                    local_db, structured_cv, folder_name, token_payload, url, headers
                )
        else:
            result = await CVStorageService.resolve_identity_and_user(
                db, structured_cv, folder_name, token_payload, url, headers
            )
        user_id, importer_id, first_name, last_name, email, is_anonymous, resolve_warnings = result
        for w in resolve_warnings:
            pipeline_warnings.append(w)
            _step_warn("user_resolve", "Résolution d'identité", 0, w)

        dur = int((time.monotonic() - t0) * 1000)
        _step_ok("user_resolve", "Résolution & création d'identité", dur, f"User ID {user_id}")

        if background_tasks:
            background_tasks.add_task(CVStorageService.bg_process_competencies_and_missions,
                                      user_id, structured_cv, headers, url)
            _step_ok("competencies_missions", "Mapping RAG et Extraction", 0, "Délégué en Background Task (Asynchrone)")
            assigned_count = 0
        else:
            await CVStorageService.bg_process_competencies_and_missions(user_id, structured_cv, headers, url)
            assigned_count = 0
    except Exception as e:
        dur = int((time.monotonic() - t0) * 1000)
        _step_error("user_resolve", "Création utilisateur et compétences", dur, str(e))
        CV_PROCESSING_TOTAL.labels(status="failure").inc()
        raise

    # ── Étape 6 : Génération des embeddings vectoriels et test de qualité ───────
    t0 = time.monotonic()
    distilled_content = _build_distilled_content(structured_cv)
    vector_data = None
    extraction_reliability_score = None
    try:
        # Distilled content embedding
        emb_res = await embed_content_with_retry(
            genai_client,
            model=os.getenv("GEMINI_EMBEDDING_MODEL"),
            contents=distilled_content,
            config={"task_type": "RETRIEVAL_DOCUMENT"},
        )
        vector_data = emb_res.embeddings[0].values
        # Raw content embedding for quality check (limit to 20k chars)
        raw_snippet = raw_text[:20000]
        raw_emb_res = await embed_content_with_retry(
            genai_client,
            model=os.getenv("GEMINI_EMBEDDING_MODEL"),
            contents=raw_snippet,
            config={"task_type": "RETRIEVAL_DOCUMENT"},
        )
        raw_vector = raw_emb_res.embeddings[0].values

        # Calculate Cosine Similarity
        dot_product = sum(a * b for a, b in zip(vector_data, raw_vector))
        norm_v1 = math.sqrt(sum(a * a for a in vector_data))
        norm_v2 = math.sqrt(sum(b * b for b in raw_vector))
        if norm_v1 > 0 and norm_v2 > 0:
            sim = dot_product / (norm_v1 * norm_v2)
            # Map [-1, 1] to [0, 100] approximately or just take max(0, sim)*100
            extraction_reliability_score = min(100, max(0, int(sim * 100)))

        dur = int((time.monotonic() - t0) * 1000)
        _step_ok(
            "embedding", "Génération des embeddings vectoriels", dur,
            f"{len(vector_data)} dimensions, Score Fiabilité: {extraction_reliability_score}%"
        )
        # Notifier drive_api si le score est sous le seuil (best-effort, ne bloque pas)
        if extraction_reliability_score is not None and extraction_reliability_score < EXTRACTION_RELIABILITY_THRESHOLD:
            await _notify_blacklist_attempt(url, headers)
    except Exception as e:
        dur = int((time.monotonic() - t0) * 1000)
        _step_warn("embedding", "Génération des embeddings vectoriels", dur, f"Embedding échoué : {e}")
        pipeline_warnings.append("Embedding vectoriel échoué")

    # ── Étape 7 : Sauvegarde en base de données ───────────────────────────────
    t0 = time.monotonic()
    try:
        from database import SessionLocal
        if db is None:
            async with SessionLocal() as local_db:
                await CVStorageService.upsert_cv_profile(
                    local_db, user_id, url, source_tag, structured_cv, raw_text, vector_data,
                    importer_id, extraction_reliability_score
                )
        else:
            await CVStorageService.upsert_cv_profile(
                db, user_id, url, source_tag, structured_cv, raw_text, vector_data,
                importer_id, extraction_reliability_score
            )
        dur = int((time.monotonic() - t0) * 1000)
        _step_ok("db_save", "Sauvegarde en base de données", dur, f"CV ID utilisateur {user_id}")
    except Exception as e:
        dur = int((time.monotonic() - t0) * 1000)
        _step_error("db_save", "Sauvegarde en base de données", dur, str(e))
        CV_PROCESSING_TOTAL.labels(status="failure").inc()
        raise HTTPException(status_code=500, detail=f"Database save failed: {e}")

    CV_PROCESSING_TOTAL.labels(status="success").inc()

    response_data = {
        "status": "success",
        "message": "Import et analyse terminés avec succès",
        "user_id": user_id,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "is_anonymous": is_anonymous,
        "competencies_assigned": assigned_count,
        "structured_cv": structured_cv,  # Transmis à pubsub pour bg_process sans re-extraction
        "warnings": pipeline_warnings,
        "steps": [s.model_dump() for s in pipeline_steps]
    }
    return CVResponse(**response_data)
