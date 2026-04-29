"""
ai_scoring.py — Fonctions internes de scoring IA (Gemini) pour les compétences.

Inclut :
  - _compute_ai_score()     : scoring Gemini v2 (missions + pondération)
  - _score_all_bg()         : BackgroundTask séquentiel pour un user
  - _bulk_scoring_all_bg()  : BackgroundTask avec Semaphore pour N users
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime
from typing import Optional

import httpx
from opentelemetry.propagate import inject
from sqlalchemy.future import select

import database
from cache import delete_cache_pattern
from google import genai
from google.genai import types
from src.competencies.models import Competency, user_competency, CompetencyEvaluation
from src.competencies.bulk_task_state import bulk_scoring_manager
from src.competencies.helpers import (
    _compute_recency_weight,
    _parse_duration_months,
    _duration_multiplier,
    _get_mission_bonus,
)

logger = logging.getLogger(__name__)

GEMINI_MODEL = os.getenv("GEMINI_MODEL")
if not GEMINI_MODEL:
    logger.warning("GEMINI_MODEL n'est pas définie dans l'environnement. Le scoring IA va échouer.")
CV_API_URL = os.getenv("CV_API_URL", "http://cv_api:8000")
USERS_API_URL = os.getenv("USERS_API_URL", "http://users_api:8000")


async def _get_or_create_evaluation(
    db, user_id: int, competency_id: int
) -> CompetencyEvaluation:
    """Retourne l'evaluation existante ou en cree une vide."""
    stmt = select(CompetencyEvaluation).where(
        CompetencyEvaluation.user_id == user_id,
        CompetencyEvaluation.competency_id == competency_id,
    )
    ev = (await db.execute(stmt)).scalars().first()
    if not ev:
        ev = CompetencyEvaluation(user_id=user_id, competency_id=competency_id)
        db.add(ev)
        await db.flush()
    return ev


def _serialize_evaluation(ev: CompetencyEvaluation, competency_name: str = "") -> dict:
    """Serialise une evaluation en dict.

    Le parametre competency_name DOIT etre fourni explicitement depuis la requete
    (via JOIN ou chargement eager) — ne jamais acceder a ev.competency.name ici
    car cela declencherait un lazy load synchrone incompatible avec AsyncSession
    (sqlalchemy.exc.MissingGreenlet).
    """
    return {
        "id": ev.id,
        "user_id": ev.user_id,
        "competency_id": ev.competency_id,
        "competency_name": competency_name,
        "ai_score": ev.ai_score,
        "ai_justification": ev.ai_justification,
        "ai_scored_at": ev.ai_scored_at,
        "user_score": ev.user_score,
        "user_comment": ev.user_comment,
        "user_scored_at": ev.user_scored_at,
    }


