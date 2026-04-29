"""
scoring_service.py — Pipeline de bulk scoring IA des compétences via Vertex AI Batch.

Remplace le pipeline séquentiel (_bulk_scoring_all_bg) par un job Vertex AI Batch
sur le même modèle que cv_api/bulk_service.py :
  1. Précharge les missions de tous les users ciblés (parallèle, semaphore=20)
  2. Construit un JSONL (1 ligne par paire user_id × competency)
  3. Upload GCS + soumet un job Vertex AI Batch
  4. Poll jusqu'à JOB_STATE_SUCCEEDED (toutes les 60s)
  5. Lit les résultats GCS et bulk-UPDATE les CompetencyEvaluation en DB

Gain vs pipeline online :
  - Coût tokens : -50% (tarif Batch Vertex AI)
  - Temps : parallélisme massif géré par Vertex AI (pas par notre Cloud Run)
  - Charge réseau : N appels HTTP/user (missions) vs N×M appels séquentiels
"""

import asyncio
import json
import logging
import math
import os
import re
import time
from datetime import datetime, timezone
from typing import Optional

import httpx
from google.cloud import storage as gcs_storage
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import database
from src.competencies.bulk_task_state import bulk_scoring_manager
from src.competencies.models import Competency, user_competency, CompetencyEvaluation
from src.competencies.scheduler_control import set_scoring_scheduler_enabled
from src.competencies.finops import log_finops


logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
GCP_PROJECT_ID: str = os.getenv("GCP_PROJECT_ID", "")
VERTEX_LOCATION: str = os.getenv("VERTEX_LOCATION", "europe-west1")
BATCH_GCS_BUCKET: str = os.getenv("BATCH_GCS_BUCKET", "")
CV_API_URL: str = os.getenv("CV_API_URL", "http://cv_api:8000")

# IMPORTANT : Vertex AI Batch n'accepte PAS les IDs preview (gemini-3.1-*-preview).
# 404 NOT_FOUND: "The PublisherModel gemini-3.1-flash-lite-preview does not exist."
# → Utiliser un ID stable (gemini-2.5-flash) via VERTEX_BATCH_MODEL.
# GEMINI_MODEL peut rester un ID preview (utilisé par l'API online avec api_key).
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL")
VERTEX_BATCH_MODEL: str = os.getenv(
    "VERTEX_BATCH_MODEL",
    os.getenv("GEMINI_MODEL_STABLE")  # ID stable Vertex AI
)

# Concurrence de préchargement des missions (1 appel HTTP par user)
MISSIONS_FETCH_SEMAPHORE: int = int(os.getenv("SCORING_MISSIONS_FETCH_SEMAPHORE", "20"))
# Concurrence d'écriture DB en phase apply
SCORING_APPLY_SEMAPHORE: int = int(os.getenv("SCORING_APPLY_SEMAPHORE", "10"))

# ── Paramètres de pondération scoring v2 (dupliqués depuis router.py) ─────────
COMPETENCY_DECAY_LAMBDA: float = float(os.getenv("COMPETENCY_DECAY_LAMBDA", "0.1"))
MISSION_TYPE_BONUS: dict = {
    "audit": 0.5, "conseil": 0.5, "accompagnement": 0.3,
    "formation": 0.4, "expertise": 0.3, "build": 0.0,
}
MISSION_TYPE_LABELS: dict = {
    "audit": "Audit / Diagnostic (valeur ajoutée élevée)",
    "conseil": "Conseil / Advisory (valeur ajoutée élevée)",
    "accompagnement": "Accompagnement / Coaching (valeur ajoutée)",
    "formation": "Formation / Workshop (valeur ajoutée)",
    "expertise": "Expert / Architecte (valeur ajoutée)",
    "build": "Build / Développement (standard)",
}


# ── Utilitaires de pondération (copiés depuis router.py pour autonomie) ───────

def _compute_recency_weight(end_date_str: Optional[str]) -> float:
    """Decay exponentiel sur l'ancienneté de la mission."""
    if not end_date_str:
        return 1.0
    if str(end_date_str).lower() in ("present", "en cours", "current"):
        return 1.0
    try:
        year = int(str(end_date_str)[:4])
        current_year = datetime.now(timezone.utc).year
        age_years = max(0, current_year - year)
        return round(math.exp(-COMPETENCY_DECAY_LAMBDA * age_years), 2)
    except (ValueError, TypeError):
        return 1.0


