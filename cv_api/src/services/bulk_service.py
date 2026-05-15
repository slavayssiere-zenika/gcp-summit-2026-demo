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

import database
import httpx
from google.cloud import storage as gcs_storage
from opentelemetry.propagate import inject
from pydantic import ValidationError
from shared.schemas.pagination import PaginationResponse
from sqlalchemy import update as sa_update
from sqlalchemy.future import select
from src.cvs.bulk_task_state import bulk_reanalyse_manager
from src.cvs.models import CVProfile
from src.gemini_retry import embed_content_with_retry
from src.services.config import (BATCH_GCS_BUCKET,
                                 BULK_APPLY_SEMAPHORE, BULK_EMBED_SEMAPHORE,
                                 BULK_SCALE_MIN_INSTANCES,
                                 COMPETENCIES_API_URL, ITEMS_API_URL,
                                 ITEMS_DELETE_SEMAPHORE,
                                 client,
                                 vertex_batch_client)
from src.services.finops import log_finops
from src.services.bulk_helpers import (  # noqa: F401 — ré-exportation pour rétrocompatibilité
    _acquire_service_token, _get_cv_extraction_prompt,
    _resolve_competency_ids, _post_missions_bulk,
)
from src.services.retry_service import bg_retry_apply  # noqa: F401
from src.services.search_service import scale_bulk_dependencies
from src.services.utils import (_CV_RESPONSE_SCHEMA, _build_distilled_content,
                                _clean_llm_json, _coerce_to_str,
                                build_taxonomy_context)

logger = logging.getLogger(__name__)

# Sémaphore global de concurrence pour les DELETE /user/{id}/items vers items-api.
# Partagé entre bg_bulk_reanalyse et bg_retry_apply pour éviter la saturation
# du pool AlloyDB de items-api-prd pendant les phases apply en parallèle.
# Valeur : ITEMS_DELETE_SEMAPHORE (défaut 2 — override via env var).
_items_delete_sem: asyncio.Semaphore = asyncio.Semaphore(ITEMS_DELETE_SEMAPHORE)


