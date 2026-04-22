from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, func
from src.schemas import FolderCreate, FolderResponse, StatusResponse, FileStateResponse, FileUpdate
from src.models import DriveFolder, DriveSyncState, DriveSyncStatus
from database import get_db
import re
import asyncio
import traceback
from datetime import datetime, timedelta

from src.drive_service import DriveService
from src.redis_client import get_redis
import logging

logger = logging.getLogger(__name__)

# For Admin endpoints we should optionally check JWT. In an internal protected network, UI uses users_api gateway.
# For simplicity, we just protect it minimally or assume the M2M or Gateway ensures roles.
# Actually, the Frontend calls these. Let's add basic token validation if we want, or proxy it through a unified gateway.
# Here, we don't import `users_api` `verify_jwt` because it's a standalone service, but we could decode the auth header.
from src.auth import verify_jwt
router = APIRouter(prefix="", tags=["Drive Admin"], dependencies=[Depends(verify_jwt)])

# Basic pseudo JWT role-check stub. Since frontend calls this via Nginx /api/drive-api
def verify_admin(request: Request):
    auth = request.headers.get("Authorization")
    if not auth:
        raise HTTPException(status_code=401, detail="Missing Auth")
    # In production, decode JWT and check role="admin"
    return True


@router.post("/folders", response_model=FolderResponse)
async def add_folder(folder: FolderCreate, db: AsyncSession = Depends(get_db)):
    raw_id = folder.google_folder_id.strip()
    match = re.search(r"folders/([a-zA-Z0-9_-]+)", raw_id)
    if match:
        raw_id = match.group(1)

    existing = (await db.execute(select(DriveFolder).filter(DriveFolder.google_folder_id == raw_id))).scalars().first()
    if existing:
        raise HTTPException(status_code=400, detail="Folder ID already registered.")

    # Récupération automatique du nom du dossier Drive (nomenclature Zenika "Prénom Nom")
    resolved_folder_name = folder.folder_name  # Fallback sur la valeur manuelle si fournie
    try:
        from src.google_auth import get_drive_service
        drive = get_drive_service()
        folder_meta = drive.files().get(
            fileId=raw_id,
            fields="name",
            supportsAllDrives=True
        ).execute()
        resolved_folder_name = folder_meta.get("name") or resolved_folder_name
        logger.info(f"[add_folder] Nom Drive récupéré pour {raw_id}: '{resolved_folder_name}'")
    except Exception as e:
        logger.warning(f"[add_folder] Impossible de récupérer le nom Drive pour {raw_id}: {e}")

    db_f = DriveFolder(google_folder_id=raw_id, tag=folder.tag.strip(), folder_name=resolved_folder_name)
    db.add(db_f)
    await db.commit()
    await db.refresh(db_f)

    # Invalider le cache drive:roots
    try:
        get_redis().delete("drive:roots")
        logger.info("[Cache] drive:roots invalidé (nouveau folder enregistré).")
    except Exception as e_redis:
        logger.warning(f"[Cache] Impossible d'invalider drive:roots (Redis indisponible): {e_redis}")

    return db_f

@router.get("/folders", response_model=list[FolderResponse])
async def list_folders(db: AsyncSession = Depends(get_db)):
    folders = (await db.execute(select(DriveFolder))).scalars().all()
    
    from sqlalchemy import func
    from src.schemas import FolderStats
    from src.models import DriveSyncStatus
    
    stats_query = select(
        DriveSyncState.folder_id,
        DriveSyncState.status,
        func.count(DriveSyncState.google_file_id)
    ).group_by(DriveSyncState.folder_id, DriveSyncState.status)
    
    stats_result = (await db.execute(stats_query)).all()
    
    stats_map = {}
    for r in stats_result:
        folder_id, status, count = r
        if folder_id not in stats_map:
            stats_map[folder_id] = {}
        stats_map[folder_id][status.name] = count
        
    response_folders = []
    for f in folders:
        f_stats = stats_map.get(f.id, {})
        f_response = FolderResponse.model_validate(f)
        f_response.stats = FolderStats(
            pending=f_stats.get(DriveSyncStatus.PENDING.name, 0),
            queued=f_stats.get(DriveSyncStatus.QUEUED.name, 0),
            processing=f_stats.get(DriveSyncStatus.PROCESSING.name, 0),
            imported=f_stats.get(DriveSyncStatus.IMPORTED_CV.name, 0),
            ignored=f_stats.get(DriveSyncStatus.IGNORED_NOT_CV.name, 0),
            errors=f_stats.get(DriveSyncStatus.ERROR.name, 0)
        )
        f_response.stats.total_files = sum(f_stats.values())
        response_folders.append(f_response)
        
    return response_folders


