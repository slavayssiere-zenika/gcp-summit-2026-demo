"""
scoring_service.py — Module orchestrateur (façade).

Re-exporte les symboles publics depuis scoring_utils et scoring_pipeline
pour assurer la rétrocompatibilité des imports existants.

RÈGLE : tout nouveau code doit importer directement depuis scoring_utils
        ou scoring_pipeline — ne JAMAIS ajouter de logique métier ici.
"""
from src.competencies.scoring_utils import (  # noqa: F401
    _compute_recency_weight,
    _parse_duration_months,
    _duration_multiplier,
    _get_mission_bonus,
    _estimate_duration_from_dates,
    _format_mission_v2,
    _build_scoring_prompt,
    _build_jsonl_lines,
    _parse_scoring_results_gcs,
    # ── Constantes (re-export compat pour analytics_router) ──────────────────
    GCP_PROJECT_ID,
    VERTEX_LOCATION,
    BATCH_GCS_BUCKET,
    CV_API_URL,
    GEMINI_MODEL,
    VERTEX_BATCH_MODEL,
    MISSIONS_FETCH_SEMAPHORE,
    SCORING_APPLY_SEMAPHORE,
    COMPETENCY_DECAY_LAMBDA,
)
from src.competencies.scoring_pipeline import (  # noqa: F401
    _fetch_missions_for_user,
    _prefetch_all_missions,
    _apply_scoring_results,
    bg_bulk_scoring_vertex,
)
