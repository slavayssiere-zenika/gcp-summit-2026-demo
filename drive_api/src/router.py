from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from src.schemas import FolderCreate, FolderResponse, StatusResponse
from src.models import DriveFolder, DriveSyncState, DriveSyncStatus
from database import get_db
import traceback

from src.drive_service import DriveService

# For Admin endpoints we should optionally check JWT. In an internal protected network, UI uses users_api gateway.
# For simplicity, we just protect it minimally or assume the M2M or Gateway ensures roles.
# Actually, the Frontend calls these. Let's add basic token validation if we want, or proxy it through a unified gateway.
# Here, we don't import `users_api` `verify_jwt` because it's a standalone service, but we could decode the auth header.
router = APIRouter(prefix="/drive-api", tags=["Drive Admin"])

# Basic pseudo JWT role-check stub. Since frontend calls this via Nginx /api/drive-api
def verify_admin(request: Request):
    auth = request.headers.get("Authorization")
    if not auth:
        raise HTTPException(status_code=401, detail="Missing Auth")
    # In production, decode JWT and check role="admin"
    return True

@router.post("/folders", response_model=FolderResponse)
async def add_folder(folder: FolderCreate, db: Session = Depends(get_db)):
    existing = db.query(DriveFolder).filter(DriveFolder.google_folder_id == folder.google_folder_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Folder ID already registered.")
        
    db_f = DriveFolder(google_folder_id=folder.google_folder_id, tag=folder.tag)
    db.add(db_f)
    db.commit()
    db.refresh(db_f)
    return db_f

@router.get("/folders", response_model=list[FolderResponse])
async def list_folders(db: Session = Depends(get_db)):
    return db.query(DriveFolder).all()

@router.delete("/folders/{folder_id}")
async def delete_folder(folder_id: int, db: Session = Depends(get_db)):
    f = db.query(DriveFolder).filter(DriveFolder.id == folder_id).first()
    if not f:
        raise HTTPException(status_code=404, detail="Not Found")
    db.delete(f)
    db.commit()
    return {"status": "deleted"}

@router.get("/status", response_model=StatusResponse)
async def get_status(db: Session = Depends(get_db)):
    total = db.query(DriveSyncState).count()
    pending = db.query(DriveSyncState).filter(DriveSyncState.status == DriveSyncStatus.PENDING).count()
    imp = db.query(DriveSyncState).filter(DriveSyncState.status == DriveSyncStatus.IMPORTED_CV).count()
    ign = db.query(DriveSyncState).filter(DriveSyncState.status == DriveSyncStatus.IGNORED_NOT_CV).count()
    err = db.query(DriveSyncState).filter(DriveSyncState.status == DriveSyncStatus.ERROR).count()
    
    from sqlalchemy import func
    last_p = db.query(func.max(DriveSyncState.last_processed_at)).scalar()
    
    return StatusResponse(
        total_files_scanned=total,
        pending=pending,
        imported=imp,
        ignored=ign,
        errors=err,
        last_processed_time=last_p
    )

import asyncio

@router.post("/sync")
async def trigger_sync(db: Session = Depends(get_db)):
    """
    Called by GCP Cloud Scheduler every X minutes.
    Performs discovery and then processes a batch.
    """
    try:
        service = DriveService(db)
        
        # 1. Delta Discovery (Runs in threadpool to avoid blocking async loop since google-api-python-client is sync)
        await asyncio.to_thread(service.discover_files)
        
        # 2. Batch Processing (Natively async httpx requests)
        processed = await service.ingest_batch()
        
        return {"status": "success", "processed_batch": processed}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