def _parse_duration_months(duration_str: Optional[str]) -> Optional[int]:
    if not duration_str:
        return None
    m = re.search(r"(\d+)\s*mois", str(duration_str), re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*an", str(duration_str), re.IGNORECASE)
    if m:
        return int(m.group(1)) * 12
    return None


def _duration_multiplier(months: Optional[int]) -> float:
    if not months:
        return 1.0
    if months >= 18:
        return 1.5
    if months >= 9:
        return 1.2
    if months >= 3:
        return 1.0
    return 0.5


def _get_mission_bonus(mission_type: Optional[str]) -> tuple[str, float]:
    key = (mission_type or "").lower().strip()
    bonus = MISSION_TYPE_BONUS.get(key, 0.0)
    label = MISSION_TYPE_LABELS.get(key, "Autre mission")
    return label, bonus


def _estimate_duration_from_dates(start: Optional[str], end: Optional[str]) -> Optional[str]:
    if not start or not end:
        return None
    try:
        sy = int(str(start)[:4])
        sm = int(str(start)[5:7]) if len(str(start)) >= 7 else 1
        if str(end).lower() in ("present", "en cours", "current"):
            from datetime import date as _date
            ey, em = _date.today().year, _date.today().month
        else:
            ey = int(str(end)[:4])
            em = int(str(end)[5:7]) if len(str(end)) >= 7 else 12
        months = max(1, (ey - sy) * 12 + (em - sm))
        return f"{months} mois"
    except (ValueError, TypeError):
        return None


def _format_mission_v2(m: dict) -> str:
    """Formate une mission avec méta-données de pondération explicites pour le LLM."""
    title = m.get("title", "Mission sans titre")
    company = m.get("company", "?")

    recency_weight = _compute_recency_weight(m.get("end_date"))
    end_date_label = m.get("end_date") or "date inconnue"
    if recency_weight >= 0.9:
        recency_label = f"récente (poids={recency_weight})"
    elif recency_weight >= 0.6:
        recency_label = f"semi-récente (poids={recency_weight})"
    else:
        recency_label = f"ancienne, valeur diminuée (poids={recency_weight})"

    raw_duration = m.get("duration") or _estimate_duration_from_dates(
        m.get("start_date"), m.get("end_date")
    )
    duration_months = _parse_duration_months(raw_duration)
    dur_mult = _duration_multiplier(duration_months)
    dur_label = (
        f"{duration_months} mois (multiplicateur={dur_mult})"
        if duration_months
        else f"durée non précisée (multiplicateur neutre={dur_mult})"
    )

    mtype_label, mtype_bonus = _get_mission_bonus(m.get("mission_type"))
    bonus_str = f"+{mtype_bonus} bonus" if mtype_bonus > 0 else "pas de bonus"

    parts = [
        f"▶ Mission [{recency_label} | {dur_label} | {mtype_label}, {bonus_str}]",
        f"  Titre : {title} chez {company}",
        f"  Période : {m.get('start_date', '?')} → {end_date_label}",
    ]
    if m.get("description"):
        parts.append(f"  Description : {str(m['description'])[:300]}")
    comps = m.get("competencies", [])
    if comps:
        parts.append(f"  Compétences utilisées : {', '.join(comps)}")
    return "\n".join(parts)


def _build_scoring_prompt(competency_name: str, missions: list) -> str:
    """Construit le prompt v2 identique à router._compute_ai_score."""
    if not missions:
        return ""

    comp_norm = competency_name.lower()
    relevant = [
        m for m in missions
        if any(
            comp_norm in c.lower() or c.lower() in comp_norm
            for c in m.get("competencies", [])
        )
    ]
    context_missions = relevant if relevant else missions[:5]
    context_label = "directement liées à cette compétence" if relevant else "générales du consultant"
    missions_text = "\n\n".join([_format_mission_v2(m) for m in context_missions])

    return (
        f"Tu es un évaluateur expert de consultants IT et tech (scoring v2 avec pondération)."
        f" Tu dois noter la maîtrise de la compétence '{competency_name}' "
        f"pour ce consultant, de 0.0 à 5.0 (par pas de 0.5).\n\n"
        f"=== RÈGLES DE PONDÉRATION OBLIGATOIRES ===\n"
        f"Tu DOIS appliquer ces poids dans ton évaluation :\n"
        f"1. RÉCENCE : chaque mission affiche un 'poids' entre 0.0 et 1.0.\n"
        f"   - poids proche de 1.0 = mission récente → compte PLEINEMENT\n"
        f"   - poids 0.2-0.4 = mission ancienne → compte mais de façon RÉDUITE\n"
        f"2. DURÉE : chaque mission affiche un 'multiplicateur' entre 0.5 et 1.5.\n"
        f"   - multiplicateur > 1.0 = mission longue → profondeur de maîtrise accrue\n"
        f"3. TYPE DE MISSION : audit/conseil/accompagnement/formation/expertise affichent\n"
        f"   un bonus (+0.3 à +0.5).\n\n"
        f"=== NIVEAUX DE RÉFÉRENCE ===\n"
        f"  - 0.0 : Aucune trace dans le CV\n"
        f"  - 1.0 : Notions de base, mentionné dans des missions anciennes ou courtes\n"
        f"  - 2.0 : Utilisation ponctuelle\n"
        f"  - 3.0 : Maîtrise confirmée, plusieurs missions avec bons poids\n"
        f"  - 4.0 : Expert, missions longues/récentes ou audit/conseil intense\n"
        f"  - 5.0 : Référence reconnue / Lead sur plusieurs missions à forte valeur ajoutée\n\n"
        f"=== MISSIONS {context_label.upper()} AVEC MÉTA-DONNÉES DE PONDÉRATION ===\n"
        f"{missions_text}\n\n"
        f"=== CONSIGNE ===\n"
        f"Réponds UNIQUEMENT en JSON valide avec exactement deux champs :\n"
        f"- score : float entre 0.0 et 5.0, arrondi au pas de 0.5\n"
        f"- justification : string factuelle de 50 à 250 caractères en français\n\n"
        f'Exemple : {{"score": 3.5, "justification": "2 missions récentes (poids>0.9) dont 1 audit."}}'
    )


# ── Phase 1 : Préchargement des missions ─────────────────────────────────────

async def _fetch_missions_for_user(
    user_id: int, headers: dict, sem: asyncio.Semaphore
) -> tuple[int, list]:
    """Récupère les missions d'un user depuis cv_api (avec semaphore de concurrence)."""
    async with sem:
        try:
            async with httpx.AsyncClient(timeout=15.0) as hc:
                res = await hc.get(
                    f"{CV_API_URL.rstrip('/')}/user/{user_id}/missions",
                    headers=headers,
                )
                if res.status_code == 200:
                    return user_id, res.json().get("missions", [])
                logger.warning(f"[scoring_service] missions user={user_id} HTTP {res.status_code}")
        except Exception as e:
            logger.warning(f"[scoring_service] missions user={user_id} erreur: {e}")
    return user_id, []


async def _prefetch_all_missions(
    user_ids: list[int], headers: dict
) -> dict[int, list]:
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

def _build_jsonl_lines(
    user_comp_list: list[tuple[int, int, str]],  # (user_id, comp_id, comp_name)
    missions_map: dict[int, list],
) -> tuple[list[str], dict[str, tuple[int, int, str]], int]:
    """
    Construit les lignes JSONL Vertex AI Batch.
    Retourne (lignes_jsonl, index, nb_skipped_no_missions).

    index : clé = "score-{user_id}-{comp_id}" → (user_id, comp_id, comp_name)
    """
    lines: list[str] = []
    index: dict[str, tuple[int, int, str]] = {}
    skipped_no_mission = 0

    for user_id, comp_id, comp_name in user_comp_list:
        missions = missions_map.get(user_id, [])
        if not missions:
            skipped_no_mission += 1
            continue

        prompt = _build_scoring_prompt(comp_name, missions)
        if not prompt:
            skipped_no_mission += 1
            continue

        key = f"score-{user_id}-{comp_id}"
        lines.append(json.dumps({
            "id": key,
            "request": {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.1,
                    "responseMimeType": "application/json",
                },
            },
        }))
        index[key] = (user_id, comp_id, comp_name)

    return lines, index, skipped_no_mission


