"""
helpers.py — Fonctions utilitaires partagées entre tous les routers de competencies_api.

Inclut :
  - Scoring v2 : pondération temporelle, durée, type de mission
  - Génération d'aliases via Gemini Flash
  - Invalidation de cache taxonomie (cv_api)
  - Sérialisation Competency
  - Détection de conflits grammaticaux
  - Résolution d'utilisateur via users_api
"""

import logging
import math
import os
import re
from datetime import date
from typing import List, Optional

import httpx
from fastapi import BackgroundTasks, HTTPException, Request
from google import genai
from opentelemetry.propagate import inject
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from src.competencies.models import Competency
from src.competencies.schemas import UserInfo

logger = logging.getLogger(__name__)

# ── Scoring v2 — Configuration ────────────────────────────────────────────────
# λ du decay temporel : e^(-λ·N) où N = années depuis la fin de mission
# λ=0.1 → poids 0.90 à 1 an, 0.61 à 5 ans, 0.37 à 10 ans, 0.22 à 15 ans (jamais 0)
COMPETENCY_DECAY_LAMBDA = float(os.getenv("COMPETENCY_DECAY_LAMBDA", "0.1"))
GEMINI_MODEL = os.getenv("GEMINI_MODEL")
USERS_API_URL = os.getenv("USERS_API_URL", "http://users_api:8000")
CV_API_URL = os.getenv("CV_API_URL", "http://cv_api:8000")

MISSION_TYPE_BONUS: dict = {
    "audit": 0.5,
    "conseil": 0.5,
    "accompagnement": 0.3,
    "formation": 0.4,
    "expertise": 0.3,
    "build": 0.0,
}

MISSION_TYPE_LABELS: dict = {
    "audit": "Audit / Diagnostic (valeur ajoutée élevée)",
    "conseil": "Conseil / Advisory (valeur ajoutée élevée)",
    "accompagnement": "Accompagnement / Coaching (valeur ajoutée)",
    "formation": "Formation / Workshop (valeur ajoutée)",
    "expertise": "Expert / Architecte (valeur ajoutée)",
    "build": "Build / Développement (standard)",
}


def _compute_recency_weight(end_date_str: Optional[str]) -> float:
    """Calcule un poids de récence via decay exponentielle e^(-λ·N).

    - end_date_str None ou 'present' → poids 1.0 (mission en cours)
    - end_date_str 'YYYY' ou 'YYYY-MM' → poids selon l'ancienneté
    - Date non parseable → poids neutre 0.7
    """
    if not end_date_str or str(end_date_str).lower() in ("present", "aujourd'hui", "current", "en cours"):
        return 1.0
    try:
        end_year = int(str(end_date_str).strip()[:4])
        years_ago = max(0, date.today().year - end_year)
        return round(math.exp(-COMPETENCY_DECAY_LAMBDA * years_ago), 2)
    except (ValueError, TypeError):
        return 0.7


def _parse_duration_months(duration_str: Optional[str]) -> Optional[int]:
    """Parse une durée texte libre en nombre de mois (FR + EN).

    Exemples : '2 ans', '18 mois', '6 months', '1 year 3 months' → retourne un int.
    Retourne None si non parseable.
    """
    if not duration_str:
        return None
    s = str(duration_str).lower()
    total_months = 0
    years_match = re.search(r'(\d+)\s*(?:an|year|yr)', s)
    months_match = re.search(r'(\d+)\s*(?:mois|month|mo)', s)
    weeks_match = re.search(r'(\d+)\s*(?:semaine|week)', s)
    if years_match:
        total_months += int(years_match.group(1)) * 12
    if months_match:
        total_months += int(months_match.group(1))
    if weeks_match:
        total_months += int(weeks_match.group(1)) // 4
    return total_months if total_months > 0 else None


def _duration_multiplier(duration_months: Optional[int]) -> float:
    """Calcule un multiplicateur de durée normalisé entre 0.5 et 1.5.

    6 mois → 0.75 | 12 mois → 1.00 | 24 mois+ → 1.50 (cap).
    Retourne 1.0 (neutre) si la durée est inconnue.
    """
    if duration_months is None:
        return 1.0
    return round(min(1.5, max(0.5, 0.5 + duration_months / 24.0)), 2)


