"""
router.py — Dispatcher léger : assemble les sous-routers spécialisés de competencies_api.

Architecture modulaire (< 400 lignes par fichier) :
  - competencies_router.py : CRUD compétences, suggestions, bulk_tree, stats
  - assignments_router.py  : assignation user/compétences + pubsub Pub/Sub
  - evaluations_router.py  : scoring (batch, ai-score-single, ai-score-all, user-score)
  - scoring_router.py      : bulk-scoring-all pipeline Vertex AI + Cloud Scheduler keepalive
  - analytics_router.py    : couverture, skill-gaps, consultants similaires
  - helpers.py             : fonctions utilitaires partagées
  - ai_scoring.py          : moteur Gemini v2

ORDRE CRITIQUE (règle FastAPI — routes statiques AVANT wildcards) :
  1. competencies_router  : /search, /suggestions, /stats, /bulk_tree  →  avant /{competency_id}
  2. evaluations_router   : /evaluations/...                            →  avant /user/{user_id}
  3. scoring_router       : /bulk-scoring-all/..., /evaluations/bulk-scoring-all
  4. analytics_router     : /stats/coverage, /analytics/...
  5. assignments_router   : /user/{user_id}/...                         →  dernière (wildcards)
  6. public_router        : /pubsub/user-events  (sans auth)
"""

from fastapi import APIRouter

from src.competencies.competencies_router import router as competencies_router
from src.competencies.evaluations_router import router as evaluations_router
from src.competencies.scoring_router import router as scoring_router
from src.competencies.scoring_router import scheduler_router as analytics_scheduler_router
from src.competencies.analytics_router import router as analytics_router
from src.competencies.assignments_router import router as assignments_router
from src.competencies.assignments_router import public_router

# Agrégateur principal (protégé JWT — chaque sous-router porte ses propres Depends)
router = APIRouter(prefix="", tags=["competencies"])

# Ordre strict : statiques d'abord, wildcards en dernier
router.include_router(competencies_router)
router.include_router(evaluations_router)
router.include_router(scoring_router)
router.include_router(analytics_router)
router.include_router(assignments_router)

__all__ = ["router", "public_router", "analytics_scheduler_router"]
