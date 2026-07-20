"""folders_router.py — Gestion des dossiers Google Drive cibles.
Shared imports for drive_api sub-routers."""

import asyncio
import logging
from shared.database import get_db
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from shared.auth.jwt import verify_jwt
from shared.cache import delete_cache, set_cache, get_cache
from src.drive_service import DriveService
from src.models import DriveSyncStatus
from src.schemas import FolderCreate, FolderResponse, FolderStats, FolderUpdate, PaginatedFoldersResponse
from src.services.folder_service import FolderService
from src.google_auth import get_drive_service
import shared.database as shared_db

logger = logging.getLogger(__name__)


def _require_admin(token_payload: dict = Depends(verify_jwt)) -> dict:
    """Guard : vérifie que l'appelant est administrateur."""
    if token_payload.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail="Privilèges administrateur requis pour cette opération Drive."
        )
    return token_payload


router = APIRouter(prefix="", tags=["Drive Folders"], dependencies=[Depends(verify_jwt)])


@router.post("/folders", response_model=FolderResponse)
async def add_folder(folder: FolderCreate, db: AsyncSession = Depends(get_db), _: dict = Depends(_require_admin)):
    service = FolderService(db)
    db_f = await service.add_folder(folder)
    return db_f


@router.patch("/folders/{folder_id}", response_model=FolderResponse)
async def update_folder(
    folder_id: int,
    folder_update: FolderUpdate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(_require_admin)
):
    service = FolderService(db)
    folder = await service.update_folder(folder_id, folder_update)
    f_response = FolderResponse.model_validate(folder)
    return f_response


@router.get("/folders", response_model=PaginatedFoldersResponse)
async def list_folders(db: AsyncSession = Depends(get_db), skip: int = 0, limit: int = 50):
    service = FolderService(db)
    folders, stats_map, total = await service.list_folders_with_stats(skip, limit)

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

    return {"items": response_folders, "total": total, "skip": skip, "limit": limit}


@router.post("/folders/reset-sync")
async def reset_folder_sync(
    tag: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(_require_admin)
):
    service = FolderService(db)
    rows_updated = await service.reset_folder_sync(tag)
    return {"status": "success", "rows_updated": rows_updated}


@router.post("/folders/rebuild-tree")
async def rebuild_folder_tree(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(_require_admin)
):
    """
    Force un scan complet de l'arbre Drive pour réparer les structures parent_folder_name manquantes,
    SANS repasser les statuts en PENDING pour les fichiers déjà importés et non modifiés.
    """
    async def run_rebuild():
        try:
            await set_cache("drive:sync:rebuild_running", "1", 1800)  # 30 min max
            async with shared_db.SessionLocal() as session:
                service = DriveService(session)
                await service.discover_files(force_full=True)
        finally:
            await delete_cache("drive:sync:rebuild_running")

    background_tasks.add_task(run_rebuild)
    return {"status": "success", "message": "Reconstruction de l'arbre lancée en arrière-plan"}


@router.get("/folders/by-name/{name}")
async def get_folder_by_name(name: str):
    """
    Retourne l'ID Google Drive du dossier d'un consultant à partir de son nom.
    """
    cache_key = f"drive:folder_id_by_name:{name.lower()}"
    folder_id = await get_cache(cache_key)

    if not folder_id:
        try:
            drive_service = get_drive_service()
            q = f"mimeType = 'application/vnd.google-apps.folder' and name = '{name}' and trashed = false"
            results = await asyncio.to_thread(
                lambda: drive_service.files().list(
                    q=q,
                    spaces="drive",
                    includeItemsFromAllDrives=True,
                    supportsAllDrives=True,
                    fields="files(id)",
                    pageSize=1
                ).execute()
            )
            files = results.get("files", [])
            if files:
                folder_id = files[0].get("id")
                await set_cache(cache_key, folder_id, 86400 * 30)
        except Exception as e:
            logger.warning(f"Failed to query Google Drive for folder name '{name}': {e}")

    if not folder_id:
        raise HTTPException(status_code=404, detail=f"Dossier Drive pour '{name}' introuvable.")

    return {
        "folder_name": name,
        "google_folder_id": folder_id,
        "url": f"https://drive.google.com/drive/folders/{folder_id}"
    }


@router.get("/folders/by-file/{google_file_id}")
async def get_folder_by_file(google_file_id: str):
    """
    Retourne l'ID Google Drive et l'URL du dossier parent d'un fichier donné.
    """
    try:
        drive_service = get_drive_service()
        # Fetch the file metadata to get its parents
        file_meta = await asyncio.to_thread(
            lambda: drive_service.files().get(
                fileId=google_file_id,
                fields="parents,name",
                supportsAllDrives=True
            ).execute()
        )
        parents = file_meta.get("parents", [])
        if not parents:
            raise HTTPException(status_code=404, detail="Aucun dossier parent trouvé pour ce fichier.")

        parent_id = parents[0]
        # Get parent name
        parent_meta = await asyncio.to_thread(
            lambda: drive_service.files().get(
                fileId=parent_id,
                fields="name",
                supportsAllDrives=True
            ).execute()
        )
        parent_name = parent_meta.get("name", "Dossier Consultant")

        return {
            "google_folder_id": parent_id,
            "folder_name": parent_name,
            "url": f"https://drive.google.com/drive/folders/{parent_id}"
        }
    except Exception as e:
        logger.error(f"Failed to resolve parent folder for file {google_file_id}: {e}")
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/folders/invalidate-cache")
async def invalidate_drive_cache(_: dict = Depends(_require_admin)):
    keys_deleted = await FolderService.invalidate_drive_cache()
    return {"status": "success", "keys_deleted": keys_deleted}


@router.delete("/folders/{folder_id}")
async def delete_folder(folder_id: int, db: AsyncSession = Depends(get_db), _: dict = Depends(_require_admin)):
    service = FolderService(db)
    files_removed = await service.delete_folder(folder_id)
    return {"status": "deleted", "files_removed": files_removed}