# ── Phase 3 : Apply des résultats GCS → DB ───────────────────────────────────

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
        nonlocal success, errors
        async with database.SessionLocal() as db:
            for user_id, comp_id, _, score, justification in chunk:
                try:
                    stmt = select(CompetencyEvaluation).where(
                        CompetencyEvaluation.user_id == user_id,
                        CompetencyEvaluation.competency_id == comp_id,
                    )
                    ev = (await db.execute(stmt)).scalars().first()
                    if not ev:
                        ev = CompetencyEvaluation(user_id=user_id, competency_id=comp_id)
                        db.add(ev)
                    ev.ai_score = score
                    ev.ai_justification = justification
                    ev.ai_scored_at = datetime.utcnow()
                    ev.scoring_version = "v3-batch"
                    ev.updated_at = datetime.utcnow()
                    await db.commit()
                    success += 1
                except Exception as item_e:
                    await db.rollback()
                    if not sample_error:
                        sample_error = str(item_e)
                    logger.error(f"[scoring_service] upsert user={user_id} comp={comp_id}: {item_e}")
                    errors += 1


    chunks = [results[i:i + chunk_size] for i in range(0, len(results), chunk_size)]
    sem = asyncio.Semaphore(SCORING_APPLY_SEMAPHORE)

    async def _sem_worker(chunk: list):
        async with sem:
            await _process_chunk(chunk)

    # Lancement des chunks en parallèle (limité par le sémaphore, donc max N connexions DB)
    await asyncio.gather(*[_sem_worker(c) for c in chunks])
    
    return success, errors, sample_error


