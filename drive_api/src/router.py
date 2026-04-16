from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from src.schemas import FolderCreate, FolderResponse, StatusResponse
from src.models import DriveFolder, DriveSyncState, DriveSyncStatus
from database import get_db
import traceback

from src.drive_service import DriveService
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

import re

@router.post("/folders", response_model=FolderResponse)
async def add_folder(folder: FolderCreate, db: AsyncSession = Depends(get_db)):
    raw_id = folder.google_folder_id.strip()
    match = re.search(r"folders/([a-zA-Z0-9_-]+)", raw_id)
    if match:
        raw_id = match.group(1)
        
    existing = (await db.execute(select(DriveFolder).filter(DriveFolder.google_folder_id == raw_id))).scalars().first()
    if existing:
        raise HTTPException(status_code=400, detail="Folder ID already registered.")
        
    db_f = DriveFolder(google_folder_id=raw_id, tag=folder.tag.strip())
    db.add(db_f)
    await db.commit()
    await db.refresh(db_f)
    return db_f

@router.get("/folders", response_model=list[FolderResponse])
async def list_folders(db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(DriveFolder))).scalars().all()

@router.delete("/folders/{folder_id}")
async def delete_folder(folder_id: int, db: AsyncSession = Depends(get_db)):
    f = (await db.execute(select(DriveFolder).filter(DriveFolder.id == folder_id))).scalars().first()
    if not f:
        raise HTTPException(status_code=404, detail="Not Found")
    await db.delete(f)
    await db.commit()
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
    
    err_q = select(func.count()).select_from(select(DriveSyncState).filter(DriveSyncState.status == DriveSyncStatus.ERROR).subquery())
    err = (await db.execute(err_q)).scalar()
    
    last_p = (await db.execute(select(func.max(DriveSyncState.last_processed_at)))).scalar()
    
    return StatusResponse(
        total_files_scanned=total,
        pending=pending,
        processing=proc,
        imported=imp,
        ignored=ign,
        errors=err,
        last_processed_time=last_p
    )

from src.schemas import FileStateResponse
from sqlalchemy import update

@router.get("/files", response_model=list[FileStateResponse])
async def list_files(db: AsyncSession = Depends(get_db)):
    # Returns all tracked files ordered by most recent first
    return (await db.execute(select(DriveSyncState).order_by(DriveSyncState.last_processed_at.desc().nullslast()))).scalars().all()

@router.post("/retry-errors")
async def retry_errors(db: AsyncSession = Depends(get_db)):
    # Flips all ERROR states back to PENDING so the next batch ingestion will retry them
    from src.models import DriveSyncStatus
    stmt = update(DriveSyncState).where(DriveSyncState.status == DriveSyncStatus.ERROR).values(status=DriveSyncStatus.PENDING)
    res = await db.execute(stmt)
    await db.commit()
    return {"status": "success", "rows_updated": res.rowcount}

import asyncio

from fastapi import BackgroundTasks

# NOTE SÉCURITÉ: Cette route est intentionnellement exclue du routeur protégé par verify_jwt.
# La sécurité est assurée par IAM Cloud Run : seul le Service Account `drive_sa`
# (roles/run.invoker) peut appeler cet endpoint via le Cloud Scheduler (oidc_token).
# Un JWT applicatif ne peut pas être utilisé ici car le Scheduler émet un token OIDC Google.
public_router = APIRouter(prefix="", tags=["Drive Sync - IAM Protected"])

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
                processed = await service.ingest_batch()
                logger.info(f"Fin de la synchronisation avec Google Drive. (CV traités: {processed})")
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
        
    await db.commit()
    await db.refresh(file_state)
    return file_state
