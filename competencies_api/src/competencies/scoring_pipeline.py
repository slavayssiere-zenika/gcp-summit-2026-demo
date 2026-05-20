"""
scoring_pipeline.py — Fonctions async réseau/DB et orchestrateur Vertex AI Batch.

Contient : _fetch_missions_for_user, _prefetch_all_missions,
           _apply_scoring_results, bg_bulk_scoring_vertex.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone

import shared.database as database
import httpx
from google.cloud import storage as gcs_storage
from pydantic import ValidationError
from sqlalchemy.future import select
from src.competencies.bulk_task_state import bulk_scoring_manager
from src.competencies.finops import log_finops
from src.competencies.models import Competency, CompetencyEvaluation, user_competency
from src.competencies.scheduler_control import set_scoring_scheduler_enabled
from src.competencies.scoring_utils import (
    BATCH_GCS_BUCKET,
    CV_API_URL,
    GCP_PROJECT_ID,
    MISSIONS_FETCH_SEMAPHORE,
    SCORING_APPLY_SEMAPHORE,
    VERTEX_BATCH_MODEL,
    VERTEX_LOCATION,
    _build_jsonl_lines,
    _parse_scoring_results_gcs,
)
from shared.schemas.missions import MissionsResponse
from google import genai  # import local pour éviter erreur si non installé

logger = logging.getLogger(__name__)


async def _fetch_missions_for_user(
    user_id: int, headers: dict, sem: asyncio.Semaphore
) -> tuple[int, list]:
    """Récupère les missions d'un user depuis cv_api (avec semaphore de concurrence)."""
    async with sem:
        missions = []
        try:
            async with httpx.AsyncClient(timeout=15.0) as hc:
                skip, limit = 0, 100
                while True:
                    url = (
                        f"{CV_API_URL.rstrip('/')}/user/{user_id}/missions"
                        f"?skip={skip}&limit={limit}"
                    )
                    # Retry sur codes HTTP transitoires (429, 502, 503, 504)
                    res = None
                    for attempt in range(3):
                        res = await hc.get(url, headers=headers)
                        if res.status_code not in (429, 502, 503, 504):
                            break
                        wait = min(2 ** attempt + 0.5, 10.0)
                        logger.warning(
                            "[scoring_pipeline] missions user=%d HTTP %d → retry %d/3 dans %.1fs",
                            user_id, res.status_code, attempt + 1, wait,
                        )
                        await asyncio.sleep(wait)
                    if res.status_code == 200:
                        try:
                            data = MissionsResponse.model_validate(res.json())
                        except ValidationError as ve:
                            logger.error(
                                "[scoring_pipeline] Rupture de contrat API missions",
                                extra={
                                    "user_id": user_id,
                                    "error": str(ve),
                                    "raw_keys": list(res.json().keys()),
                                },
                            )
                            break  # Stopper proprement la pagination
                        missions.extend([m.model_dump() for m in data.items])
                        if len(data.items) < limit:
                            break
                        skip += limit
                    else:
                        logger.warning(
                            f"[scoring_service] missions user={user_id} HTTP {res.status_code}"
                        )
                        break
        except Exception as e:
            logger.warning(f"[scoring_service] missions user={user_id} erreur: {e}")
    return user_id, missions