def _parse_scoring_results_gcs(
    blobs_jsonl: list[str],
    index: dict[str, tuple[int, int, str]],
) -> tuple[list[tuple[int, int, str, float, str]], dict[int, dict]]:
    """
    Parse les lignes JSONL de sortie Vertex AI Batch.
    Retourne une liste de (user_id, comp_id, comp_name, score, justification) 
    et un dict des usages tokens par user_id.
    """
    results: list[tuple[int, int, str, float, str]] = []
    user_usage: dict[int, dict] = {}
    for line in blobs_jsonl:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            key = record.get("id") or record.get("key", "")
            if key not in index:
                continue
            user_id, comp_id, comp_name = index[key]
            candidates = record.get("response", {}).get("candidates", [])
            usage = record.get("response", {}).get("usageMetadata", {})
            
            inp = usage.get("promptTokenCount", 0)
            out = usage.get("candidatesTokenCount", 0)
            if user_id not in user_usage:
                user_usage[user_id] = {"prompt_token_count": 0, "candidates_token_count": 0}
            user_usage[user_id]["prompt_token_count"] += inp
            user_usage[user_id]["candidates_token_count"] += out
            
            if not candidates:
                continue
            raw = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
            if not raw.startswith("{"):
                m = re.search(r"\{.*\}", raw, re.DOTALL)
                raw = m.group(0) if m else raw
            data = json.loads(raw)
            score = max(0.0, min(5.0, float(data.get("score", 0.0))))
            score = round(score * 2) / 2  # arrondi au pas de 0.5
            justification = str(data.get("justification", ""))[:500]
            results.append((user_id, comp_id, comp_name, score, justification))
        except Exception as e:
            logger.warning(f"[scoring_service] parse ligne GCS: {e}")
    return results, user_usage


# ── Point d'entrée principal ──────────────────────────────────────────────────