def _get_mission_bonus(mission_type: Optional[str]) -> tuple:
    """Retourne (label_lisible, bonus_score) pour un type de mission."""
    mtype = (mission_type or "build").lower().strip()
    bonus = MISSION_TYPE_BONUS.get(mtype, 0.0)
    label = MISSION_TYPE_LABELS.get(mtype, f"Type: {mtype}")
    return label, bonus


async def _generate_aliases_for_competency(name: str) -> str | None:
    """Génère 3-5 alias pour une compétence via Gemini Flash."""
    try:
        client = genai.Client()
        prompt = (
            f"Tu es un expert technique. Génère 3 à 5 aliases très courts (abréviations, "
            f"variantes de nommage) pour la technologie suivante : '{name}'.\n"
            f"Exemple pour 'Kubernetes' : 'K8s, kube, k8s, Kube, kubernetes'.\n"
            f"Retourne UNIQUEMENT une liste séparée par des virgules, sans aucun texte additionnel."
        )
        res = await client.aio.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        if res.text:
            aliases = res.text.strip().strip("'").strip('"')
            logger.info(f"Alias générés pour '{name}' : {aliases}")
            return aliases
    except Exception as e:
        logger.warning(f"Échec de génération d'alias pour '{name}': {e}")
    return None


def trigger_taxonomy_cache_invalidation(bg_tasks: BackgroundTasks, auth_header: str = None):
    """Déclenche de manière asynchrone l'invalidation du cache de la taxonomie dans cv_api."""
    async def invalidate():
        try:
            async with httpx.AsyncClient() as http_client:
                headers = {}
                if auth_header:
                    headers["Authorization"] = auth_header
                inject(headers)
                await http_client.post(
                    f"{CV_API_URL.rstrip('/')}/cache/invalidate-taxonomy",
                    headers=headers,
                    timeout=3.0,
                )
                logger.info("[Cache Sync] Ordre d'invalidation de la taxonomie envoyé à cv_api.")
        except Exception as e:
            logger.warning(f"[Cache Sync] Échec d'invalidation de cv_api: {e}")
    bg_tasks.add_task(invalidate)


def serialize_competency(c: Competency) -> dict:
    """Sérialise un objet ORM Competency en dict JSON-compatible."""
    return {
        "id": c.id,
        "name": c.name,
        "description": c.description,
        "aliases": c.aliases,
        "parent_id": c.parent_id,
        "created_at": c.created_at,
        "sub_competencies": [],
    }


def get_grammatical_variants(name: str) -> List[str]:
    """Génère les variantes singulier/pluriel potentielles d'un nom de compétence."""
    name = name.strip()
    variants = {name.lower()}
    if name.lower().endswith("s"):
        variants.add(name[:-1].lower())
    if name.lower().endswith("es"):
        variants.add(name[:-2].lower())
    if name.lower().endswith("x"):
        variants.add(name[:-1].lower())
    variants.add(name.lower() + "s")
    variants.add(name.lower() + "es")
    variants.add(name.lower() + "x")
    return list(variants)


async def check_grammatical_conflict(
    db: AsyncSession, name: str, exclude_id: Optional[int] = None
) -> Optional[Competency]:
    """Vérifie si une variante grammaticale du nom existe déjà en base."""
    variants = get_grammatical_variants(name)
    stmt = select(Competency).filter(func.lower(Competency.name).in_(variants))
    if exclude_id:
        stmt = stmt.filter(Competency.id != exclude_id)
    result = (await db.execute(stmt)).scalars().first()
    return result


async def get_user_from_api(user_id: int, request: Request) -> UserInfo:
    """Vérifie que l'utilisateur existe dans users_api en propageant le JWT d'origine."""
    auth_header = request.headers.get("Authorization")
    headers = {"Authorization": auth_header} if auth_header else {}
    inject(headers)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{USERS_API_URL.rstrip('/')}/{user_id}", headers=headers)
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail=f"User {user_id} not found")
            response.raise_for_status()
            return UserInfo(**response.json())
        except httpx.HTTPError as e:
            raise HTTPException(status_code=503, detail=f"Users API unavailable: {str(e)}")