async def _prefetch_all_missions(user_ids: list[int], headers: dict) -> dict[int, list]:
    """Précharge toutes les missions en parallèle — 1 appel HTTP par user."""
    sem = asyncio.Semaphore(MISSIONS_FETCH_SEMAPHORE)
    tasks = [_fetch_missions_for_user(uid, headers, sem) for uid in user_ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    missions_map: dict[int, list] = {}
    for res in results:
        if isinstance(res, Exception):
            logger.warning(f"[scoring_service] prefetch exception: {res}")
            continue
        uid, missions = res
        missions_map[uid] = missions
    return missions_map


# ── Phase 2 : Construction du JSONL ──────────────────────────────────────────


async def _apply_scoring_results(
    results: list[tuple[int, int, str, float, str]],
) -> tuple[int, int, str]:
    """
    Applique les scores en DB via upsert.
    results : liste de (user_id, comp_id, comp_name, score, justification)
    Retourne (nb_success, nb_errors, sample_error_msg).
    """
    success = 0
    errors = 0
    chunk_size = 200  # 200 items par connexion DB
    sample_error = ""

    async def _process_chunk(chunk: list[tuple[int, int, str, float, str]]):
        nonlocal success, errors, sample_error
        async with database.SessionLocal() as db:
            for user_id, comp_id, _, score, justification in chunk:
                try:
                    stmt = select(CompetencyEvaluation).where(
                        CompetencyEvaluation.user_id == user_id,
                        CompetencyEvaluation.competency_id == comp_id,
                    )
                    ev = (await db.execute(stmt)).scalars().first()
                    if not ev:
                        ev = CompetencyEvaluation(
                            user_id=user_id, competency_id=comp_id
                        )
                        db.add(ev)
                    ev.ai_score = score
                    ev.ai_justification = justification
                    ev.ai_scored_at = datetime.now(timezone.utc).replace(tzinfo=None)
                    ev.scoring_version = "v3-batch"
                    ev.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
                    await db.commit()
                    success += 1
                except Exception as item_e:
                    await db.rollback()
                    if not sample_error:
                        sample_error = str(item_e)
                    logger.error(
                        f"[scoring_service] upsert user={user_id} comp={comp_id}: {item_e}"
                    )
                    errors += 1

    chunks = [results[i: i + chunk_size] for i in range(0, len(results), chunk_size)]  # noqa: E203
    sem = asyncio.Semaphore(SCORING_APPLY_SEMAPHORE)

    async def _sem_worker(chunk: list):
        async with sem:
            await _process_chunk(chunk)

    # Lancement des chunks en parallèle (limité par le sémaphore, donc max N connexions DB)
    await asyncio.gather(*[_sem_worker(c) for c in chunks])

    return success, errors, sample_error


async def bg_bulk_scoring_vertex(
    user_ids: list[int],
    headers: dict,
    delta_only: bool = True,
) -> None:
    """
    Background task principale : pipeline complet de bulk scoring via Vertex AI Batch.
    Appelée depuis router.py en remplacement de _bulk_scoring_all_bg.

    delta_only=True (défaut) : ne score que les compétences sans ai_score (moins coûteuses).
    delta_only=False          : re-score toutes les compétences feuilles assignées.
    """

    if not GCP_PROJECT_ID or not BATCH_GCS_BUCKET:
        await bulk_scoring_manager.update_progress(
            status="error",
            error="GCP_PROJECT_ID ou BATCH_GCS_BUCKET non configuré — scoring Vertex désactivé.",
        )
        return

    if not VERTEX_BATCH_MODEL:
        await bulk_scoring_manager.update_progress(
            status="error",
            error=(
                "VERTEX_BATCH_MODEL non configuré (variable d'environnement absente). "
                "Ajouter VERTEX_BATCH_MODEL dans cr_competencies.tf (ex: gemini-2.5-flash). "
                "Sans ce paramètre, Vertex AI Batch retourne 400 INVALID_ARGUMENT."
            ),
        )
        logger.error(
            "[scoring_pipeline] VERTEX_BATCH_MODEL absent — impossible de soumettre le job Vertex."
        )
        return

    try:
        vertex_client = genai.Client(
            vertexai=True, project=GCP_PROJECT_ID, location=VERTEX_LOCATION
        )
    except Exception as e:
        await bulk_scoring_manager.update_progress(
            status="error", error=f"Init vertex_client: {e}"
        )
        return

    try:
        # Active le Cloud Scheduler keepalive en premier — garantit l'ordre enable→pipeline→disable.
        # Ne pas déléguer au router (background task séparée) : l'ordre d'exécution n'est pas garanti.
        await set_scoring_scheduler_enabled(True)

        # ── Étape 1 : Collecter (user_id, comp_id, comp_name) depuis la DB ──────
        mode_label = "delta (ai_score IS NULL)" if delta_only else "complet (toutes feuilles)"
        await bulk_scoring_manager.update_progress(
            new_log=f"Collecte des compétences — mode {mode_label} pour {len(user_ids)} users..."
        )
        user_comp_list: list[tuple[int, int, str]] = []
        async with database.SessionLocal() as db:
            for uid in user_ids:
                user_comp_select = (
                    select(user_competency.c.competency_id)
                    .where(user_competency.c.user_id == uid)
                )
                leaf_stmt = (
                    select(user_competency.c.competency_id)
                    .where(user_competency.c.user_id == uid)
                    .where(
                        ~select(Competency.id)
                        .where(Competency.parent_id == user_competency.c.competency_id)
                        .where(Competency.id.in_(user_comp_select))
                        .correlate(user_competency)
                        .exists()
                    )
                )
                leaf_ids = (await db.execute(leaf_stmt)).scalars().all()
                if not leaf_ids:
                    continue

                # ── Filtre delta : exclure les compétences déjà scorées ─────────
                if delta_only:
                    already_scored_ids = (
                        await db.execute(
                            select(CompetencyEvaluation.competency_id).where(
                                CompetencyEvaluation.user_id == uid,
                                CompetencyEvaluation.competency_id.in_(leaf_ids),
                                CompetencyEvaluation.ai_score.isnot(None),
                            )
                        )
                    ).scalars().all()
                    leaf_ids = [lid for lid in leaf_ids if lid not in already_scored_ids]
                    if not leaf_ids:
                        continue  # Ce user est déjà entièrement scoré

                comps = (
                    await db.execute(
                        select(Competency.id, Competency.name).where(
                            Competency.id.in_(leaf_ids)
                        )
                    )
                ).all()

                for comp_id, comp_name in comps:
                    user_comp_list.append((uid, comp_id, comp_name))

        total_pairs = len(user_comp_list)
        await bulk_scoring_manager.update_progress(
            new_log=f"Collecte OK : {total_pairs} paires (user × compétence) à scorer."
        )
        if not total_pairs:
            await bulk_scoring_manager.update_progress(
                status="completed",
                new_log="Aucune compétence feuille trouvée — terminé.",
            )
            return

        # ── Étape 2 : Préchargement des missions en parallèle ────────────────────
        await bulk_scoring_manager.update_progress(
            new_log=f"Préchargement des missions pour {len(user_ids)} users (semaphore={MISSIONS_FETCH_SEMAPHORE})..."
        )
        missions_map = await _prefetch_all_missions(user_ids, headers)
        await bulk_scoring_manager.update_progress(
            new_log=f"Missions préchargées : {sum(len(v) for v in missions_map.values())} missions totales."
        )

        # ── Étape 3 : Construire le JSONL ─────────────────────────────────────────
        jsonl_lines, scoring_index, skipped_no_mission = _build_jsonl_lines(
            user_comp_list, missions_map
        )
        await bulk_scoring_manager.update_progress(
            new_log=f"JSONL : {len(jsonl_lines)} requêtes, {skipped_no_mission} ignorés (pas de missions)."
        )
        if not jsonl_lines:
            await bulk_scoring_manager.update_progress(
                status="completed", new_log="Aucune requête à soumettre — terminé."
            )
            return

        # ── Étape 4 : Upload GCS ──────────────────────────────────────────────────
        await bulk_scoring_manager.update_progress(
            status="uploading", new_log="Upload JSONL vers GCS..."
        )
        ts = int(time.time())
        blob_input = f"bulk-scoring/input/{ts}.jsonl"
        blob_output_prefix = f"bulk-scoring/output/{ts}/"
        input_uri = f"gs://{BATCH_GCS_BUCKET}/{blob_input}"
        dest_uri = f"gs://{BATCH_GCS_BUCKET}/{blob_output_prefix}"

        try:
            gcs_client = gcs_storage.Client()
            bucket = gcs_client.bucket(BATCH_GCS_BUCKET)
            blob = bucket.blob(blob_input)
            blob.upload_from_string(
                "\n".join(jsonl_lines), content_type="application/jsonlines"
            )
            await bulk_scoring_manager.update_progress(
                new_log=f"Upload OK : {input_uri} ({len(jsonl_lines)} lignes)"
            )
        except Exception as e:
            await bulk_scoring_manager.update_progress(
                status="error", error=f"GCS upload: {e}"
            )
            return

        # ── Étape 5 : Soumettre le job Vertex AI Batch ───────────────────────────
        try:
            job = await asyncio.to_thread(
                vertex_client.batches.create,
                model=VERTEX_BATCH_MODEL,
                src=input_uri,
                config={
                    "display_name": f"competencies-bulk-scoring-{ts}",
                    "dest": dest_uri,
                },
            )
            vertex_console_url = (
                f"https://console.cloud.google.com/vertex-ai/batch-predictions"
                f"?project={GCP_PROJECT_ID}"
            )
            await bulk_scoring_manager.update_progress(
                status="batch_running",
                batch_job_id=job.name,
                dest_uri=dest_uri,
                new_log=(
                    f"Job Vertex AI soumis : {job.name} (model={VERTEX_BATCH_MODEL}) "
                    f"| Suivi : {vertex_console_url}"
                ),
            )
            logger.info(
                f"[scoring_service] Vertex batch job créé : {job.name} "
                f"(model={VERTEX_BATCH_MODEL}) | Console : {vertex_console_url}"
            )

        except Exception as e:
            await bulk_scoring_manager.update_progress(
                status="error", error=f"Vertex create: {e}"
            )
            return

        # ── Étape 6 : Poll jusqu'à la fin du job ─────────────────────────────────
        poll_count = 0
        state_labels = {
            "JOB_STATE_QUEUED": "En file d'attente Vertex AI…",
            "JOB_STATE_PENDING": "Démarrage du job Vertex AI…",
            "JOB_STATE_RUNNING": "Traitement en cours par Vertex AI…",
            "JOB_STATE_SUCCEEDED": "Terminé avec succès ✅",
            "JOB_STATE_FAILED": "Échec ❌",
            "JOB_STATE_CANCELLED": "Annulé ⛔",
        }
        while True:
            await asyncio.sleep(30)
            poll_count += 1
            try:
                job = await asyncio.to_thread(vertex_client.batches.get, name=job.name)
            except Exception as poll_e:
                logger.warning(f"[scoring_service] poll erreur: {poll_e}")
                await bulk_scoring_manager.update_progress(
                    new_log=f"Poll #{poll_count} — erreur réseau : {poll_e}"
                )
                continue

            state_name = (
                job.state.name if hasattr(job.state, "name") else str(job.state)
            )
            label = state_labels.get(state_name, state_name)
            logger.info(
                f"[scoring_service] job state={state_name} (poll #{poll_count})"
            )
            await bulk_scoring_manager.update_progress(
                new_log=f"[Poll #{poll_count}] {label} (état Vertex : {state_name})"
            )
            if state_name == "JOB_STATE_SUCCEEDED":
                await bulk_scoring_manager.update_progress(
                    new_log="Vertex Batch terminé avec succès."
                )
                break

            if state_name in ("JOB_STATE_FAILED", "JOB_STATE_CANCELLED"):
                await bulk_scoring_manager.update_progress(
                    status="error", error=f"Vertex job {state_name}."
                )
                return

        # ── Étape 7 : Lire les résultats GCS ─────────────────────────────────────
        await bulk_scoring_manager.update_progress(
            status="applying", new_log=f"Lecture des résultats GCS ({dest_uri})..."
        )
        raw_lines: list[str] = []
        try:
            gcs_client2 = gcs_storage.Client()
            bucket2 = gcs_client2.bucket(BATCH_GCS_BUCKET)
            blobs = await asyncio.to_thread(
                list, bucket2.list_blobs(prefix=blob_output_prefix)
            )
            for out_blob in blobs:
                if not out_blob.name.endswith(".jsonl"):
                    continue
                content = await asyncio.to_thread(out_blob.download_as_text)
                raw_lines.extend(content.splitlines())
        except Exception as e:
            await bulk_scoring_manager.update_progress(
                status="error", error=f"GCS read: {e}"
            )
            return

        results, user_usage = _parse_scoring_results_gcs(raw_lines, scoring_index)
        await bulk_scoring_manager.update_progress(
            new_log=f"Résultats parsés : {len(results)} scores valides sur {len(jsonl_lines)} soumis."
        )

        # ── Étape 7.5 : Log FinOps ────────────────────────────────────────────────
        auth_header = headers.get("Authorization", "")
        service_token = (
            auth_header.removeprefix("Bearer ").strip() if auth_header else ""
        )
        for uid, usage in user_usage.items():
            asyncio.create_task(
                log_finops(
                    user_email=f"user_{uid}",
                    action="bulk_scoring_vertex",
                    model=VERTEX_BATCH_MODEL,
                    usage_metadata=usage,
                    metadata={
                        "user_id": uid,
                        "scores_count": sum(1 for r in results if r[0] == uid),
                    },
                    auth_token=service_token,
                    is_batch=True,
                )
            )

        # ── Étape 8 : Apply en DB ─────────────────────────────────────────────────
        await bulk_scoring_manager.update_progress(
            new_log=f"Écriture en DB de {len(results)} scores..."
        )
        nb_success, nb_errors, sample_err = await _apply_scoring_results(results)

        # Scores minimaux (1.0) pour les users sans mission
        if skipped_no_mission > 0:
            await bulk_scoring_manager.update_progress(
                new_log=f"{skipped_no_mission} paires ignorées (aucune mission dans CV) — score minimal 1.0 non appliqué automatiquement (relancer avec missions disponibles)."  # noqa: E501
            )

        final_status = "error" if nb_errors > 0 else "completed"

        log_msg = (
            f"Pipeline terminé — {nb_success} scores appliqués, "
            f"{nb_errors} erreurs, {skipped_no_mission} ignorés."
        )
        if sample_err:
            log_msg += f" Raison de l'erreur: {sample_err[:150]}..."

        await bulk_scoring_manager.update_progress(
            status=final_status,
            processed_inc=len(user_ids),
            success_inc=nb_success,
            error_count_inc=nb_errors,
            new_log=log_msg,
        )

        logger.info(
            f"[scoring_service] Terminé — {nb_success} scores, {nb_errors} erreurs, "
            f"{skipped_no_mission} ignorés."
        )
        # Pipeline terminé avec succès — pause le Cloud Scheduler keepalive
        await set_scoring_scheduler_enabled(False)

    except Exception as e:
        logger.error(f"[scoring_service] Erreur fatale: {e}", exc_info=True)
        await bulk_scoring_manager.update_progress(status="error", error=f"Fatal: {e}")
        # Pipeline en erreur — pause le Cloud Scheduler keepalive
        await set_scoring_scheduler_enabled(False)
