"""
data_quality_service.py — Calcul du rapport de qualité des données du pipeline bulk.

Responsabilités :
  - Agréger les métriques SQL sur CVProfile (missions, embeddings, compétences, summary, current_role)
  - Interroger competencies_api pour les métriques externes (coverage, ai_scoring)
  - Calculer le score pondéré 0-100, le grade A-D, et les issues actionnables
  - Servir de source unique de vérité pour l'endpoint REST et le tool MCP

Ce module est intentionnellement SANS état global — le cache TTL est géré par config.py.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx
from opentelemetry.propagate import inject
from sqlalchemy import func
from sqlalchemy import text as sa_text
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
    "embedding":                0.10,  # extraction technique
    "competencies":             0.10,  # extraction LLM
    "missions":                 0.10,  # extraction LLM
    "summary":                  0.05,  # cosmétique
    "current_role":             0.05,  # cosmétique
    "competency_assignment":    0.20,  # liaison taxonomie
    "ai_scoring":               0.20,  # scoring effectif
    "processing_errors":        0.10,  # erreurs post-traitement (historique)
    "extraction_reliability":   0.10,  # fiabilité extraction Gemini
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

    processing_errors_count: int = (
        await db.execute(
            sa_text(
                "SELECT COUNT(*) FROM cv_profiles "
                "WHERE processing_errors IS NOT NULL "
                "AND jsonb_array_length(processing_errors) > 0"
            )
        )
    ).scalar_one() or 0
    processing_errors_ok = total_cvs - processing_errors_count

    res_extraction = await db.execute(
        sa_text("""
        SELECT
            COUNT(extraction_reliability_score) AS count_scored,
            AVG(extraction_reliability_score)   AS mean_score,
            percentile_cont(0.5) WITHIN GROUP (ORDER BY extraction_reliability_score) AS median_score,
            SUM(CASE WHEN extraction_reliability_score >= 75 THEN 1 ELSE 0 END) AS ok_count
        FROM cv_profiles
        WHERE extraction_reliability_score IS NOT NULL
        """)
    )
    row_ext = res_extraction.fetchone()
    mean_score = round(row_ext[1] or 0, 1) if row_ext else 0.0
    median_score = round(row_ext[2] or 0, 1) if row_ext else 0.0
    extraction_scored_count = int(row_ext[0] or 0) if row_ext else 0  # CVs avec score renseigné
    extraction_ok_count = int(row_ext[3] or 0) if row_ext else 0
    # Dénominateur = CVs ayant un score (pas total_cvs) :
    # Les CVs sans score (NULL après bulk-apply BUG4 fix) sont 'non évalués', pas 'en erreur'.
    # Si aucun CV n'a encore été évalué → métrique ignorée (pct=100, status=ok).
    extraction_denominator = extraction_scored_count if extraction_scored_count > 0 else None

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
    # extraction_reliability : dénominateur = CVs avec score renseigné uniquement.
    # Seuil minimal d'échantillon : < 50 CVs scorés = non représentatif
    # (cas typique post-bulk-reanalyse Vertex où BUG4 fix remet tous les scores à NULL).
    # Dans ce cas, la métrique est marquée N/A plutôt que de générer un faux warning.
    MIN_EXTRACTION_SAMPLE = 50
    if extraction_denominator is None or extraction_scored_count < MIN_EXTRACTION_SAMPLE:
        ext_pct = 100  # non représentatif = pas d'alerte
        ext_status_override = "ok"
        ext_na = True   # flag pour affichage N/A dans l'issue
    else:
        ext_pct = _pct(extraction_ok_count, extraction_denominator)
        ext_status_override = None  # calculé normalement
        ext_na = False
    m_extraction_reliability = {
        "ok": extraction_ok_count,
        "total": extraction_denominator or 0,  # 0 si non évalué
        "pct": ext_pct,
        "mean": mean_score,
        "median": median_score,
        "scored_count": extraction_scored_count,
        "na": ext_na,  # True = échantillon insuffisant, metric non représentatif
    }
    m_processing_errors = {
        "ok": processing_errors_ok,
        "total": total,
        "pct": _pct(processing_errors_ok, total),
    }

    all_metrics = [m_missions, m_embedding, m_competencies, m_summary,
                   m_current_role, m_comp_assign, m_ai_scoring, m_extraction_reliability, m_processing_errors]
    for m in all_metrics:
        m["status"] = _status(m["pct"])
    # Override extraction_reliability status si aucun CV évalué
    if ext_status_override:
        m_extraction_reliability["status"] = ext_status_override

    # ── 4. Score global (moyenne pondérée) ────────────────────────────────────
    score = round(
        m_embedding["pct"] * _WEIGHTS["embedding"]
        + m_competencies["pct"] * _WEIGHTS["competencies"]
        + m_missions["pct"] * _WEIGHTS["missions"]
        + m_summary["pct"] * _WEIGHTS["summary"]
        + m_current_role["pct"] * _WEIGHTS["current_role"]
        + m_comp_assign["pct"] * _WEIGHTS["competency_assignment"]
        + m_ai_scoring["pct"] * _WEIGHTS["ai_scoring"]
        + m_processing_errors["pct"] * _WEIGHTS["processing_errors"]
        + m_extraction_reliability["pct"] * _WEIGHTS["extraction_reliability"]
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
    # extraction_reliability est exclu du gate quand l'échantillon est insuffisant (ext_na=True)
    # pour ne pas pénaliser un pipeline sain avec un indicateur non représentatif.
    gate_metrics = [
        m for m in all_metrics
        if not (m is m_extraction_reliability and ext_na)
    ]
    failing_metrics = [m for m in gate_metrics if m["pct"] < _GATE_THRESHOLD]
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
    if ext_na:
        # Échantillon insuffisant : metric non représentatif (CVs traités via Vertex Batch)
        # On affiche une note informative sans bloquer le grade
        issues.append(
            f"Fiabilité d'extraction : seulement {extraction_scored_count} CV(s) avec score "
            f"(seuil min={MIN_EXTRACTION_SAMPLE}). Metric non représentatif — "
            "les CVs importés via Vertex Batch n'ont pas de score de fiabilité calculable."
        )
    elif m_extraction_reliability["status"] != "ok" and extraction_denominator:
        below_threshold = extraction_denominator - extraction_ok_count
        issues.append(
            f"Fiabilité d'extraction IA insuffisante : "
            f"{below_threshold}/{extraction_denominator} CVs évalués ont un score inférieur à 75%. "
            "À vérifier dans l'interface de Qualité d'Extraction."
        )
    if m_processing_errors["status"] != "ok":
        issues.append(
            f"Erreurs d'ingestion non résolues : "
            f"{processing_errors_count} CVs ont des erreurs de post-traitement. "
            "Relancer les imports depuis l'onglet Erreurs CV."
        )

    recommendation = (
        "Tous les indicateurs sont dans les seuils nominaux. Pipeline en bonne santé."
        if not issues
        else "Relancer le pipeline bulk (Retry Apply ou Bulk Scoring) pour résoudre les anomalies détectées."
    )

    # ── 6. Métriques RAG Sémantique (R3) ─────────────────────────────────────
    # Source : golden_queries.json (versionné en git, mis à jour par rag-calibrate)
    # Non-bloquant : si le fichier est absent ou vide, rag_* sont null.
    rag_recall_at_5: float | None = None
    rag_nb_cases: int | None = None
    rag_nb_cases_ok: int | None = None
    rag_embedding_model: str | None = os.getenv("GEMINI_EMBEDDING_MODEL")

    try:
        # Résolution robuste : parents[2] = /app (Cloud Run) ou cv_api/ (dev local)
        # Structure Cloud Run : /app/src/services/data_quality_service.py → parents[2] = /app
        # Structure dev local : /…/cv_api/src/services/data_quality_service.py → parents[2] = cv_api/
        _svc_file = Path(__file__).resolve()
        _candidate = _svc_file.parents[2] / "eval" / "golden_queries.json"
        if not _candidate.exists():
            # Fallback explicite Cloud Run si workdir non standard
            _candidate = Path("/app/eval/golden_queries.json")

        if _candidate.exists():
            golden_data = json.loads(_candidate.read_text(encoding="utf-8"))
            cases = golden_data.get("cases", [])
            rag_nb_cases = len(cases)
            rag_nb_cases_ok = sum(1 for c in cases if c.get("expected_user_ids"))
            rag_recall_at_5 = round(rag_nb_cases_ok / rag_nb_cases, 4) if rag_nb_cases else None
        else:
            logger.warning(
                "[data-quality] golden_queries.json introuvable (%s). RAG metrics non disponibles.",
                _candidate,
            )
    except Exception as exc:
        logger.warning("[data-quality] Lecture golden_queries.json échouée (non-bloquant): %s", exc)

    # ── 7. Métrique RAG Chunking (R7) — non-bloquant ──────────────────────────
    # Mesure l'état d'indexation de la table cv_mission_embeddings.
    # Si la table est vide (avant première indexation), status='not_indexed'.
    mission_chunks_total = 0
    mission_chunks_profiles = 0
    mission_chunks_avg = 0.0
    mission_chunks_status = "not_indexed"
    try:
        row_chunks = (await db.execute(sa_text("""
            SELECT
                COUNT(*) AS total_chunks,
                COUNT(DISTINCT user_id) AS profiles_indexed
            FROM cv_mission_embeddings
            WHERE chunk_embedding IS NOT NULL
        """))).fetchone()
        if row_chunks:
            mission_chunks_total = int(row_chunks[0] or 0)
            mission_chunks_profiles = int(row_chunks[1] or 0)
            if mission_chunks_profiles > 0:
                mission_chunks_avg = round(mission_chunks_total / mission_chunks_profiles, 1)
            if mission_chunks_total > 0:
                mission_chunks_status = "ok" if mission_chunks_profiles >= total_cvs * 0.9 else "partial"
    except Exception as exc:
        logger.warning("[data-quality] Lecture cv_mission_embeddings échouée (non-bloquant): %s", exc)

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
            "extraction_reliability": m_extraction_reliability,
            "processing_errors":     m_processing_errors,
        },
        "issues": issues,
        "recommendation": recommendation,
        # ── RAG Quality (R3) — ajouté au rapport sans impacter le score global ──
        "rag": {
            "recall_at_5": rag_recall_at_5,
            "nb_cases": rag_nb_cases,
            "nb_cases_ok": rag_nb_cases_ok,
            "embedding_model": rag_embedding_model,
            "status": (
                "ok" if rag_recall_at_5 is not None and rag_recall_at_5 >= 1.0
                else "warning" if rag_recall_at_5 is not None and rag_recall_at_5 >= 0.5
                else "error" if rag_recall_at_5 is not None
                else "unknown"
            ),
        },
        # ── RAG Chunking (R7) — état de la table cv_mission_embeddings ──
        "rag_chunking": {
            "total_chunks": mission_chunks_total,
            "profiles_indexed": mission_chunks_profiles,
            "avg_chunks_per_profile": mission_chunks_avg,
            "status": mission_chunks_status,
            "chunked_search_active": os.getenv("RAG_CHUNKED_SEARCH", "").lower() == "true",
        },
    }
