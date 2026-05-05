import logging
import os
import time
from typing import List, Optional

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


async def process_cv_core(
    url: str,
    google_access_token: Optional[str],
    source_tag: Optional[str],
    headers: dict,
    token_payload: dict,
    db: AsyncSession,
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
        _step_error("download", "Téléchargement du document", dur, str(e))
        CV_PROCESSING_TOTAL.labels(status="failure").inc()
        raise HTTPException(status_code=400, detail=f"Failed downloading CV content: {e}")

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
        await log_finops(user_caller, "analyze_cv", os.getenv("GEMINI_CV_MODEL", os.getenv("GEMINI_MODEL")), safe_meta, {"cv_url": url}, auth_token=auth_token)

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
        user_id, importer_id, first_name, last_name, email, is_anonymous, resolve_warnings = await CVStorageService.resolve_identity_and_user(
            db, structured_cv, folder_name, token_payload, url, headers
        )
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

    # ── Étape 6 : Génération des embeddings vectoriels ────────────────────────
    t0 = time.monotonic()
    distilled_content = _build_distilled_content(structured_cv)
    vector_data = None
    try:
        emb_res = await embed_content_with_retry(
            genai_client,
            model=os.getenv("GEMINI_EMBEDDING_MODEL"),
            contents=distilled_content
        )
        vector_data = emb_res.embeddings[0].values
        dur = int((time.monotonic() - t0) * 1000)
        _step_ok("embedding", "Génération des embeddings vectoriels", dur, f"{len(vector_data)} dimensions")
    except Exception as e:
        dur = int((time.monotonic() - t0) * 1000)
        _step_warn("embedding", "Génération des embeddings vectoriels", dur, f"Embedding échoué : {e}")
        pipeline_warnings.append("Embedding vectoriel échoué")

    # ── Étape 7 : Sauvegarde en base de données ───────────────────────────────
    t0 = time.monotonic()
    try:
        await CVStorageService.upsert_cv_profile(
            db, user_id, url, source_tag, structured_cv, raw_text, vector_data, importer_id
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
        "warnings": pipeline_warnings,
        "steps": [s.model_dump() for s in pipeline_steps]
    }
    return CVResponse(**response_data)
