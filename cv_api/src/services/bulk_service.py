"""
bulk_service.py — Service de ré-analyse globale des CVs en asynchrone (Vertex AI Batch).

Centralise la logique métier Bulk (MapReduce) extraite de router.py.
"""

import asyncio
import json
import logging
import os
import time
import traceback
from datetime import datetime, timedelta
from typing import Optional

import httpx
from fastapi import BackgroundTasks, HTTPException, Request, Depends
from google.cloud import storage as gcs_storage
from opentelemetry.propagate import inject
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update as sa_update
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.sql import func

import database
from src.cvs.models import CVProfile
from src.cvs.bulk_task_state import bulk_reanalyse_manager


from src.gemini_retry import embed_content_with_retry

from src.services.config import (
    COMPETENCIES_API_URL,
    ITEMS_API_URL,
    PROMPTS_API_URL,
    USERS_API_URL,
    BATCH_GCS_BUCKET,
    BULK_SCALE_MIN_INSTANCES,
    BULK_APPLY_SEMAPHORE,
    BULK_EMBED_SEMAPHORE,
    _CV_CACHE,
    client,
    vertex_batch_client,
)
from src.services.finops import log_finops
from src.services.utils import (
    _CV_RESPONSE_SCHEMA,
    _build_distilled_content,
    _coerce_to_str,
    _clean_llm_json,
    build_taxonomy_context,
)
from src.services.search_service import scale_bulk_dependencies

logger = logging.getLogger(__name__)


async def _acquire_service_token(auth_header: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=10.0) as hc:
            res = await hc.post(
                f"{USERS_API_URL.rstrip('/')}/internal/service-token",
                headers={"Authorization": auth_header},
            )
            if res.status_code == 200:
                return res.json().get("access_token", auth_header.removeprefix("Bearer ").strip())
            logger.warning(f"[bulk_reanalyse] service-token HTTP {res.status_code} — fallback JWT court.")
    except Exception as e:
        logger.warning(f"[bulk_reanalyse] Impossible d'obtenir le service-token: {e} — fallback JWT court.")
    return auth_header.removeprefix("Bearer ").strip()


async def _get_cv_extraction_prompt() -> str:
    now = datetime.now()
    cached = _CV_CACHE.get("prompt", {})
    if cached.get("value") and now < cached.get("expires", datetime.min):
        return cached["value"]
    try:
        async with httpx.AsyncClient(timeout=10.0) as hc:
            res = await hc.get(f"{PROMPTS_API_URL.rstrip('/')}/prompts/cv_api.extract_cv_info")
            if res.status_code == 200:
                prompt = res.json().get("value", "")
                if prompt:
                    _CV_CACHE["prompt"] = {"value": prompt, "expires": now + timedelta(minutes=30)}
                    return prompt
    except Exception as e:
        logger.warning(f"[bulk_reanalyse] prompts_api indisponible: {e}")
    for candidate in ["cv_api.extract_cv_info.txt", "/app/cv_api.extract_cv_info.txt"]:
        if os.path.exists(candidate):
            with open(candidate, "r", encoding="utf-8") as f:
                prompt = f.read()
            _CV_CACHE["prompt"] = {"value": prompt, "expires": now + timedelta(minutes=30)}
            return prompt
    logger.error("[bulk_reanalyse] CRITIQUE : aucun prompt CV disponible")
    return ""


async def _post_missions_bulk(hc: httpx.AsyncClient, user_id: int, missions: list, headers: dict):
    if not missions:
        return
    items_payload = []
    for m in missions:
        title = m.get("title") or m.get("company") or "Mission sans titre"
        items_payload.append({
            "name": title[:255],
            "description": m.get("description", "")[:2000],
            "user_id": user_id,
            "category_ids": [],
            "metadata_json": {
                "start_date": m.get("start_date"),
                "end_date": m.get("end_date"),
                "company": m.get("company"),
                "skills": m.get("skills", []),
                "source": "bulk_reanalyse",
            },
        })
    try:
        inject(headers)
        await hc.post(
            f"{ITEMS_API_URL.rstrip('/')}/bulk",
            json={"items": items_payload},
            headers=headers,
            timeout=30.0,
        )
    except Exception as e:
        logger.warning(f"[bulk_reanalyse] items_api /bulk user={user_id}: {e}")