async def bg_bulk_reanalyse(service_token: str, cv_ids_filter: list[int] | None = None):
    headers = {"Authorization": f"Bearer {service_token}"}
    inject(headers)

    try:
        if cv_ids_filter:
            log_scope = f"Lecture de {len(cv_ids_filter)} CVs ciblés (filtre cv_ids)..."
        else:
            log_scope = "Lecture des CVs..."
        await bulk_reanalyse_manager.update_progress(status="building", new_log=log_scope)
        async with database.SessionLocal() as db:
            stmt = select(CVProfile.id, CVProfile.raw_content, CVProfile.user_id).order_by(CVProfile.id)
            if cv_ids_filter:
                stmt = stmt.where(CVProfile.id.in_(cv_ids_filter))
            rows = (await db.execute(stmt)).all()

        gemini_model = os.getenv("GEMINI_PRO_MODEL", os.getenv("GEMINI_MODEL"))
        prompt = await _get_cv_extraction_prompt()
        if not prompt:
            await bulk_reanalyse_manager.update_progress(status="error", error="CRITIQUE : prompt d'extraction CV vide")
            return

        tree_context = ""
        try:
            async with httpx.AsyncClient(timeout=10.0) as hc:
                inject({"Authorization": f"Bearer {service_token}"})
                page_res = await hc.get(
                    f"{COMPETENCIES_API_URL.rstrip('/')}/",
                    params={"skip": 0, "limit": 500},
                    headers=headers,
                    timeout=10.0,
                )
                if page_res.status_code == 200:
                    try:
                        page_data = PaginationResponse[dict].model_validate(page_res.json())
                        items = page_data.items
                    except ValidationError as ve:
                        logger.warning(
                            "[bulk_reanalyse] Rupture de contrat API competencies (taxonomy non chargée)",
                            extra={"error": str(ve), "raw_keys": list(page_res.json().keys())},
                        )
                        items = []
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
                    "contents": [{
                        "role": "user",
                        "parts": [{"text": f"{full_prompt}\n\nRESUME:\n{raw_content[:100000]}"}],
                    }],
                    "generationConfig": {
                        "temperature": 0.1,
                        "responseMimeType": "application/json",
                        "responseSchema": _CV_RESPONSE_SCHEMA,
                    },
                },
            }))
            cv_index[id_str] = (cv_id, user_id)

        await bulk_reanalyse_manager.update_progress(
            skipped_count_inc=skipped, new_log=f"JSONL: {len(jsonl_lines)} CVs."
        )
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
            job = await asyncio.to_thread(
                vertex_batch_client.batches.create,
                model=gemini_model,
                src=input_uri,
                config={"display_name": "cv-bulk-reanalyse", "dest": dest_uri},
            )
            await bulk_reanalyse_manager.update_progress(
                status="batch_running", batch_job_id=job.name, new_log=f"Vertex Job: {job.name}"
            )
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
                        text = _clean_llm_json(candidates[0].get("content", {}).get("parts", [{}])[0].get("text", ""))
                        results.append((cv_id, user_id, json.loads(text), record.get(
                            "response", {}).get("usageMetadata", {})))
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
                logger.warning(
                    "[bulk_readiness] %s non disponible après %ss — on continue quand même (retry intégré)",
                    _health_url, _readiness_timeout,
                )
        await bulk_reanalyse_manager.update_progress(
            new_log=(
                f"Services prêts — démarrage pipeline {len(results)} CVs "
                f"(embed={BULK_EMBED_SEMAPHORE} / apply={BULK_APPLY_SEMAPHORE})."
            )
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
            """Retry exponentiel sur 429 (pool saturé), 5xx et timeouts.

            Le 429 est explicitement inclus : competencies_api le retourne quand
            son semaphore ASSIGN_BULK_SEMAPHORE est plein, signalant une surcharge
            transitoire du pool DB. Un retry après backoff suffit à résoudre.
            Jitter aléatoire : évite le thundering herd quand plusieurs instances
            retentent simultanément après un pic d'import massif.
            """
            import random
            for attempt in range(4):
                try:
                    resp = await getattr(hc, method)(url, **kwargs)
                    if resp.status_code not in (429, 500, 502, 503, 504):
                        return resp
                    wait = min(2 ** attempt + random.uniform(0, 1), 30.0)
                    logger.warning(
                        "[bulk_apply] %s %s → %s, retry %d/4 dans %.1fs",
                        method.upper(), url, resp.status_code, attempt + 1, wait,
                    )
                except (httpx.TimeoutException, httpx.RemoteProtocolError) as exc:
                    wait = min(2 ** attempt + random.uniform(0, 1), 30.0)
                    logger.warning(
                        "[bulk_apply] %s %s → %s, retry %d/4 dans %.1fs",
                        method.upper(), url, type(exc).__name__, attempt + 1, wait,
                    )
                await asyncio.sleep(wait)
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
                                # Réinitialise les erreurs historiques : un apply réussi = profil sain
                                processing_errors=[],
                                # BUG 4 fix : score non disponible en Vertex Batch
                                # (pas d'embedding raw pour cosine sim) — reset à None
                                extraction_reliability_score=None,
                            )
                        )
                        await db.commit()

                    req_headers = dict(headers)
                    inject(req_headers)
                    async with httpx.AsyncClient(timeout=30.0) as hc:
                        await _apply_with_retry(hc, "delete",
                                                f"{COMPETENCIES_API_URL.rstrip('/')}/user/{user_id}/evaluations",
                                                headers=req_headers)
                        await _apply_with_retry(hc, "delete",
                                                f"{COMPETENCIES_API_URL.rstrip('/')}/user/{user_id}/clear",
                                                headers=req_headers)
                        comps_payload = structured_cv.get("competencies", [])
                        if comps_payload:
                            competency_ids = await _resolve_competency_ids(
                                comps_payload, hc, req_headers
                            )
                            if competency_ids:
                                await _apply_with_retry(
                                    hc, "post",
                                    f"{COMPETENCIES_API_URL.rstrip('/')}/user/{user_id}/assign/bulk",
                                    json={"competency_ids": competency_ids},
                                    headers=req_headers, timeout=120.0,
                                )
                        async with _items_delete_sem:
                            await _apply_with_retry(
                                hc, "delete",
                                f"{ITEMS_API_URL.rstrip('/')}/user/{user_id}/items",
                                headers=req_headers,
                            )
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
