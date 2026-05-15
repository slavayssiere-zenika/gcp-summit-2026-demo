"""
router.py — Dispatcher léger : assemble les sous-routers spécialisés de competencies_api.

Architecture modulaire (< 400 lignes par fichier) :
  - competencies_router.py : CRUD compétences, bulk_tree, stats
  - suggestions_router.py  : suggestions de compétences (POST/GET /suggestions)
  - assignments_router.py  : assignation user/compétences + pubsub Pub/Sub
  - evaluations_router.py  : scoring (batch, ai-score-single, ai-score-all, user-score)
  - scoring_router.py      : bulk-scoring-all pipeline Vertex AI + Cloud Scheduler keepalive
  - analytics_router.py    : couverture, skill-gaps, consultants similaires
  - helpers.py             : fonctions utilitaires partagées
  - ai_scoring.py          : moteur Gemini v2

ORDRE CRITIQUE (règle FastAPI — routes statiques AVANT wildcards) :
  1. suggestions_router   : /suggestions                          →  avant /{competency_id}
  2. competencies_router  : /search, /stats, /bulk_tree          →  puis wildcard /{competency_id}
  3. evaluations_router   : /evaluations/...                     →  avant /user/{user_id}
  4. scoring_router       : /bulk-scoring-all/..., /evaluations/bulk-scoring-all
  5. analytics_router     : /stats/coverage, /analytics/...
  6. assignments_router   : /user/{user_id}/...                  →  dernière (wildcards)
  7. public_router        : /pubsub/user-events  (sans auth)
"""

from fastapi import APIRouter
from src.competencies.analytics_router import router as analytics_router
from src.competencies.assignments_router import public_router
from src.competencies.assignments_router import router as assignments_router
from src.competencies.competencies_router import router as competencies_router
from src.competencies.evaluations_router import router as evaluations_router
from src.competencies.scoring_router import router as scoring_router
from src.competencies.scoring_router import (
    scheduler_router as analytics_scheduler_router,
)
from src.competencies.suggestions_router import router as suggestions_router
from src.competencies.tree_router import router as tree_router

# Agrégateur principal (protégé JWT — chaque sous-router porte ses propres Depends)
router = APIRouter(prefix="", tags=["competencies"])

# Ordre strict : statiques d'abord, wildcards en dernier
router.include_router(suggestions_router)   # /suggestions  →  AVANT /{competency_id}
router.include_router(competencies_router)  # /{competency_id} wildcard
router.include_router(tree_router)
router.include_router(evaluations_router)
router.include_router(scoring_router)
router.include_router(analytics_router)
router.include_router(assignments_router)

__all__ = ["router", "public_router", "analytics_scheduler_router"]