async def bg_bulk_reanalyse(service_token: str):
    headers = {"Authorization": f"Bearer {service_token}"}
    inject(headers)

    try:
        await bulk_reanalyse_manager.update_progress(status="building", new_log="Lecture des CVs...")
        async with database.SessionLocal() as db:
            rows = (await db.execute(select(CVProfile.id, CVProfile.raw_content, CVProfile.user_id).order_by(CVProfile.id))).all()

        gemini_model = os.getenv("GEMINI_PRO_MODEL", os.getenv("GEMINI_MODEL"))
        prompt = await _get_cv_extraction_prompt()
        if not prompt:
            await bulk_reanalyse_manager.update_progress(status="error", error="CRITIQUE : prompt d'extraction CV vide")
            return

        tree_context = ""
        try:
            async with httpx.AsyncClient(timeout=10.0) as hc:
                inject({"Authorization": f"Bearer {service_token}"})
                page_res = await hc.get(f"{COMPETENCIES_API_URL.rstrip('/')}/", params={"skip": 0, "limit": 500}, headers=headers, timeout=10.0)
                if page_res.status_code == 200:
                    items = page_res.json().get("items", [])
                    if items:
                        ctx, nb_parents, nb_leaves = build_taxonomy_context(items)
                        tree_context = f"\n\n## TAXONOMY:\n{ctx}"
        except Exception as e:
            logger.warning("[bulk_reanalyse] Taxonomy fetch failed (non-blocking): %s", e)

        full_prompt = prompt + tree_context
        jsonl_lines: list[str] = []
        cv_index: dict[str, tuple[int, int]] = {}
        skipped = 0

        for cv_id, raw_content, user_id in rows:
            if not raw_content or not raw_content.strip():
                skipped += 1
                continue
            id_str = f"cv-{cv_id}"
            jsonl_lines.append(json.dumps({
                "id": id_str,
                "request": {
                    "contents": [{"role": "user", "parts": [{"text": f"{full_prompt}\n\nRESUME:\n{raw_content[:100000]}"}]}],
                    "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json", "responseSchema": _CV_RESPONSE_SCHEMA},
                },
            }))
            cv_index[id_str] = (cv_id, user_id)

        await bulk_reanalyse_manager.update_progress(skipped_count_inc=skipped, new_log=f"JSONL: {len(jsonl_lines)} CVs.")
        if not jsonl_lines:
            await bulk_reanalyse_manager.update_progress(status="error", error="Aucun CV")
            return

        await bulk_reanalyse_manager.update_progress(status="uploading", new_log="Upload GCS...")
        ts = int(time.time())
        blob_input = f"bulk-reanalyse/input/{ts}.jsonl"
        blob_output_prefix = f"bulk-reanalyse/output/{ts}/"
        input_uri = f"gs://{BATCH_GCS_BUCKET}/{blob_input}"
        dest_uri = f"gs://{BATCH_GCS_BUCKET}/{blob_output_prefix}"

        try:
            gcs_client = gcs_storage.Client()
            bucket = gcs_client.bucket(BATCH_GCS_BUCKET)
            blob = bucket.blob(blob_input)
            blob.upload_from_string("\n".join(jsonl_lines), content_type="application/jsonlines")
            await bulk_reanalyse_manager.update_progress(dest_uri=dest_uri, new_log=f"Upload OK: {input_uri}")
        except Exception as e:
            await bulk_reanalyse_manager.update_progress(status="error", error=f"Échec GCS: {e}")
            return

        if not vertex_batch_client:
            await bulk_reanalyse_manager.update_progress(status="error", error="vertex_batch_client non initialisé.")
            return

        try:
            job = await asyncio.to_thread(vertex_batch_client.batches.create, model=gemini_model, src=input_uri, config={"display_name": "cv-bulk-reanalyse", "dest": dest_uri})
            await bulk_reanalyse_manager.update_progress(status="batch_running", batch_job_id=job.name, new_log=f"Vertex Job: {job.name}")
        except Exception as e:
            await bulk_reanalyse_manager.update_progress(status="error", error=f"Vertex create: {e}")
            return

        while True:
            await asyncio.sleep(30)
            try:
                job = await asyncio.to_thread(vertex_batch_client.batches.get, name=job.name)
            except Exception as e:
                logger.warning("[bulk_reanalyse] Vertex job poll error (retrying): %s", e)
                continue

            state_name = job.state.name if hasattr(job.state, "name") else str(job.state)
            if state_name == "JOB_STATE_SUCCEEDED":
                await bulk_reanalyse_manager.update_progress(new_log="Vertex Terminé.")
                break
            if state_name in ("JOB_STATE_FAILED", "JOB_STATE_CANCELLED"):
                await bulk_reanalyse_manager.update_progress(status="error", error=f"Vertex {state_name}.")
                return

        await bulk_reanalyse_manager.update_progress(status="applying", new_log=f"Apply de {len(cv_index)} CVs...")

        results = []
        try:
            gcs_client2 = gcs_storage.Client()
            bucket2 = gcs_client2.bucket(BATCH_GCS_BUCKET)
            blobs = await asyncio.to_thread(list, bucket2.list_blobs(prefix=blob_output_prefix))
            for out_blob in blobs:
                if not out_blob.name.endswith(".jsonl"): continue
                content = await asyncio.to_thread(out_blob.download_as_text)
                for line in content.splitlines():
                    if not line.strip(): continue
                    try:
                        record = json.loads(line)
                        key = record.get("id") or record.get("key", "")
                        if key not in cv_index: continue
                        cv_id, user_id = cv_index[key]
                        candidates = record.get("response", {}).get("candidates", [])
                        if not candidates: continue
                        text = _clean_llm_json(candidates[0].get("content", {}).get("parts", [{}])[0].get("text", ""))
                        results.append((cv_id, user_id, json.loads(text), record.get("response", {}).get("usageMetadata", {})))
                    except Exception as e:
                        logger.warning("[bulk_reanalyse] Skipping malformed GCS result line: %s", e)
        except Exception as e:
            await bulk_reanalyse_manager.update_progress(status="error", error=f"GCS read: {e}")
            return

        await scale_bulk_dependencies(min_instances=BULK_SCALE_MIN_INSTANCES)

        # ── Readiness wait : s'assurer que les instances scalées sont prêtes ────
        # Le LRO Cloud Run update_service est asynchrone — les instances peuvent
        # prendre 30-120s pour démarrer et passer le health check AlloyDB IAM.
        # On poll /health sur chaque service jusqu'à 200 (max 120s, step 10s).
        _scale_targets = [COMPETENCIES_API_URL, ITEMS_API_URL]
        _readiness_timeout = int(os.getenv("BULK_READINESS_TIMEOUT_S", "120"))
        _readiness_step = 10
        for _svc_url in _scale_targets:
            _health_url = f"{_svc_url.rstrip('/')}/health"
            _waited = 0
            while _waited < _readiness_timeout:
                try:
                    async with httpx.AsyncClient(timeout=5.0) as _hc:
                        _r = await _hc.get(_health_url)
                    if _r.status_code == 200:
                        logger.info(f"[bulk_readiness] {_health_url} → OK ({_waited}s attendu)")
                        break
                    logger.debug(f"[bulk_readiness] {_health_url} → {_r.status_code}, retry in {_readiness_step}s")
                except Exception as _e:
                    logger.debug(f"[bulk_readiness] {_health_url} → {_e}, retry in {_readiness_step}s")
                await asyncio.sleep(_readiness_step)
                _waited += _readiness_step
            else:
                logger.warning(f"[bulk_readiness] {_health_url} non disponible après {_readiness_timeout}s — on continue quand même (retry intégré)")
        await bulk_reanalyse_manager.update_progress(
            new_log=f"Services prêts — démarrage pipeline {len(results)} CVs (embed={BULK_EMBED_SEMAPHORE} / apply={BULK_APPLY_SEMAPHORE})."
        )

        # ── Pipeline producteur/consommateur (Queue) ──────────────────────────
        # Architecture : BULK_EMBED_SEMAPHORE workers calculent les embeddings et
        # poussent dans la Queue. BULK_APPLY_SEMAPHORE workers consomment et appliquent.
        # L'apply démarre dès le 1er embedding disponible — pas d'attente upfront.
        # Queue(maxsize=BULK_APPLY_SEMAPHORE*2) crée une back-pressure naturelle.
        embedding_model = os.getenv("GEMINI_EMBEDDING_MODEL")
        _SENTINEL = object()
        apply_queue: asyncio.Queue = asyncio.Queue(maxsize=BULK_APPLY_SEMAPHORE * 2)
        sem_embed = asyncio.Semaphore(BULK_EMBED_SEMAPHORE)

        async def _embed_and_enqueue(cv_id: int, user_id: int, structured_cv: dict, usage: dict) -> None:
            async with sem_embed:
                embedding = None
                try:
                    distilled = _build_distilled_content(structured_cv)
                    result = await embed_content_with_retry(client, model=embedding_model, contents=distilled)
                    embedding = result.embeddings[0].values if result and result.embeddings else None
                except Exception as emb_exc:
                    logger.warning(f"[bulk_embed] cv_id={cv_id} échoué: {emb_exc}")
                await apply_queue.put((cv_id, user_id, structured_cv, usage, embedding))

        async def _producer() -> None:
            embed_tasks = [_embed_and_enqueue(cv_id, uid, scv, usage) for cv_id, uid, scv, usage in results]
            await asyncio.gather(*embed_tasks, return_exceptions=True)
            for _ in range(BULK_APPLY_SEMAPHORE):
                await apply_queue.put(_SENTINEL)

        async def _apply_with_retry(hc: httpx.AsyncClient, method: str, url: str, **kwargs) -> httpx.Response:
            """Retry exponentiel sur 5xx/timeout."""
            for attempt in range(4):
                try:
                    resp = await getattr(hc, method)(url, **kwargs)
                    if resp.status_code < 500:
                        return resp
                    logger.warning(f"[bulk_apply] {method.upper()} {url} → {resp.status_code}, retry {attempt+1}/4")
                except (httpx.TimeoutException, httpx.RemoteProtocolError) as exc:
                    logger.warning(f"[bulk_apply] {method.upper()} {url} → {type(exc).__name__}, retry {attempt+1}/4")
                await asyncio.sleep(2 ** attempt)
            raise RuntimeError(f"[bulk_apply] Échec 4 tentatives: {method.upper()} {url}")

        async def _consumer() -> None:
            while True:
                item = await apply_queue.get()
                if item is _SENTINEL:
                    apply_queue.task_done()
                    break
                cv_id, user_id, structured_cv, usage, embedding_values = item
                try:
                    comp_keywords = [c.get("name") for c in structured_cv.get("competencies", []) if c.get("name")]
                    async with database.SessionLocal() as db:
                        await db.execute(
                            sa_update(CVProfile).where(CVProfile.id == cv_id).values(
                                current_role=structured_cv.get("current_role"),
                                years_of_experience=structured_cv.get("years_of_experience"),
                                summary=_coerce_to_str(structured_cv.get("summary")),
                                competencies_keywords=comp_keywords,
                                missions=structured_cv.get("missions", []),
                                educations=structured_cv.get("educations", []),
                                extracted_competencies=structured_cv.get("competencies", []),
                                semantic_embedding=embedding_values,
                            )
                        )
                        await db.commit()

                    # Copie locale des headers pour éviter la race condition OTel
                    req_headers = dict(headers)
                    inject(req_headers)
                    async with httpx.AsyncClient(timeout=30.0) as hc:
                        await _apply_with_retry(hc, "delete",
                            f"{COMPETENCIES_API_URL.rstrip('/')}/user/{user_id}/evaluations", headers=req_headers)
                        await _apply_with_retry(hc, "delete",
                            f"{COMPETENCIES_API_URL.rstrip('/')}/user/{user_id}/clear", headers=req_headers)
                        comps_payload = structured_cv.get("competencies", [])
                        if comps_payload:
                            await _apply_with_retry(hc, "post",
                                f"{COMPETENCIES_API_URL.rstrip('/')}/user/{user_id}/assign/bulk",
                                json={"competencies": comps_payload}, headers=req_headers, timeout=120.0)
                        await hc.delete(
                            f"{ITEMS_API_URL.rstrip('/')}/user/{user_id}/items", headers=req_headers)
                        await _post_missions_bulk(hc, user_id, structured_cv.get("missions", []), req_headers)

                    input_tok = usage.get("promptTokenCount", 0)
                    output_tok = usage.get("candidatesTokenCount", 0)
                    asyncio.create_task(log_finops(
                        user_email=f"user_{user_id}", action="bulk_reanalyse_cv", model=gemini_model,
                        usage_metadata={"prompt_token_count": input_tok, "candidates_token_count": output_tok},
                        metadata={"cv_id": cv_id, "user_id": user_id}, auth_token=service_token, is_batch=True,
                    ))
                    await bulk_reanalyse_manager.update_progress(
                        applying_current_inc=1, tokens_input_inc=input_tok, tokens_output_inc=output_tok
                    )
                except Exception as e:
                    err_type = type(e).__name__
                    err_msg = str(e) or repr(e)
                    logger.error(f"[bulk_reanalyse] cv_id={cv_id} [{err_type}] {err_msg}\n{traceback.format_exc()}")
                    await bulk_reanalyse_manager.update_progress(
                        error_count_inc=1, cv_error=f"CV {cv_id} (user {user_id}): [{err_type}] {err_msg}",
                        applying_current_inc=1,
                    )
                finally:
                    apply_queue.task_done()

        consumers = [asyncio.create_task(_consumer()) for _ in range(BULK_APPLY_SEMAPHORE)]
        await asyncio.gather(_producer(), *consumers, return_exceptions=True)

        await bulk_reanalyse_manager.update_progress(status="completed", new_log="Pipeline terminé.")
        await scale_bulk_dependencies(min_instances=0)

    except Exception as e:
        logger.error(f"[bulk_reanalyse] Erreur fatale: {e}", exc_info=True)
        await bulk_reanalyse_manager.update_progress(status="error", error=f"Fatal: {e}")
        await scale_bulk_dependencies(min_instances=0)