async def bg_bulk_scoring_vertex(
    user_ids: list[int],
    headers: dict,
) -> None:
    """
    Background task principale : pipeline complet de bulk scoring via Vertex AI Batch.
    Appelée depuis router.py en remplacement de _bulk_scoring_all_bg.
    """
    from google import genai  # import local pour éviter erreur si non installé

    if not GCP_PROJECT_ID or not BATCH_GCS_BUCKET:
        await bulk_scoring_manager.update_progress(
            status="error",
            error="GCP_PROJECT_ID ou BATCH_GCS_BUCKET non configuré — scoring Vertex désactivé.",
        )
        return

    try:
        vertex_client = genai.Client(vertexai=True, project=GCP_PROJECT_ID, location=VERTEX_LOCATION)
    except Exception as e:
        await bulk_scoring_manager.update_progress(
            status="error", error=f"Init vertex_client: {e}"
        )
        return

    try:
        # ── Étape 1 : Collecter (user_id, comp_id, comp_name) depuis la DB ──────
        await bulk_scoring_manager.update_progress(
            new_log=f"Collecte des compétences feuilles pour {len(user_ids)} users..."
        )
        user_comp_list: list[tuple[int, int, str]] = []
        async with database.SessionLocal() as db:
            for uid in user_ids:
                user_comp_subq = (
                    select(user_competency.c.competency_id)
                    .where(user_competency.c.user_id == uid)
                    .subquery()
                )
                leaf_stmt = (
                    select(user_competency.c.competency_id)
                    .where(user_competency.c.user_id == uid)
                    .where(
                        ~select(Competency.id)
                        .where(Competency.parent_id == user_competency.c.competency_id)
                        .where(Competency.id.in_(user_comp_subq))
                        .correlate(user_competency)
                        .exists()
                    )
                )
                leaf_ids = (await db.execute(leaf_stmt)).scalars().all()
                if not leaf_ids:
                    continue
                comps = (await db.execute(
                    select(Competency.id, Competency.name).where(Competency.id.in_(leaf_ids))
                )).all()

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
        jsonl_lines, scoring_index, skipped_no_mission = _build_jsonl_lines(user_comp_list, missions_map)
        await bulk_scoring_manager.update_progress(
            new_log=f"JSONL : {len(jsonl_lines)} requêtes, {skipped_no_mission} ignorés (pas de missions)."
        )
        if not jsonl_lines:
            await bulk_scoring_manager.update_progress(
                status="completed", new_log="Aucune requête à soumettre — terminé."
            )
            return

        # ── Étape 4 : Upload GCS ──────────────────────────────────────────────────
        await bulk_scoring_manager.update_progress(status="uploading", new_log="Upload JSONL vers GCS...")
        ts = int(time.time())
        blob_input = f"bulk-scoring/input/{ts}.jsonl"
        blob_output_prefix = f"bulk-scoring/output/{ts}/"
        input_uri = f"gs://{BATCH_GCS_BUCKET}/{blob_input}"
        dest_uri = f"gs://{BATCH_GCS_BUCKET}/{blob_output_prefix}"

        try:
            gcs_client = gcs_storage.Client()
            bucket = gcs_client.bucket(BATCH_GCS_BUCKET)
            blob = bucket.blob(blob_input)
            blob.upload_from_string("\n".join(jsonl_lines), content_type="application/jsonlines")
            await bulk_scoring_manager.update_progress(
                new_log=f"Upload OK : {input_uri} ({len(jsonl_lines)} lignes)"
            )
        except Exception as e:
            await bulk_scoring_manager.update_progress(status="error", error=f"GCS upload: {e}")
            return

        # ── Étape 5 : Soumettre le job Vertex AI Batch ───────────────────────────
        try:
            job = await asyncio.to_thread(
                vertex_client.batches.create,
                model=VERTEX_BATCH_MODEL,
                src=input_uri,
                config={"display_name": f"competencies-bulk-scoring-{ts}", "dest": dest_uri},
            )
            await bulk_scoring_manager.update_progress(
                status="batch_running",
                batch_job_id=job.name,
                dest_uri=dest_uri,
                new_log=f"Job Vertex AI soumis : {job.name} (model={VERTEX_BATCH_MODEL})",
            )
            logger.info(f"[scoring_service] Vertex batch job créé : {job.name} (model={VERTEX_BATCH_MODEL})")

        except Exception as e:
            await bulk_scoring_manager.update_progress(status="error", error=f"Vertex create: {e}")
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

            state_name = job.state.name if hasattr(job.state, "name") else str(job.state)
            label = state_labels.get(state_name, state_name)
            logger.info(f"[scoring_service] job state={state_name} (poll #{poll_count})")
            await bulk_scoring_manager.update_progress(
                new_log=f"[Poll #{poll_count}] {label} (état Vertex : {state_name})"
            )
            if state_name == "JOB_STATE_SUCCEEDED":
                await bulk_scoring_manager.update_progress(new_log="Vertex Batch terminé avec succès.")
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
            blobs = await asyncio.to_thread(list, bucket2.list_blobs(prefix=blob_output_prefix))
            for out_blob in blobs:
                if not out_blob.name.endswith(".jsonl"):
                    continue
                content = await asyncio.to_thread(out_blob.download_as_text)
                raw_lines.extend(content.splitlines())
        except Exception as e:
            await bulk_scoring_manager.update_progress(status="error", error=f"GCS read: {e}")
            return

        results, user_usage = _parse_scoring_results_gcs(raw_lines, scoring_index)
        await bulk_scoring_manager.update_progress(
            new_log=f"Résultats parsés : {len(results)} scores valides sur {len(jsonl_lines)} soumis."
        )

        # ── Étape 7.5 : Log FinOps ────────────────────────────────────────────────
        auth_header = headers.get("Authorization", "")
        service_token = auth_header.removeprefix("Bearer ").strip() if auth_header else ""
        for uid, usage in user_usage.items():
            asyncio.create_task(
                log_finops(
                    user_email=f"user_{uid}",
                    action="bulk_scoring_vertex",
                    model=VERTEX_BATCH_MODEL,
                    usage_metadata=usage,
                    metadata={"user_id": uid, "scores_count": sum(1 for r in results if r[0] == uid)},
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
                new_log=f"{skipped_no_mission} paires ignorées (aucune mission dans CV) — score minimal 1.0 non appliqué automatiquement (relancer avec missions disponibles)."
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
        await bulk_scoring_manager.update_progress(
            status="error", error=f"Fatal: {e}"
        )
        # Pipeline en erreur — pause le Cloud Scheduler keepalive
        await set_scoring_scheduler_enabled(False)