async def _compute_ai_score(
    user_id: int, competency_name: str, headers: dict
) -> tuple[Optional[float], Optional[str]]:
    """Appelle cv_api pour obtenir les missions puis demande a Gemini de noter la competence.

    Retourne (score: float 0.0-5.0, justification: str) ou (None, message_erreur).
    Le score est arrondi au pas de 0.5 le plus proche.
    """
    api_key = os.environ.get("GOOGLE_API_KEY", "")
    if not api_key:
        logger.warning(
            f"[_compute_ai_score] GOOGLE_API_KEY non configurée — scoring IA désactivé "
            f"pour user_id={user_id}, competency='{competency_name}'"
        )
        return None, "GOOGLE_API_KEY non configurée — scoring IA désactivé."

    logger.info(f"[_compute_ai_score] Starting evaluation for user_id={user_id}, competency='{competency_name}'")

    # 1. Récupération des missions depuis cv_api
    missions = []
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(f"{CV_API_URL.rstrip('/')}/user/{user_id}/missions", headers=headers)
            if res.status_code == 200:
                missions = res.json().get("missions", [])
                logger.info(f"[_compute_ai_score] Found {len(missions)} missions for user_id={user_id}")
            else:
                logger.error(f"[_compute_ai_score] Error fetching missions for user {user_id}: HTTP {res.status_code}")
    except Exception as e:
        logger.warning(f"[AI Score] Failed to fetch missions for user {user_id}: {e}")
        return None, "Missions non disponibles (erreur réseau)."

    if not missions:
        logger.warning(f"[_compute_ai_score] No missions found for user_id={user_id}. Assigning minimal score 1.0")
        return 1.0, "Aucune mission trouvée dans le CV — score minimal attribué."

    # 2. Filtrage des missions pertinentes
    comp_norm = competency_name.lower()
    relevant_missions = [
        m for m in missions
        if any(comp_norm in c.lower() or c.lower() in comp_norm for c in m.get("competencies", []))
    ]
    context_missions = relevant_missions if relevant_missions else missions[:5]

    # 3. Construction du contexte enrichi v2
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

        raw_duration = m.get("duration") or _estimate_duration_from_dates(m.get("start_date"), m.get("end_date"))
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

    missions_text = "\n\n".join([_format_mission_v2(m) for m in context_missions])
    context_label = "directement liées à cette compétence" if relevant_missions else "générales du consultant"

    # 4. Prompt v2
    prompt = (
        f"Tu es un évaluateur expert de consultants IT et tech (scoring v2 avec pondération)."
        f" Tu dois noter la maîtrise de la compétence '{competency_name}' "
        f"pour ce consultant, de 0.0 à 5.0 (par pas de 0.5).\n\n"
        f"=== RÈGLES DE PONDÉRATION OBLIGATOIRES ===\n"
        f"1. RÉCENCE : chaque mission affiche un 'poids' entre 0.0 et 1.0.\n"
        f"   - poids proche de 1.0 = mission récente → compte PLEINEMENT\n"
        f"   - poids 0.2-0.4 = mission ancienne → compte de façon RÉDUITE\n"
        f"2. DURÉE : chaque mission affiche un 'multiplicateur' entre 0.5 et 1.5.\n"
        f"3. TYPE DE MISSION : audit/conseil/accompagnement/formation/expertise = bonus +0.3 à +0.5.\n\n"
        f"=== NIVEAUX DE RÉFÉRENCE ===\n"
        f"  0.0: Aucune trace | 1.0: Notions | 2.0: Utilisation ponctuelle\n"
        f"  3.0: Maîtrise confirmée | 4.0: Expert | 5.0: Référence reconnue\n\n"
        f"=== MISSIONS {context_label.upper()} ===\n{missions_text}\n\n"
        f"=== CONSIGNE ===\n"
        f"Réponds UNIQUEMENT en JSON valide avec exactement deux champs :\n"
        f"- score : float 0.0-5.0, arrondi au pas de 0.5\n"
        f"- justification : string 50-250 caractères en français\n\n"
        f'Exemple : {{"score": 3.5, "justification": "2 missions récentes (poids>0.9) dont 1 audit chez Airbus (bonus +0.5)."}}'
    )

    # 5. Appel Gemini avec JSON forcé
    try:
        client = genai.Client(api_key=api_key)
        response = await client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1),
        )
        raw = response.text.strip()
        if not raw.startswith("{"):
            json_match = re.search(r"\{.*\}", raw, re.DOTALL)
            raw = json_match.group(0) if json_match else raw
        data = json.loads(raw)
        score = round(round(max(0.0, min(5.0, float(data.get("score", 0.0)))) * 2) / 2, 1)
        justification = str(data.get("justification", ""))[:500]
        logger.info(f"[AI Score] user={user_id} comp='{competency_name}' score={score}")
        return score, justification
    except json.JSONDecodeError as e:
        logger.error(f"[AI Score] JSON parse error for '{competency_name}': {e}")
        return None, "Réponse Gemini non parseable en JSON."
    except Exception as e:
        logger.error(f"[AI Score] Gemini call failed for '{competency_name}': {e}")
    return None, "Calcul IA échoué."


