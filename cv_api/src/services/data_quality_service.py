"""
data_quality_service.py — Calcul du rapport de qualité des données du pipeline bulk.

Responsabilités :
  - Agréger les métriques SQL sur CVProfile (missions, embeddings, compétences, summary, current_role)
  - Interroger competencies_api pour les métriques externes (coverage, ai_scoring)
  - Calculer le score pondéré 0-100, le grade A-D, et les issues actionnables
  - Servir de source unique de vérité pour l'endpoint REST et le tool MCP

Ce module est intentionnellement SANS état global — le cache TTL est géré par config.py.
"""

import logging
import os
from datetime import datetime, timezone

import httpx
from opentelemetry.propagate import inject
from sqlalchemy import func, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from src.cvs.models import CVProfile

logger = logging.getLogger(__name__)

# ── Constantes ─────────────────────────────────────────────────────────────────
MIN_SCORED_COUNT: int = 10
CACHE_TTL_SECONDS: int = 30

# Pondération du score global (somme = 1.0)
# Règle métier : ai_scoring et competency_assignment sont les indicateurs
# de bout-en-bout du pipeline — ils ont la pondération la plus forte.
# Les métriques structurelles (summary, current_role) pèsent moins car
# leur absence a moins d'impact sur la qualité opérationnelle.
_WEIGHTS: dict[str, float] = {
    "embedding":             0.15,  # extraction technique — important mais auto
    "competencies":          0.10,  # extraction LLM — validé par competency_assignment
    "missions":              0.10,  # extraction LLM — moins critique que le scoring final
    "summary":               0.05,  # cosmétique — impact limité sur la recherche
    "current_role":          0.05,  # cosmétique — impact limité sur le staffing
    "competency_assignment": 0.30,  # liaison consultant → compétences taxonomie ← critique
    "ai_scoring":            0.25,  # scoring IA effectif ← critique (était 0.10)
}
# sum(_WEIGHTS.values()) == 1.0 — invariant vérifié

# Gate bloquant : si une métrique est sous ce seuil, le grade est plafonné à C.
# Raison : un maillon faible invalide la fiabilité globale du pipeline.
_GATE_THRESHOLD: int = 80


def _pct(ok: int, tot: int) -> int:
    """Retourne le pourcentage entier (0-100), sécurisé contre la division par zéro et plafonné à 100."""
    return min(100, round((ok / max(tot, 1)) * 100))


def _status(pct: int) -> str:
    """Retourne 'ok', 'warning' ou 'error' selon le seuil de qualité."""
    if pct >= 80:
        return "ok"
    if pct >= 50:
        return "warning"
    return "error"


