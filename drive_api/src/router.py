"""
router.py — Orchestrateur pur drive_api.

Ce fichier ne contient QUE des include_router(). Toute la logique métier
est dans les sous-routers :
  - routers/folders_router.py   : gestion des dossiers cibles Drive
  - routers/files_router.py     : statut fichiers, sync, retry, tokens, search
  - routers/dlq_router.py       : Dead Letter Queue Pub/Sub management
  - routers/ingestion_router.py : KPIs, quality gate, batch-retry, history

RÈGLE : ne JAMAIS ajouter de logique métier ici — créer un nouveau sous-router.
"""
from fastapi import APIRouter, Depends

from src.auth import verify_jwt
from src.routers.folders_router import router as folders_router
from src.routers.files_router import (
    router as files_router,
    public_router as files_public_router,
)
from src.routers.dlq_router import router as dlq_router
from src.routers.ingestion_router import router as ingestion_router

# ── Router principal (protégé JWT) ────────────────────────────────────────────
router = APIRouter(prefix="", tags=["Drive Admin"], dependencies=[Depends(verify_jwt)])

# ── Router public (sync/scheduled — pas de JWT) ───────────────────────────────
public_router = APIRouter(prefix="", tags=["Drive_Public"])

# ── Inclusion des sous-routers ─────────────────────────────────────────────────
# RÈGLE FastAPI : routes statiques avant wildcards (KI fastapi-route-ordering).
router.include_router(folders_router)
router.include_router(files_router)
router.include_router(dlq_router)
router.include_router(ingestion_router)

public_router.include_router(files_public_router)