async def _score_all_bg(user_id: int, comp_tuples: list[tuple[int, str]], headers: dict):
    """BackgroundTask : score toutes les competences feuilles d'un utilisateur.

    Recoit des tuples (competency_id, competency_name) pour eviter toute
    contamination cross-session SQLAlchemy.
    """
    logger.info(f"[AI Score BG] Background task started for user={user_id} - {len(comp_tuples)} competencies")
    for comp_id, comp_name in comp_tuples:
        try:
            # 1. Calcul IA (long) SANS maintenir de connexion DB
            score, justification = await _compute_ai_score(user_id, comp_name, headers)
            
            # 2. Persistance courte (checkout d'une connexion DB juste pour écrire)
            async with database.SessionLocal() as db:
                ev = await _get_or_create_evaluation(db, user_id, comp_id)
                ev.ai_score = score
                ev.ai_justification = justification
                ev.ai_scored_at = datetime.utcnow()
                ev.scoring_version = "v2"
                ev.updated_at = datetime.utcnow()
                await db.commit()

            if score is not None:
                logger.info(f"[AI Score BG] user={user_id} competency='{comp_name}' score={score}")
            else:
                logger.warning(f"[AI Score BG] score=None user={user_id} competency='{comp_name}' — {justification}")
            await asyncio.sleep(0.3)
        except Exception as e:
            logger.error(f"[AI Score BG] Failed for user={user_id} comp='{comp_name}': {e}")
            
    delete_cache_pattern(f"competencies:evaluations:user:{user_id}:*")
    logger.info(f"[AI Score BG] Scoring terminé pour user={user_id} — {len(comp_tuples)} compétences traitées.")


async def _bulk_scoring_all_bg(user_ids: list[int], headers: dict, semaphore_limit: int = 2):
    """BackgroundTask : déclenche ai-score-all pour chaque user, avec Semaphore.

    Orchestre N users avec contrôle du débit quota Gemini.
    """
    logger.info(f"[bulk-scoring-all BG] Démarrage — {len(user_ids)} users à scorer")
    sem = asyncio.Semaphore(semaphore_limit)
    success = 0
    errors = 0
    skipped = 0

    async def _trigger_one(uid: int):
        nonlocal success, errors, skipped
        async with sem:
            try:
                async with database.SessionLocal() as db:
                    user_comp_subq = (
                        select(user_competency.c.competency_id)
                        .where(user_competency.c.user_id == uid)
                        .subquery()
                    )
                    leaf_ids_stmt = (
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
                    leaf_ids = (await db.execute(leaf_ids_stmt)).scalars().all()
                    if not leaf_ids:
                        skipped += 1
                        await bulk_scoring_manager.update_progress(processed_inc=1, new_log=f"User {uid} ignoré (0 compétence feuille)")
                        return
                    comps_raw = (await db.execute(
                        select(Competency.id, Competency.name).where(Competency.id.in_(leaf_ids))
                    )).all()
                    comp_tuples = [(row[0], row[1]) for row in comps_raw]

                await _score_all_bg(uid, comp_tuples, headers)
                success += 1
                await bulk_scoring_manager.update_progress(processed_inc=1, success_inc=1)
                await asyncio.sleep(0.5)
            except Exception as e:
                errors += 1
                logger.error(f"[bulk-scoring-all BG] user={uid} erreur: {e}")
                await bulk_scoring_manager.update_progress(
                    processed_inc=1, error_count_inc=1, error=f"User {uid} erreur: {e}"
                )

    await asyncio.gather(*[_trigger_one(uid) for uid in user_ids], return_exceptions=True)
    await bulk_scoring_manager.update_progress(
        status="completed",
        new_log=f"Terminé — {success} succès, {errors} erreurs, {skipped} ignorés.",
    )
    logger.info(f"[bulk-scoring-all BG] Terminé — {success} succès, {errors} erreurs sur {len(user_ids)} users.")
