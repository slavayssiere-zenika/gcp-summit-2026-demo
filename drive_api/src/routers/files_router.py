"""files_router.py — Statut des fichiers, sync, retry, tokens, consultant search."""
"""Shared imports for drive_api sub-routers."""
import base64 as _b64
import os as _os
import json as _json
import re
import asyncio
import traceback
import logging
from datetime import datetime, timedelta

import google.auth
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from google.cloud import pubsub_v1
from google.api_core.exceptions import DeadlineExceeded
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, func

from src.schemas import (FolderCreate, FolderResponse, StatusResponse,
    FileStateResponse, PaginatedFilesResponse, FileUpdate, FolderStats, FolderUpdate)
from src.models import DriveFolder, DriveSyncState, DriveSyncStatus
from src.google_auth import get_google_access_token, get_drive_service
from database import get_db
from src.drive_service import DriveService
from src.redis_client import get_redis
from src.auth import verify_jwt

logger = logging.getLogger(__name__)


def _require_admin(token_payload: dict = Depends(verify_jwt)) -> dict:
    """Guard : vérifie que l'appelant est administrateur."""
    if token_payload.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail="Privilèges administrateur requis pour cette opération Drive."
        )
    return token_payload

router = APIRouter(prefix="", tags=["Drive Files"], dependencies=[Depends(verify_jwt)])
public_router = APIRouter(prefix="", tags=["Drive_Public"])

@router.get("/status", response_model=StatusResponse)
async def get_status(db: AsyncSession = Depends(get_db)):
    total = (await db.execute(select(func.count()).select_from(DriveSyncState))).scalar()
    
    pending_q = select(func.count()).select_from(select(DriveSyncState).filter(DriveSyncState.status == DriveSyncStatus.PENDING).subquery())
    pending = (await db.execute(pending_q)).scalar()

    proc_q = select(func.count()).select_from(select(DriveSyncState).filter(DriveSyncState.status == DriveSyncStatus.PROCESSING).subquery())
    proc = (await db.execute(proc_q)).scalar()
    
    imp_q = select(func.count()).select_from(select(DriveSyncState).filter(DriveSyncState.status == DriveSyncStatus.IMPORTED_CV).subquery())
    imp = (await db.execute(imp_q)).scalar()
    
    ign_q = select(func.count()).select_from(select(DriveSyncState).filter(DriveSyncState.status == DriveSyncStatus.IGNORED_NOT_CV).subquery())
    ign = (await db.execute(ign_q)).scalar()

    queued_q = select(func.count()).select_from(select(DriveSyncState).filter(DriveSyncState.status == DriveSyncStatus.QUEUED).subquery())
    queued = (await db.execute(queued_q)).scalar()
    
    err_q = select(func.count()).select_from(select(DriveSyncState).filter(DriveSyncState.status == DriveSyncStatus.ERROR).subquery())
    err = (await db.execute(err_q)).scalar()
    
    last_p = (await db.execute(select(func.max(DriveSyncState.last_processed_at)))).scalar()
    
    return StatusResponse(
        total_files_scanned=total,
        pending=pending,
        queued=queued,
        processing=proc,
        imported=imp,
        ignored=ign,
        errors=err,
        last_processed_time=last_p
    )



