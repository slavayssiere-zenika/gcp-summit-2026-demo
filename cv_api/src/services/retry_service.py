"""
retry_service.py — Service de retry de la phase apply Vertex AI (sans re-soumission batch).

Extrait de bulk_service.py (God module) — 2026-05-14.

Fonctions exportées :
  - bg_retry_apply(service_token, dest_uri) — Rejoue la phase apply depuis GCS existant
"""

import asyncio
import json
import logging
import os

import httpx

import database
from google.cloud import storage as gcs_storage
from opentelemetry.propagate import inject
from sqlalchemy import update as sa_update
from sqlalchemy.future import select
from src.cvs.bulk_task_state import bulk_reanalyse_manager
from src.cvs.models import CVProfile
from src.gemini_retry import embed_content_with_retry
from src.services.config import (
    BULK_APPLY_SEMAPHORE, BULK_EMBED_SEMAPHORE, BULK_SCALE_MIN_INSTANCES,
    COMPETENCIES_API_URL, ITEMS_API_URL,
    client,
)
from src.services.bulk_helpers import _post_missions_bulk, _resolve_competency_ids
from src.services.finops import log_finops
from src.services.search_service import scale_bulk_dependencies
from src.services.utils import _build_distilled_content, _clean_llm_json, _coerce_to_str

logger = logging.getLogger(__name__)

# Sémaphore partagé importé depuis bulk_service (évite double instanciation)
from src.services.bulk_service import _items_delete_sem  # noqa: E402 (cycle évité par import tardif)


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

        loaded_cv_ids = {cv_id for cv_id, _, _, _ in results}
        all_cv_ids = {cv_id for cv_id, _ in cv_index.values()}
        missing_cv_ids = all_cv_ids - loaded_cv_ids
        await bulk_reanalyse_manager.update_progress(
            new_log=f"[retry-apply] {len(results)} CVs charg\u00e9s depuis GCS."
        )
        if missing_cv_ids:
            sample = sorted(missing_cv_ids)[:20]
            logger.warning(
                "[retry-apply] %d CVs absents des outputs GCS (parsing \u00e9chou\u00e9 ou absents du batch) "
                "| IDs \u00e9chantillon: %s%s",
                len(missing_cv_ids), sample,
                " (+ autres)" if len(missing_cv_ids) > 20 else "",
            )
            await bulk_reanalyse_manager.update_progress(
                new_log=(
                    f"[retry-apply] \u26a0\ufe0f {len(missing_cv_ids)} CVs sans r\u00e9sultat Vertex dans GCS. "
                    f"IDs: {sample}"
                    f"{'...' if len(missing_cv_ids) > 20 else ''}"
                )
            )
        if not results:
            await bulk_reanalyse_manager.update_progress(
                status="error", error="[retry-apply] Aucun r\u00e9sultat GCS valide trouv\u00e9."
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
            """Retry exponentiel sur 429, 5xx et timeouts (voir bg_bulk_reanalyse pour la doc)."""
            import random
            for attempt in range(4):
                try:
                    resp = await getattr(hc, method)(url, **kwargs)
                    if resp.status_code not in (429, 500, 502, 503, 504):
                        return resp
                    wait = min(2 ** attempt + random.uniform(0, 1), 30.0)
                    logger.warning(
                        "[retry-apply] %s %s → %s, retry %d/4 dans %.1fs",
                        method.upper(), url, resp.status_code, attempt + 1, wait,
                    )
                except (httpx.TimeoutException, httpx.RemoteProtocolError) as exc:
                    wait = min(2 ** attempt + random.uniform(0, 1), 30.0)
                    logger.warning(
                        "[retry-apply] %s %s → %s, retry %d/4 dans %.1fs",
                        method.upper(), url, type(exc).__name__, attempt + 1, wait,
                    )
                await asyncio.sleep(wait)
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