async def bg_retry_apply(service_token: str, dest_uri: str) -> None:
    """Rejoue uniquement la phase apply depuis les résultats GCS d'un batch Vertex existant.

    Contrairement à bg_bulk_reanalyse, cette fonction :
    - Ne relance PAS Vertex AI (économise ~35min + coût batch)
    - Lit directement les fichiers .jsonl depuis dest_uri dans GCS
    - Reconstruit le cv_index depuis la DB (CVProfile.id + user_id)
    - Applique les résultats via le même pipeline embed→apply que bg_bulk_reanalyse

    Prérequis : dest_uri doit correspondre à un job Vertex AI terminé avec succès.
    """
    headers = {"Authorization": f"Bearer {service_token}"}
    inject(headers)

    try:
        # 1. Reconstruire le cv_index depuis la DB
        async with database.SessionLocal() as db:
            rows = (await db.execute(
                select(CVProfile.id, CVProfile.user_id).order_by(CVProfile.id)
            )).all()
        cv_index: dict[str, tuple[int, int]] = {f"cv-{cv_id}": (cv_id, user_id) for cv_id, user_id in rows}

        await bulk_reanalyse_manager.update_progress(
            new_log=f"[retry-apply] cv_index reconstruit: {len(cv_index)} CVs connus."
        )

        # 2. Lire les résultats GCS
        bucket_name = dest_uri.replace("gs://", "").split("/")[0]
        prefix = dest_uri.replace(f"gs://{bucket_name}/", "")
        results = []
        try:
            gcs_client = gcs_storage.Client()
            bucket = gcs_client.bucket(bucket_name)
            blobs = await asyncio.to_thread(list, bucket.list_blobs(prefix=prefix))
            for out_blob in blobs:
                if not out_blob.name.endswith(".jsonl"):
                    continue
                content = await asyncio.to_thread(out_blob.download_as_text)
                for line in content.splitlines():
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                        key = record.get("id") or record.get("key", "")
                        if key not in cv_index:
                            continue
                        cv_id, user_id = cv_index[key]
                        candidates = record.get("response", {}).get("candidates", [])
                        if not candidates:
                            continue
                        text = _clean_llm_json(
                            candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        )
                        results.append((
                            cv_id, user_id,
                            json.loads(text),
                            record.get("response", {}).get("usageMetadata", {}),
                        ))
                    except Exception as parse_exc:
                        logger.warning(f"[retry-apply] Ligne GCS non parseable: {parse_exc}")
        except Exception as e:
            await bulk_reanalyse_manager.update_progress(status="error", error=f"[retry-apply] GCS read: {e}")
            return

        await bulk_reanalyse_manager.update_progress(
            new_log=f"[retry-apply] {len(results)} CVs chargés depuis GCS."
        )
        if not results:
            await bulk_reanalyse_manager.update_progress(
                status="error", error="[retry-apply] Aucun résultat GCS valide trouvé."
            )
            return

        # 3. Scaler les dépendances et attendre la readiness
        await scale_bulk_dependencies(min_instances=BULK_SCALE_MIN_INSTANCES)
        _readiness_timeout = int(os.getenv("BULK_READINESS_TIMEOUT_S", "120"))
        _readiness_step = 10
        for _svc_url in [COMPETENCIES_API_URL, ITEMS_API_URL]:
            _health_url = f"{_svc_url.rstrip('/')}/health"
            _waited = 0
            while _waited < _readiness_timeout:
                try:
                    async with httpx.AsyncClient(timeout=5.0) as _hc:
                        _r = await _hc.get(_health_url)
                    if _r.status_code == 200:
                        break
                    logger.debug(f"[retry-apply] {_health_url} → {_r.status_code}, retry in {_readiness_step}s")
                except Exception as _e:
                    logger.debug(f"[retry-apply] {_health_url} → {_e}, retry in {_readiness_step}s")
                await asyncio.sleep(_readiness_step)
                _waited += _readiness_step
            else:
                logger.warning(f"[retry-apply] {_health_url} non dispo après {_readiness_timeout}s — on continue")

        await bulk_reanalyse_manager.update_progress(
            new_log=f"[retry-apply] Services prêts — apply de {len(results)} CVs."
        )

        # 4. Pipeline embed → apply (même logique que bg_bulk_reanalyse)
        embedding_model = os.getenv("GEMINI_EMBEDDING_MODEL")
        _SENTINEL = object()
        apply_queue: asyncio.Queue = asyncio.Queue(maxsize=BULK_APPLY_SEMAPHORE * 2)
        sem_embed = asyncio.Semaphore(BULK_EMBED_SEMAPHORE)

        async def _embed_and_enqueue(cv_id: int, user_id: int, structured_cv: dict, usage: dict) -> None:
            async with sem_embed:
                embedding = None
                try:
                    distilled = _build_distilled_content(structured_cv)
                    result = await embed_content_with_retry(client, model=embedding_model, contents=distilled)
                    embedding = result.embeddings[0].values if result and result.embeddings else None
                except Exception as emb_exc:
                    logger.warning(f"[retry-apply] embed cv_id={cv_id}: {emb_exc}")
                await apply_queue.put((cv_id, user_id, structured_cv, usage, embedding))

        async def _producer() -> None:
            embed_tasks = [_embed_and_enqueue(cv_id, uid, scv, usage) for cv_id, uid, scv, usage in results]
            await asyncio.gather(*embed_tasks, return_exceptions=True)
            for _ in range(BULK_APPLY_SEMAPHORE):
                await apply_queue.put(_SENTINEL)

        async def _apply_with_retry(hc: httpx.AsyncClient, method: str, url: str, **kwargs) -> httpx.Response:
            for attempt in range(4):
                try:
                    resp = await getattr(hc, method)(url, **kwargs)
                    if resp.status_code < 500:
                        return resp
                    logger.warning(f"[retry-apply] {method.upper()} {url} → {resp.status_code}, retry {attempt+1}/4")
                except (httpx.TimeoutException, httpx.RemoteProtocolError) as exc:
                    logger.warning(f"[retry-apply] {method.upper()} {url} → {type(exc).__name__}, retry {attempt+1}/4")
                await asyncio.sleep(2 ** attempt)
            raise RuntimeError(f"[retry-apply] Échec 4 tentatives: {method.upper()} {url}")

        async def _consumer() -> None:
            while True:
                item = await apply_queue.get()
                if item is _SENTINEL:
                    apply_queue.task_done()
                    break
                cv_id, user_id, structured_cv, usage, embedding_values = item
                try:
                    comp_keywords = [c.get("name") for c in structured_cv.get("competencies", []) if c.get("name")]
                    async with database.SessionLocal() as db:
                        await db.execute(
                            sa_update(CVProfile).where(CVProfile.id == cv_id).values(
                                current_role=structured_cv.get("current_role"),
                                years_of_experience=structured_cv.get("years_of_experience"),
                                summary=_coerce_to_str(structured_cv.get("summary")),
                                competencies_keywords=comp_keywords,
                                missions=structured_cv.get("missions", []),
                                educations=structured_cv.get("educations", []),
                                extracted_competencies=structured_cv.get("competencies", []),
                                semantic_embedding=embedding_values,
                            )
                        )
                        await db.commit()

                    req_headers = dict(headers)
                    inject(req_headers)
                    async with httpx.AsyncClient(timeout=30.0) as hc:
                        await _apply_with_retry(hc, "delete",
                            f"{COMPETENCIES_API_URL.rstrip('/')}/user/{user_id}/evaluations", headers=req_headers)
                        await _apply_with_retry(hc, "delete",
                            f"{COMPETENCIES_API_URL.rstrip('/')}/user/{user_id}/clear", headers=req_headers)
                        comps_payload = structured_cv.get("competencies", [])
                        if comps_payload:
                            await _apply_with_retry(hc, "post",
                                f"{COMPETENCIES_API_URL.rstrip('/')}/user/{user_id}/assign/bulk",
                                json={"competencies": comps_payload}, headers=req_headers, timeout=120.0)
                        await hc.delete(
                            f"{ITEMS_API_URL.rstrip('/')}/user/{user_id}/items", headers=req_headers)
                        await _post_missions_bulk(hc, user_id, structured_cv.get("missions", []), req_headers)

                    input_tok = usage.get("promptTokenCount", 0)
                    output_tok = usage.get("candidatesTokenCount", 0)
                    asyncio.create_task(log_finops(
                        user_email=f"user_{user_id}", action="retry_apply_cv",
                        model="none",
                        usage_metadata={"prompt_token_count": input_tok, "candidates_token_count": output_tok},
                        metadata={"cv_id": cv_id, "user_id": user_id}, auth_token=service_token, is_batch=True,
                    ))
                    await bulk_reanalyse_manager.update_progress(applying_current_inc=1)
                except Exception as e:
                    err_type = type(e).__name__
                    err_msg = str(e) or repr(e)
                    logger.error(f"[retry-apply] cv_id={cv_id} [{err_type}] {err_msg}")
                    await bulk_reanalyse_manager.update_progress(
                        error_count_inc=1,
                        cv_error=f"CV {cv_id} (user {user_id}): [{err_type}] {err_msg}",
                        applying_current_inc=1,
                    )
                finally:
                    apply_queue.task_done()

        consumers = [asyncio.create_task(_consumer()) for _ in range(BULK_APPLY_SEMAPHORE)]
        await asyncio.gather(_producer(), *consumers, return_exceptions=True)

        await bulk_reanalyse_manager.update_progress(status="completed", new_log="[retry-apply] Pipeline terminé.")
        await scale_bulk_dependencies(min_instances=0)

    except Exception as e:
        logger.error(f"[retry-apply] Erreur fatale: {e}", exc_info=True)
        await bulk_reanalyse_manager.update_progress(status="error", error=f"[retry-apply] Fatal: {e}")
        await scale_bulk_dependencies(min_instances=0)