@router.post("/folders/reset-sync")
async def reset_folder_sync(tag: str | None = None, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import update
    stmt = update(DriveFolder).values(is_initial_sync_done=False)
    if tag:
        stmt = stmt.where(DriveFolder.tag.ilike(f"%{tag}%"))
    res = await db.execute(stmt)
    await db.commit()
    return {"status": "success", "rows_updated": res.rowcount}

@router.delete("/folders/{folder_id}")
async def delete_folder(folder_id: int, db: AsyncSession = Depends(get_db)):
    f = (await db.execute(select(DriveFolder).filter(DriveFolder.id == folder_id))).scalars().first()
    if not f:
        raise HTTPException(status_code=404, detail="Not Found")
    await db.delete(f)
    await db.commit()
    # Invalider le cache drive:roots
    try:
        get_redis().delete("drive:roots")
        logger.info(f"[Cache] drive:roots invalidé (folder {folder_id} supprimé).")
    except Exception as e_redis:
        logger.warning(f"[Cache] Impossible d'invalider drive:roots (Redis indisponible): {e_redis}")
    return {"status": "deleted"}

@router.get("/status", response_model=StatusResponse)
async def get_status(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import func
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


@router.get("/files", response_model=list[FileStateResponse])
async def list_files(
    status: str | None = None,
    folder_id: int | None = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(DriveSyncState)
    if status:
        stmt = stmt.filter(DriveSyncState.status == status)
    if folder_id:
        stmt = stmt.filter(DriveSyncState.folder_id == folder_id)
        
    stmt = stmt.order_by(DriveSyncState.last_processed_at.desc().nullslast()).offset(skip).limit(limit)
    return (await db.execute(stmt)).scalars().all()

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

@router.post("/retry-errors")
async def retry_errors(db: AsyncSession = Depends(get_db)):
    """
    Remet en PENDING tous les fichiers en erreur ou bloqués (QUEUED/PROCESSING zombies).
    Appelé manuellement depuis le Frontend ("Réessayer Tout") — requiert JWT.
    Délègue à la logique métier partagée _reset_errors_to_pending.
    """
    result = await _reset_errors_to_pending(db)
    return result



async def _reset_errors_to_pending(db: AsyncSession) -> dict:
    """
    Logique métier partagée : remet en PENDING les fichiers bloqués.

    Cas traités :
    1. STATUS = ERROR : fichiers pour lesquels cv_api a retourné une erreur définitive
       (ou Pub/Sub a épuisé ses 5 retries et envoyé en DLQ).
    2. STATUS = QUEUED/PROCESSING depuis plus de 30 minutes : zombies Pub/Sub
       (message perdu, instance cv_api redémarrée, timeout non géré).

    Après reset → status = PENDING → le prochain tour de /sync les republiera
    dans Pub/Sub automatiquement.
    """
    zombie_threshold = datetime.utcnow() - timedelta(minutes=30)

    # Reset des ERROR
    stmt_errors = (
        update(DriveSyncState)
        .where(DriveSyncState.status == DriveSyncStatus.ERROR)
        .values(status=DriveSyncStatus.PENDING, error_message=None)
        .returning(DriveSyncState.google_file_id)
    )
    result_errors = await db.execute(stmt_errors)
    error_ids = [r[0] for r in result_errors.fetchall()]

    # Reset des zombies QUEUED/PROCESSING bloqués depuis > 30 min
    stmt_zombies = (
        update(DriveSyncState)
        .where(DriveSyncState.status.in_([DriveSyncStatus.QUEUED, DriveSyncStatus.PROCESSING]))
        .where(DriveSyncState.last_processed_at < zombie_threshold)
        .values(status=DriveSyncStatus.PENDING, error_message="Réinitialisé automatiquement (zombie > 30min)")
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
async def scheduled_retry_errors(db: AsyncSession = Depends(get_db)):
    """
    Drain automatique de la DLQ — appelé par Cloud Scheduler toutes les heures.

    Processus DLQ :
    1. Pub/Sub tente 5 fois de livrer un message à cv_api.
    2. Après 5 échecs, le message tombe dans la DLQ (topic zenika-cv-import-events-dead-letter).
    3. Le fichier reste en ERROR dans drive_api (via le PATCH d'erreur de cv_api).
    4. Toutes les heures, ce scheduler remet les ERROR + zombies en PENDING.
    5. Le prochain POST /sync republiera les fichiers dans le topic principal.
    6. Pub/Sub retente → pipeline complète.

    Authentification : OIDC token du SA drive_sa (pas de JWT applicatif).
    """
    result = await _reset_errors_to_pending(db)
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
        from src.google_auth import get_drive_service
        drive = get_drive_service()
        # Fast API call to verify the OAuth binding hasn't been lost or deleted
        drive.about().get(fields="user").execute()
    except Exception as e:
        logger.error(f"[DRIVE_API_AUTH_LOSS] Le Service Account a perdu l'accès au Drive: {e}")
        from fastapi.responses import JSONResponse
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
                await service.discover_files()
                
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
from src.google_auth import get_google_access_token

@router.get("/tokens/google")
async def get_google_token():
    """
    Retourne le token d'accès Google Drive (ADC) pour les opérations de réanalyse.
    Cet endpoint est protégé par verify_jwt sur le router principal.
    """
    token = get_google_access_token()
    if not token:
        raise HTTPException(status_code=500, detail="Impossible de générer le token Google ADC.")
    return {"access_token": token}
from src.schemas import FileUpdate

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
    if update_data.error_message is not None:
        file_state.error_message = update_data.error_message
        
    await db.commit()
    await db.refresh(file_state)
    return file_state