@router.get("/files", response_model=PaginatedFilesResponse)
async def list_files(
    status: str | None = None,
    folder_id: int | None = None,
    search: str | None = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(DriveSyncState)
    if status:
        stmt = stmt.filter(DriveSyncState.status == status)
    if folder_id:
        stmt = stmt.filter(DriveSyncState.folder_id == folder_id)
    if search:
        stmt = stmt.filter(DriveSyncState.parent_folder_name.ilike(f"%{search}%"))
        
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0
        
    stmt = stmt.order_by(DriveSyncState.last_processed_at.desc().nullslast()).offset(skip).limit(limit)
    files = (await db.execute(stmt)).scalars().all()
    
    return {
        "files": files,
        "total": total,
        "skip": skip,
        "limit": limit
    }


@router.get("/files/{google_file_id}", response_model=FileStateResponse)
async def get_file_state(google_file_id: str, db: AsyncSession = Depends(get_db)):
    """
    Retourne l'état de synchronisation Drive pour un fichier donné par son ID Google.
    Utilisé par cv_api (reanalyze) pour récupérer le parent_folder_name (nomenclature Zenika).
    """
    state = (
        await db.execute(
            select(DriveSyncState).filter(DriveSyncState.google_file_id == google_file_id)
        )
    ).scalars().first()
    if not state:
        raise HTTPException(status_code=404, detail=f"Fichier Drive '{google_file_id}' inconnu.")
    return state



@router.get("/consultant/search")
async def search_consultant_files(
    name: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Endpoint de diagnostic : recherche tous les fichiers d'un consultant par nom de dossier (ILIKE).
    Retourne le parent_folder_name, status, user_id et folder_id pour chaque fichier trouvé.
    Utile pour investiguer les consultants manquants dans le graphe.
    Exemple : GET /drive/consultant/search?name=Lavayssière
    """
    stmt = (
        select(DriveSyncState)
        .filter(DriveSyncState.parent_folder_name.ilike(f"%{name}%"))
        .order_by(DriveSyncState.parent_folder_name)
    )
    results = (await db.execute(stmt)).scalars().all()

    return {
        "query": name,
        "count": len(results),
        "files": [
            {
                "google_file_id": r.google_file_id,
                "file_name": r.file_name,
                "parent_folder_name": r.parent_folder_name,
                "status": r.status,
                "user_id": r.user_id,
                "folder_id": r.folder_id,
                "error_message": r.error_message,
            }
            for r in results
        ],
    }


@router.post("/retry-errors")
async def retry_errors(force: bool = False, db: AsyncSession = Depends(get_db)):
    """
    Remet en PENDING tous les fichiers en erreur ou bloqués (QUEUED/PROCESSING zombies).
    Appelé manuellement depuis le Frontend ("Réessayer Tout") — requiert JWT.
    Paramètre `force=true` : bypass du seuil zombie (10 min) — reset immédiat de TOUS les QUEUED/PROCESSING.
    Délègue à la logique métier partagée _reset_errors_to_pending.
    """
    result = await _reset_errors_to_pending(db, force=force)
    return result


@router.delete("/errors")
async def clear_all_errors(db: AsyncSession = Depends(get_db), _: dict = Depends(_require_admin)):
    """
    Supprime toutes les erreurs actuelles en basculant leur statut a IGNORED.
    Utile pour purger les erreurs persistantes du pipeline.
    """
    stmt = (
        update(DriveSyncState)
        .where(DriveSyncState.status == DriveSyncStatus.ERROR)
        .values(status=DriveSyncStatus.IGNORED_NOT_CV, error_message="Erreur purgee par un administrateur")
    )
    result = await db.execute(stmt)
    await db.commit()
    logger.info(f"Purge des erreurs : {result.rowcount} fichiers marques comme IGNORED.")
    return {"status": "success", "cleared_count": result.rowcount}



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
    zombie_threshold = datetime.utcnow() - timedelta(minutes=30)

    # Reset des ERROR
    stmt_errors = (
        update(DriveSyncState)
        .where(DriveSyncState.status == DriveSyncStatus.ERROR)
        .values(status=DriveSyncStatus.PENDING, error_message=None, last_processed_at=datetime.utcnow())
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
            error_message="Réinitialisé automatiquement (zombie > 30min)" if not force else "Réinitialisé manuellement (force flush)",
            last_processed_at=datetime.utcnow()  # réinitialise le timer affiché dans l'UI
        )
        .returning(DriveSyncState.google_file_id)
    )
    result_zombies = await db.execute(stmt_zombies)
    zombie_ids = [r[0] for r in result_zombies.fetchall()]

    await db.commit()

    total = len(error_ids) + len(zombie_ids)
    logger.info(
        f"[retry-errors] Reset terminé — {len(error_ids)} erreurs + {len(zombie_ids)} zombies → PENDING. Total: {total}",
        extra={"errors_reset": len(error_ids), "zombies_reset": len(zombie_ids)}
    )
    return {
        "status": "success",
        "errors_reset": len(error_ids),
        "zombies_reset": len(zombie_ids),
        "total_reset": total,
    }


# NOTE SÉCURITÉ: Cette route est intentionnellement exclue du routeur protégé par verify_jwt.
# La sécurité est assurée par IAM Cloud Run : seul le Service Account `drive_sa`
# (roles/run.invoker) peut appeler cet endpoint via le Cloud Scheduler (oidc_token).
# Un JWT applicatif ne peut pas être utilisé ici car le Scheduler émet un token OIDC Google.
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
        from database import SessionLocal
        async with SessionLocal() as session:
            try:
                service = DriveService(session)
                
                try:
                    await service.discover_files()
                except Exception as discover_err:
                    logger.error(f"Erreur durant la découverte Drive (discover_files), on continue l'ingestion: {discover_err}")
                
                total_processed = 0
                while True:
                    processed = await service.ingest_batch()
                    if processed == 0:
                        break
                    total_processed += processed
                    
                logger.info(f"Fin de la synchronisation avec Google Drive. (CV traités: {total_processed})")
            except Exception as e:
                logger.error(f"Erreur durant la synchronisation Google Drive: {e}")
                import traceback
                traceback.print_exc()

    background_tasks.add_task(run_sync)
    return {"status": "started"}


@router.get("/tokens/google")
async def get_google_token(_: dict = Depends(_require_admin)):
    """
    Retourne le token d'accès Google Drive (ADC) pour les opérations de réanalyse.
    Cet endpoint est protégé par verify_jwt sur le router principal.
    """
    token = get_google_access_token()
    if not token:
        raise HTTPException(status_code=500, detail="Impossible de générer le token Google ADC.")
    return {"access_token": token}


# ── DLQ (Dead Letter Queue) Management ───────────────────────────────────────


def _get_dlq_subscription_path() -> str:
    """Retourne le chemin complet de la subscription DLQ Pub/Sub."""
    project_id = _os.getenv("PUBSUB_PROJECT_ID", "")
    workspace = _os.getenv("WORKSPACE", "dev")
    sub_name = _os.getenv("PUBSUB_DLQ_SUBSCRIPTION", f"cv-import-events-dlq-sub-{workspace}")
    if not project_id:
        _, project_id = google.auth.default()
    return f"projects/{project_id}/subscriptions/{sub_name}"



@router.patch("/files/{file_id}", response_model=FileStateResponse)
async def update_file(file_id: str, update_data: FileUpdate, db: AsyncSession = Depends(get_db)):
    """
    Updates a file's state (user_id and/or status).
    Used by other services to fix identity assignments.
    """
    stmt = select(DriveSyncState).filter(DriveSyncState.google_file_id == file_id)
    file_state = (await db.execute(stmt)).scalars().first()
    
    if not file_state:
        raise HTTPException(status_code=404, detail="File not found")
        
    if update_data.user_id is not None:
        file_state.user_id = update_data.user_id
    if update_data.status is not None:
        file_state.status = update_data.status
        # Fix #3 : invalider le cache Redis quand un fichier repasse en PENDING
        # pour que discover_files() ne le skippe pas lors du prochain /sync.
        if str(update_data.status) in ("PENDING", DriveSyncStatus.PENDING.value):
            try:
                get_redis().delete(f"drive:file:known:{file_id}")
                logger.info(f"[Cache] drive:file:known:{file_id} invalidé (status → PENDING).")
            except Exception as e_redis:
                logger.warning(f"[Cache] Impossible d'invalider drive:file:known:{file_id}: {e_redis}")
    if update_data.error_message is not None:
        file_state.error_message = update_data.error_message
    if update_data.processing_duration_ms is not None:
        file_state.processing_duration_ms = update_data.processing_duration_ms
    
    if str(update_data.status) == DriveSyncStatus.IMPORTED_CV.value or update_data.status == DriveSyncStatus.IMPORTED_CV:
        file_state.imported_at = datetime.utcnow()
        
    await db.commit()
    await db.refresh(file_state)
    return file_state


# ── Ingestion KPIs & Quality Gate ─────────────────�

# ── Ingestion KPIs & Quality Gate ─────────────────────────────────────────────

def _compute_kpi_metric(ok: int, total: int, warning_pct: float, critical_pct: float, unit: str = "%") -> dict:
    """Helper : calcule le statut d'une métrique selon les seuils."""
    if total == 0:
        return {"value": 0.0, "pct": 0.0, "ok": 0, "total": 0, "status": "ok", "unit": unit}
    pct = min(100.0, round((ok / total) * 100, 1))
    if pct < critical_pct:
        status = "critical"
    elif pct < warning_pct:
        status = "warning"
    else:
        status = "ok"
    return {"value": pct, "pct": pct, "ok": ok, "total": total, "status": status, "unit": unit}


