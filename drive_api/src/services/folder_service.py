import logging
import re
from sqlalchemy import func, update, select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from shared.cache import delete_cache, clear_namespace
from src.models import DriveFolder, DriveSyncState
from src.schemas import FolderCreate, FolderUpdate
from src.google_auth import get_drive_service
import asyncio

logger = logging.getLogger(__name__)


class FolderService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def add_folder(self, folder: FolderCreate) -> DriveFolder:
        raw_id = folder.google_folder_id.strip()
        match = re.search(r"folders/([a-zA-Z0-9_-]+)", raw_id)
        if match:
            raw_id = match.group(1)

        existing = (await self.db.execute(select(DriveFolder).filter(DriveFolder.google_folder_id == raw_id))).scalars().first()
        if existing:
            raise HTTPException(status_code=400, detail="Folder ID already registered.")

        existing_tag = (await self.db.execute(select(DriveFolder).filter(DriveFolder.tag == folder.tag.strip()))).scalars().first()
        if existing_tag:
            raise HTTPException(
                status_code=409,
                detail=f"Tag '{folder.tag.strip()}' already used by folder '{existing_tag.folder_name or existing_tag.google_folder_id}'. Tags must be unique."
            )

        resolved_folder_name = folder.folder_name
        try:
            drive = get_drive_service()
            folder_meta = await asyncio.to_thread(
                lambda: drive.files().get(fileId=raw_id, fields="name", supportsAllDrives=True).execute()
            )
            resolved_folder_name = folder_meta.get("name") or resolved_folder_name
            logger.info(f"[add_folder] Nom Drive récupéré pour {raw_id}: '{resolved_folder_name}'")
        except Exception as e:
            logger.warning(f"[add_folder] Impossible de récupérer le nom Drive pour {raw_id}: {e}")

        db_f = DriveFolder(google_folder_id=raw_id, tag=folder.tag.strip(),
                           folder_name=resolved_folder_name, excluded_folders=folder.excluded_folders)
        self.db.add(db_f)
        await self.db.commit()
        await self.db.refresh(db_f)

        try:
            await delete_cache("drive:roots")
            logger.info("[Cache] drive:roots invalidé (nouveau folder enregistré).")
        except Exception as e_redis:
            logger.warning(f"[Cache] Impossible d'invalider drive:roots (Redis indisponible): {e_redis}")

        return db_f

    async def update_folder(self, folder_id: int, folder_update: FolderUpdate) -> DriveFolder:
        folder = (await self.db.execute(select(DriveFolder).filter(DriveFolder.id == folder_id))).scalars().first()
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found")

        if folder_update.tag is not None:
            new_tag = folder_update.tag.strip()
            existing_tag = (await self.db.execute(select(DriveFolder).filter(DriveFolder.tag == new_tag, DriveFolder.id != folder_id))).scalars().first()
            if existing_tag:
                raise HTTPException(
                    status_code=409,
                    detail=f"Tag '{new_tag}' already used by folder '{existing_tag.folder_name or existing_tag.google_folder_id}'. Tags must be unique."
                )
            folder.tag = new_tag

        if folder_update.excluded_folders is not None:
            folder.excluded_folders = folder_update.excluded_folders

        await self.db.commit()
        await self.db.refresh(folder)

        try:
            await delete_cache("drive:roots")
            logger.info(f"[Cache] drive:roots invalidé (folder {folder_id} mis à jour).")
        except Exception as e_redis:
            logger.warning(f"[Cache] Impossible d'invalider drive:roots (Redis indisponible): {e_redis}")

        return folder

    async def list_folders_with_stats(self, skip: int = 0, limit: int = 50) -> tuple[list[DriveFolder], dict, int]:
        total = (await self.db.execute(select(func.count()).select_from(DriveFolder))).scalar()
        folders = (await self.db.execute(select(DriveFolder).offset(skip).limit(limit))).scalars().all()

        stats_query = select(
            DriveSyncState.folder_id,
            DriveSyncState.status,
            func.count(DriveSyncState.google_file_id)
        ).group_by(DriveSyncState.folder_id, DriveSyncState.status)

        stats_result = (await self.db.execute(stats_query)).all()

        stats_map = {}
        for folder_id, status, count in stats_result:
            if folder_id not in stats_map:
                stats_map[folder_id] = {}
            stats_map[folder_id][status.name] = count

        return folders, stats_map, total

    async def reset_folder_sync(self, tag: str | None = None) -> int:
        stmt = update(DriveFolder).values(is_initial_sync_done=False)
        if tag:
            stmt = stmt.where(DriveFolder.tag.ilike(f"%{tag}%"))
        res = await self.db.execute(stmt)
        await self.db.commit()
        return res.rowcount

    async def delete_folder(self, folder_id: int) -> int:
        f = (await self.db.execute(select(DriveFolder).filter(DriveFolder.id == folder_id))).scalars().first()
        if not f:
            raise HTTPException(status_code=404, detail="Not Found")

        files_count_result = await self.db.execute(select(func.count()).select_from(DriveSyncState).filter(DriveSyncState.folder_id == folder_id))
        files_count = files_count_result.scalar() or 0
        if files_count > 0:
            await self.db.execute(
                DriveSyncState.__table__.delete().where(DriveSyncState.folder_id == folder_id)
            )
            logger.info(f"[delete_folder] {files_count} fichiers de sync supprimés pour le dossier {folder_id}.")

        await self.db.delete(f)
        await self.db.commit()

        try:
            await delete_cache("drive:roots")
            logger.info(f"[Cache] drive:roots invalidé (folder {folder_id} supprimé).")
        except Exception as e_redis:
            logger.warning(f"[Cache] Impossible d'invalider drive:roots (Redis indisponible): {e_redis}")

        return files_count

    @staticmethod
    async def invalidate_drive_cache() -> int:
        """Invalide le cache Drive (graphe, oos, noms) via shared.cache (async)."""
        deleted = 0
        for pattern in ["drive:graph:", "drive:oos:", "drive:name:"]:
            deleted += await clear_namespace(pattern)
        await delete_cache("drive:sync:rebuild_running")
        logger.info(f"Purge du cache Redis Drive : {deleted} clés supprimées.")
        return deleted