async def compute_data_quality_report(db: AsyncSession, auth_header: str) -> dict:
    """Calcule le rapport complet de qualité des données du pipeline bulk.

    Effectue les requêtes SQL directes sur CVProfile pour les métriques internes,
    puis appelle competencies_api (soft-dependency — fallback gracieux si indisponible).

    Args:
        db: Session SQLAlchemy async (injectée par FastAPI ou ouverte manuellement).
        auth_header: Header 'Authorization: Bearer <token>' à propager aux appels HTTP.

    Returns:
        Dict conforme au type DqReport attendu par le frontend DataQuality.vue :
        {computed_at, total_cvs, users_with_cv, score, grade, metrics, issues, recommendation}
    """
    # ── 1. Métriques SQL internes ─────────────────────────────────────────────
    total_cvs: int = (
        await db.execute(select(func.count()).select_from(CVProfile))
    ).scalar_one() or 0

    users_with_cv: int = (
        await db.execute(
            select(func.count(func.distinct(CVProfile.user_id))).select_from(CVProfile)
        )
    ).scalar_one() or 0

    missions_ok: int = (
        await db.execute(
            select(func.count()).select_from(CVProfile).where(
                CVProfile.missions.isnot(None),
                sa_text("jsonb_array_length(missions) > 0"),
            )
        )
    ).scalar_one() or 0

    embedding_ok: int = (
        await db.execute(
            select(func.count()).select_from(CVProfile).where(
                CVProfile.semantic_embedding.isnot(None)
            )
        )
    ).scalar_one() or 0

    competencies_ok: int = (
        await db.execute(
            select(func.count()).select_from(CVProfile).where(
                CVProfile.extracted_competencies.isnot(None),
                sa_text("jsonb_array_length(extracted_competencies) > 0"),
            )
        )
    ).scalar_one() or 0

    summary_ok: int = (
        await db.execute(
            select(func.count()).select_from(CVProfile).where(
                CVProfile.summary.isnot(None),
                CVProfile.summary != "",
            )
        )
    ).scalar_one() or 0

    current_role_ok: int = (
        await db.execute(
            select(func.count()).select_from(CVProfile).where(
                CVProfile.current_role.isnot(None),
                CVProfile.current_role != "",
            )
        )
    ).scalar_one() or 0

    # ── 2. Métriques externes (soft-dependencies) ─────────────────────────────
    competencies_api_url = os.getenv("COMPETENCIES_API_URL", "http://competencies_api:8000")

    competency_assignment_ok = 0
    competency_assignment_total = users_with_cv
    try:
        h = {"Authorization": auth_header}
        inject(h)
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0)) as hc:
            res = await hc.get(
                f"{competencies_api_url.rstrip('/')}/stats/coverage",
                headers=h,
            )
            if res.status_code == 200:
                data = res.json()
                competency_assignment_ok = data.get("users_with_competencies", 0)
                competency_assignment_total = data.get("total_users", users_with_cv) or users_with_cv
    except Exception as exc:
        logger.warning(f"[data-quality] competencies_api /stats/coverage indisponible: {exc}")

    ai_scoring_ok = 0
    ai_scoring_avg = 0.0
    try:
        h_ai = {"Authorization": auth_header}
        inject(h_ai)
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0)) as hc:
            res = await hc.get(
                f"{competencies_api_url.rstrip('/')}/evaluations/scoring-stats",
                params={"min_scored_count": MIN_SCORED_COUNT},
                headers=h_ai,
            )
            if res.status_code == 200:
                data = res.json()
                ai_scoring_ok = data.get("users_with_min_scored", 0)
                ai_scoring_avg = round(data.get("avg_scored_per_user", 0.0), 1)
    except Exception as exc:
        logger.warning(f"[data-quality] competencies_api /evaluations/scoring-stats indisponible: {exc}")

    # ── 3. Construction des métriques ─────────────────────────────────────────
    total = total_cvs or 1  # éviter division par zéro

    m_missions = {
        "ok": missions_ok, "total": total,
        "pct": _pct(missions_ok, total),
    }
    m_embedding = {
        "ok": embedding_ok, "total": total,
        "pct": _pct(embedding_ok, total),
    }
    m_competencies = {
        "ok": competencies_ok, "total": total,
        "pct": _pct(competencies_ok, total),
    }
    m_summary = {
        "ok": summary_ok, "total": total,
        "pct": _pct(summary_ok, total),
    }
    m_current_role = {
        "ok": current_role_ok, "total": total,
        "pct": _pct(current_role_ok, total),
    }
    m_comp_assign = {
        "ok": competency_assignment_ok,
        "total": competency_assignment_total,
        "pct": _pct(competency_assignment_ok, competency_assignment_total),
    }
    m_ai_scoring = {
        "ok": ai_scoring_ok,
        "total": users_with_cv,
        "pct": _pct(ai_scoring_ok, users_with_cv),
        "min_scored_count": MIN_SCORED_COUNT,
        "avg_scored_per_user": ai_scoring_avg,
    }

    all_metrics = [m_missions, m_embedding, m_competencies, m_summary,
                   m_current_role, m_comp_assign, m_ai_scoring]
    for m in all_metrics:
        m["status"] = _status(m["pct"])

    # ── 4. Score global (moyenne pondérée) ────────────────────────────────────
    score = round(
        m_embedding["pct"]      * _WEIGHTS["embedding"]
        + m_competencies["pct"] * _WEIGHTS["competencies"]
        + m_missions["pct"]     * _WEIGHTS["missions"]
        + m_summary["pct"]      * _WEIGHTS["summary"]
        + m_current_role["pct"] * _WEIGHTS["current_role"]
        + m_comp_assign["pct"]  * _WEIGHTS["competency_assignment"]
        + m_ai_scoring["pct"]   * _WEIGHTS["ai_scoring"]
    )

    if score >= 85:
        grade = "A"
    elif score >= 65:
        grade = "B"
    elif score >= 40:
        grade = "C"
    else:
        grade = "D"

    # ── Gate bloquant — plafonnement à C si un maillon < 80% ─────────────────
    # Un seul indicateur défaillant invalide le grade A ou B, indépendamment
    # de la moyenne pondérée. Règle métier : le pipeline est aussi solide que
    # son maillon le plus faible.
    failing_metrics = [m for m in all_metrics if m["pct"] < _GATE_THRESHOLD]
    if failing_metrics and grade in ("A", "B"):
        grade = "C"
        score = min(score, 64)  # borne haute de la plage C

    # ── 5. Issues actionnables ────────────────────────────────────────────────
    issues: list[str] = []
    if m_embedding["status"] != "ok":
        issues.append(f"Embeddings manquants : {total - embedding_ok} CVs sans vecteur sémantique.")
    if m_competencies["status"] != "ok":
        issues.append(f"Compétences extraites manquantes : {total - competencies_ok} CVs sans compétences.")
    if m_missions["status"] != "ok":
        issues.append(f"Missions manquantes : {total - missions_ok} CVs sans mission.")
    if m_summary["status"] != "ok":
        issues.append(f"Résumés manquants : {total - summary_ok} CVs sans summary.")
    if m_current_role["status"] != "ok":
        issues.append(f"Poste actuel manquant : {total - current_role_ok} CVs sans current_role.")
    if m_comp_assign["status"] != "ok":
        issues.append(
            f"Compétences assignées insuffisantes : "
            f"{competency_assignment_total - competency_assignment_ok} consultant(s) sans compétences liées. "
            "Lancer Retry Apply ou Bulk Scoring."
        )
    if m_ai_scoring["status"] != "ok":
        issues.append(
            f"Bulk Scoring IA insuffisant : "
            f"{users_with_cv - ai_scoring_ok} consultant(s) n'ont pas atteint "
            f"{MIN_SCORED_COUNT} compétences scorées."
        )

    recommendation = (
        "Tous les indicateurs sont dans les seuils nominaux. Pipeline en bonne santé."
        if not issues
        else "Relancer le pipeline bulk (Retry Apply ou Bulk Scoring) pour résoudre les anomalies détectées."
    )

    return {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "total_cvs": total_cvs,
        "users_with_cv": users_with_cv,
        "score": score,
        "grade": grade,
        "metrics": {
            "missions":              m_missions,
            "embedding":             m_embedding,
            "competencies":          m_competencies,
            "summary":               m_summary,
            "current_role":          m_current_role,
            "competency_assignment": m_comp_assign,
            "ai_scoring":            m_ai_scoring,
        },
        "issues": issues,
        "recommendation": recommendation,
    }
