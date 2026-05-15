"""ingestion_router.py — Ingestion KPIs, quality gate, batch-retry, history.
Shared imports for drive_api sub-routers."""
import logging

from shared.database import get_db
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from shared.auth.jwt import verify_jwt
from src.drive_service import DriveService
from src.services.ingestion_kpi_service import IngestionKpiService

logger = logging.getLogger(__name__)


def _require_admin(token_payload: dict = Depends(verify_jwt)) -> dict:
    """Guard : vérifie que l'appelant est administrateur."""
    if token_payload.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail="Privilèges administrateur requis pour cette opération Drive."
        )
    return token_payload


router = APIRouter(prefix="", tags=["Drive Ingestion"], dependencies=[Depends(verify_jwt)])


@router.get("/ingestion/stats")
async def get_ingestion_stats(db: AsyncSession = Depends(get_db)):
    """
    Retourne les KPIs de data quality pour le pipeline d'ingestion Drive → CV.
    Utilisé par AdminDriveIngestion pour afficher le grade global et les métriques.
    """
    service = IngestionKpiService(db)
    return await service.get_ingestion_stats()


@router.get("/ingestion/folder-kpis")
async def get_folder_kpis(db: AsyncSession = Depends(get_db)):
    """
    Retourne les KPIs d'ingestion par folder/agence.
    Utilisé par AdminDriveIngestion pour le tableau par agence.
    """
    service = IngestionKpiService(db)
    return await service.get_folder_kpis()


@router.get("/ingestion/history")
async def get_ingestion_history(limit: int = 50, db: AsyncSession = Depends(get_db)):
    """Retourne les dernières ingestions réussies avec horodatages."""
    service = IngestionKpiService(db)
    return await service.get_ingestion_history(limit)


@router.post("/ingestion/batch-retry")
async def ingestion_batch_retry(
    force: bool = False,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(_require_admin)
):
    """
    Retry simple : remet en PENDING les fichiers en ERROR et zombies bloqués,
    puis déclenche un /sync immédiat pour les republier dans Pub/Sub.
    """
    service = IngestionKpiService(db)
    result = await service.batch_retry(force=force)

    async def run_sync_after_retry():
        from shared.database import SessionLocal
        async with SessionLocal() as session:
            try:
                d_service = DriveService(session)
                processed = await d_service.ingest_batch()
                logger.info(f"[batch-retry] {processed} fichier(s) republié(s).")
            except Exception as e:
                logger.error(f"[batch-retry] Erreur sync post-retry : {e}")

    background_tasks.add_task(run_sync_after_retry)
    return {
        **result,
        "sync_triggered": True,
        "message": f"{result['total_reset']} fichier(s) remis en PENDING. Sync Pub/Sub déclenché.",
    }


@router.post("/ingestion/quality-gate-batch")
async def quality_gate_batch(
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(_require_admin)
):
    """
    Quality Gate Batch : identifie les CVs avec données incomplètes et les remet
    en PENDING pour re-traitement ciblé via Pub/Sub.
    """
    service = IngestionKpiService(db)
    result = await service.quality_gate_batch()
    total_queued = result["total_queued"]

    async def run_sync_after_gate():
        from shared.database import SessionLocal
        async with SessionLocal() as session:
            try:
                d_service = DriveService(session)
                processed = await d_service.ingest_batch()
                logger.info(f"[QualityGate] {processed} fichier(s) republié(s) dans Pub/Sub.")
            except Exception as e:
                logger.error(f"[QualityGate] Erreur sync post-gate : {e}")

    if total_queued > 0:
        background_tasks.add_task(run_sync_after_gate)

    return {
        "status": "success",
        "files_queued_for_retry": total_queued,
        "reason_breakdown": result["reason_breakdown"],
        "sync_triggered": total_queued > 0,
        "message": (
            f"{total_queued} CV(s) avec données incomplètes republiés dans Pub/Sub."
            if total_queued > 0
            else "Aucun CV incomplet détecté — data quality satisfaisante."
        ),
    }
