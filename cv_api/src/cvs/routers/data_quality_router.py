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
import os

from database import get_db
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.data_quality_publisher import publish_data_quality_snapshot
from src.services.taxonomy_batch_service import TaxonomyBatchService

logger = logging.getLogger(__name__)

# Router public (pas de JWT applicatif) — sécurisé par validation OIDC du SA
public_router = APIRouter(prefix="", tags=["Data Quality"])


def _validate_scheduler_oidc(request: Request) -> None:
    """Valide le token OIDC émis par Cloud Scheduler (SA cv_sa).

    En local dev (PUBSUB_INVOKER_SA_EMAIL absent ou placeholder), bypass contrôlé.
    En production, vérifie que l'émetteur est bien le SA cv_sa.
    Lève HTTPException(401) si invalide.
    """
    invoker_sa_email = os.getenv("PUBSUB_INVOKER_SA_EMAIL", "")
    auth_header_val = request.headers.get("Authorization", "")

    if not auth_header_val.startswith("Bearer "):
        logger.warning("[dq-snapshot] Requête sans token OIDC — rejetée.")
        raise HTTPException(status_code=401, detail="Missing OIDC token")

    # En local dev (SA non configuré), bypass contrôlé
    if not invoker_sa_email or "your-project" in invoker_sa_email:
        logger.info("[dq-snapshot] Dev local — bypass validation OIDC.")
        return

    oidc_token = auth_header_val.replace("Bearer ", "")
    try:
        audience = os.getenv(
            "PUBSUB_DQ_SNAPSHOT_AUDIENCE",
            f"https://{request.headers.get('host', '')}",
        )
        decoded = google_id_token.verify_oauth2_token(
            oidc_token,
            google_requests.Request(),
            audience=audience,
        )
        token_email = decoded.get("email", "")
        # Le scheduler utilise cv_sa comme SA OIDC — vérifier l'email du SA cv_sa
        cv_sa_email = os.getenv("CV_SA_EMAIL", invoker_sa_email)
        if token_email not in (invoker_sa_email, cv_sa_email):
            logger.warning(
                "[dq-snapshot] SA non autorisé: %s (attendus: %s, %s)",
                token_email, invoker_sa_email, cv_sa_email,
            )
            raise HTTPException(status_code=401, detail="Unauthorized scheduler invoker")
        logger.info("[dq-snapshot] OIDC validé pour %s.", token_email)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("[dq-snapshot] Échec validation OIDC: %s", exc)
        raise HTTPException(status_code=401, detail=f"Invalid OIDC token: {exc}")


@public_router.post("/pubsub/data-quality-snapshot")
async def trigger_data_quality_snapshot(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Déclenche le calcul et la publication d'un snapshot de data quality.

    Appelé par Cloud Scheduler (toutes les 4h) ou par le pipeline batch post-COMPLETED.
    Retourne 202 immédiatement — le snapshot est calculé et publié en arrière-plan.
    """
    _validate_scheduler_oidc(request)

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
