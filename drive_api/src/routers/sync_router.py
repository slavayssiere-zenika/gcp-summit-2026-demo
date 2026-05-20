"""
sync_router.py — Routes de synchronisation Drive protégées par IAM Cloud Run.

Extrait de files_router.py (God module) — 2026-05-14.

Routes (IAM-only, sans JWT) :
  POST  /scheduled/retry-errors   — DLQ drain automatique (Cloud Scheduler)
  POST  /sync                     — Synchronisation Drive (Cloud Scheduler)

Logique métier partagée :
  _reset_errors_to_pending()      — Importée par files_router + ingestion_kpi_service
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from shared.database import get_db
from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from src.drive_service import DriveService
from src.google_auth import get_drive_service
from src.models import DriveSyncState, DriveSyncStatus
from shared.database import SessionLocal
import traceback

logger = logging.getLogger(__name__)


async def _reset_errors_to_pending(db: AsyncSession, force: bool = False) -> dict:
    """
    Logique métier partagée : remet en PENDING les fichiers bloqués.

    Cas traités :
    1. STATUS = ERROR : fichiers pour lesquels cv_api a retourné une erreur définitive
       (ou Pub/Sub a épuisé ses 5 retries et envoyé en DLQ).
    2. STATUS = QUEUED/PROCESSING depuis plus de 10 minutes : zombies Pub/Sub
       (message perdu, instance cv_api redémarrée, timeout non géré).
    3. Si force=True : réinitialise immédiatement TOUS les QUEUED/PROCESSING
       sans attendre le seuil de 30 min. Utile après une réanalyse massive
       où des fichiers sont bloqués suite à un JWT expiré (pré-fix #4).

    Après reset → status = PENDING → le prochain tour de /sync les republiera
    dans Pub/Sub automatiquement.
    """
    zombie_threshold = datetime.now(timezone.utc) - timedelta(minutes=30)

    # Reset des ERROR
    # Circuit breaker: on abandonne après 3 échecs (passage en IGNORED_NOT_CV)
    stmt_failed = (
        update(DriveSyncState)
        .where(DriveSyncState.status == DriveSyncStatus.ERROR)
        .where(DriveSyncState.retry_count >= 3)
        .values(
            status=DriveSyncStatus.IGNORED_NOT_CV,
            error_message="Circuit breaker: Echec définitif après 3 tentatives d'import"
        )
    )
    await db.execute(stmt_failed)

    # Pour ceux qui n'ont pas encore atteint la limite, on incrémente le retry_count et on remet en PENDING
    stmt_errors = (
        update(DriveSyncState)
        .where(DriveSyncState.status == DriveSyncStatus.ERROR)
        .where(DriveSyncState.retry_count < 3)
        .values(
            status=DriveSyncStatus.PENDING,
            error_message=None,
            last_processed_at=datetime.now(timezone.utc),
            retry_count=DriveSyncState.retry_count + 1
        )
        .returning(DriveSyncState.google_file_id)
    )
    result_errors = await db.execute(stmt_errors)
    error_ids = [r[0] for r in result_errors.fetchall()]

    # Reset des zombies QUEUED/PROCESSING — avec ou sans filtre temporel
    stmt_zombies = (
        update(DriveSyncState)
        .where(DriveSyncState.status.in_([DriveSyncStatus.QUEUED, DriveSyncStatus.PROCESSING]))
    )
    if not force:
        stmt_zombies = stmt_zombies.where(DriveSyncState.last_processed_at < zombie_threshold)
    stmt_zombies = (
        stmt_zombies
        .values(
            status=DriveSyncStatus.PENDING,
            error_message=(
                "Réinitialisé automatiquement (zombie > 30min)" if not force
                else "Réinitialisé manuellement (force flush)"
            ),
            last_processed_at=datetime.now(timezone.utc)  # réinitialise le timer affiché dans l'UI
        )
        .returning(DriveSyncState.google_file_id)
    )
    result_zombies = await db.execute(stmt_zombies)
    zombie_ids = [r[0] for r in result_zombies.fetchall()]

    await db.commit()

    total = len(error_ids) + len(zombie_ids)
    logger.info(
        "[retry-errors] Reset terminé — %d erreurs + %d zombies → PENDING. Total: %d",
        len(error_ids), len(zombie_ids), total,
        extra={"errors_reset": len(error_ids), "zombies_reset": len(zombie_ids)}
    )
    return {
        "status": "success",
        "errors_reset": len(error_ids),
        "zombies_reset": len(zombie_ids),
        "total_reset": total,
    }


# NOTE SÉCURITÉ: Routes exclues du routeur protégé par verify_jwt.
# Sécurité assurée par IAM Cloud Run : seul le Service Account `drive_sa`
# (roles/run.invoker) peut appeler ces endpoints via le Cloud Scheduler (oidc_token).

public_router = APIRouter(prefix="", tags=["Drive Sync - IAM Protected"])


@public_router.post("/scheduled/retry-errors")
async def scheduled_retry_errors(force: bool = False, db: AsyncSession = Depends(get_db)):
    """
    Drain automatique de la DLQ — appelé par Cloud Scheduler toutes les heures.
    Accepte aussi force=true pour forcer le déblocage immédiat depuis un outil externe.
    """
    result = await _reset_errors_to_pending(db, force=force)
    logger.info(f"[Scheduler] DLQ drain automatique : {result['total_reset']} fichiers remis en queue.")
    return result


@public_router.post("/sync")
async def trigger_sync(background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """
    Called by GCP Cloud Scheduler every X minutes.
    Performs discovery and then processes a batch.
    Protected by Cloud Run IAM (OIDC token from Scheduler SA), NOT by JWT.
    """
    logger.info("Début de la synchronisation avec Google Drive.")

    # 1. Verification synchrone des droits d'accès
    try:
        drive = get_drive_service()
        # Fast API call to verify the OAuth binding hasn't been lost or deleted
        await asyncio.to_thread(lambda: drive.about().get(fields="user").execute())
    except Exception as e:
        logger.error(f"[DRIVE_API_AUTH_LOSS] Le Service Account a perdu l'accès au Drive: {e}")
        return JSONResponse(
            status_code=403,
            content={"status": "error", "message": "SERVICE_ACCOUNT_ACCESS_LOSS", "details": str(e)}
        )

    async def run_sync():
        # Get a new DB session since the one in dependency might close
        async with SessionLocal() as session:
            try:
                service = DriveService(session)

                try:
                    await service.discover_files()
                except Exception as discover_err:
                    logger.error(
                        f"Erreur durant la découverte Drive (discover_files), on continue l'ingestion: {discover_err}")

                total_processed = 0
                while True:
                    processed = await service.ingest_batch()
                    if processed == 0:
                        break
                    total_processed += processed

                logger.info(f"Fin de la synchronisation avec Google Drive. (CV traités: {total_processed})")
            except Exception as e:
                logger.error(f"Erreur durant la synchronisation Google Drive: {e}")
                traceback.print_exc()

    background_tasks.add_task(run_sync)
    return {"status": "started"}
