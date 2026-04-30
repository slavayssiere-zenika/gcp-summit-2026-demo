"""
router.py — Orchestrateur pur cv_api.

Ce fichier ne contient QUE des include_router(). Toute la logique métier
est dans les sous-routers :
  - routers/profile_router.py   : import, profils, tags, merge, pubsub
  - routers/search_router.py    : recherche sémantique, similar, RAG
  - routers/analytics_router.py : ranking, reindex, reanalyze, skills coverage
  - routers/taxonomy_router.py  : recalculate_tree interactif + batch
  - routers/bulk_router.py      : bulk-reanalyse pipeline

RÈGLE : ne JAMAIS ajouter de logique métier ici — créer un nouveau sous-router.
"""
from fastapi import APIRouter, Depends
import httpx  # Re-exporté pour compat mocks tests (src.cvs.router.httpx)

from src.auth import verify_jwt
from src.cvs.routers.profile_router import (
    router as profile_router,
    public_router as profile_public_router,
)
from src.cvs.routers.search_router import router as search_router
from src.cvs.routers.analytics_router import router as analytics_router
from src.cvs.routers.taxonomy_router import router as taxonomy_router
from src.cvs.routers.bulk_router import router as bulk_router

# ── Router principal (protégé JWT) ───────────────────────────────────────────
router = APIRouter(prefix="", tags=["CV Analysis"], dependencies=[Depends(verify_jwt)])

# ── Router public (pubsub — pas de JWT) ──────────────────────────────────────
public_router = APIRouter(prefix="", tags=["CV_Public"])

# ── Inclusion des sous-routers ────────────────────────────────────────────────
# RÈGLE FastAPI : routes statiques avant wildcards (voir KI fastapi-route-ordering).
# L'ordre ici détermine la priorité de résolution des routes.
router.include_router(profile_router)
router.include_router(search_router)
router.include_router(analytics_router)
router.include_router(taxonomy_router)
router.include_router(bulk_router)

public_router.include_router(profile_public_router)
