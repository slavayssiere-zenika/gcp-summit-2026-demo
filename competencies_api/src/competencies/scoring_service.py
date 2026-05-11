"""
scoring_service.py — Module orchestrateur (façade).

Re-exporte les symboles publics depuis scoring_utils et scoring_pipeline
pour assurer la rétrocompatibilité des imports existants.

RÈGLE : tout nouveau code doit importer directement depuis scoring_utils
        ou scoring_pipeline — ne JAMAIS ajouter de logique métier ici.
"""

from src.competencies.scoring_pipeline import (  # noqa: F401
    _apply_scoring_results,
    _fetch_missions_for_user,
    _prefetch_all_missions,
    bg_bulk_scoring_vertex,
)
from src.competencies.scoring_utils import (  # noqa: F401; ── Constantes (re-export compat pour analytics_router) ──────────────────  # noqa: E501
    BATCH_GCS_BUCKET,
    COMPETENCY_DECAY_LAMBDA,
    CV_API_URL,
    GCP_PROJECT_ID,
    GEMINI_MODEL,
    MISSIONS_FETCH_SEMAPHORE,
    SCORING_APPLY_SEMAPHORE,
    VERTEX_BATCH_MODEL,
    VERTEX_LOCATION,
    _build_jsonl_lines,
    _build_scoring_prompt,
    _compute_recency_weight,
    _duration_multiplier,
    _estimate_duration_from_dates,
    _format_mission_v2,
    _get_mission_bonus,
    _parse_duration_months,
    _parse_scoring_results_gcs,
)
