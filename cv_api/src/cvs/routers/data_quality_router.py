"""
data_quality_router.py — Endpoint déclencheur du snapshot de data quality.

Déclenché par :
  1. Cloud Scheduler (toutes les 4h) via POST /pubsub/data-quality-snapshot
     Authentifié via OIDC (SA cv_sa), même pattern que le taxonomy_batch_polling.
  2. taxonomy_batch_service.py (post-batch COMPLETED) via call interne.

Ce router est SANS JWT applicatif (public_router) — la sécurité repose sur
la validation OIDC du SA cv_sa qui est le seul à appeler cet endpoint.
"""
import logging

from shared.database import get_db
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from shared.auth.jwt import VerifyOIDC
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.data_quality_publisher import publish_data_quality_snapshot
from src.services.taxonomy_batch_service import TaxonomyBatchService

logger = logging.getLogger(__name__)

# Router public (pas de JWT applicatif) — sécurisé par validation OIDC du SA
public_router = APIRouter(prefix="", tags=["Data Quality"])


verify_oidc = VerifyOIDC(audience_env_var="PUBSUB_DQ_SNAPSHOT_AUDIENCE")


@public_router.post("/pubsub/data-quality-snapshot")
async def trigger_data_quality_snapshot(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _oidc: dict = Depends(verify_oidc),
):
    """Déclenche le calcul et la publication d'un snapshot de data quality.

    Appelé par Cloud Scheduler (toutes les 4h) ou par le pipeline batch post-COMPLETED.
    Retourne 202 immédiatement — le snapshot est calculé et publié en arrière-plan.
    """

    # Génération d'un service token autonome pour les appels HTTP sortants
    # (compétencies_api, etc.) — identique au pattern taxonomy_batch_service.
    svc_token = await TaxonomyBatchService.generate_autonomous_service_token()
    auth_header = f"Bearer {svc_token}" if svc_token else ""

    background_tasks.add_task(
        publish_data_quality_snapshot,
        None,
        auth_header,
        "scheduler",
    )
    logger.info("[dq-snapshot] Snapshot planifié en arrière-plan (trigger=scheduler).")
    return {"status": "accepted"}
