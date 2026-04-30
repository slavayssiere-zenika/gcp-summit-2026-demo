"""folders_router.py — Gestion des dossiers Google Drive cibles."""
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

router = APIRouter(prefix="", tags=["Drive Folders"], dependencies=[Depends(verify_jwt)])

@router.post("/folders", response_model=FolderResponse)
async def add_folder(folder: FolderCreate, db: AsyncSession = Depends(get_db), _: dict = Depends(_require_admin)):
    raw_id = folder.google_folder_id.strip()
    match = re.search(r"folders/([a-zA-Z0-9_-]+)", raw_id)
    if match:
        raw_id = match.group(1)

    existing = (await db.execute(select(DriveFolder).filter(DriveFolder.google_folder_id == raw_id))).scalars().first()
    if existing:
        raise HTTPException(status_code=400, detail="Folder ID already registered.")

    existing_tag = (await db.execute(select(DriveFolder).filter(DriveFolder.tag == folder.tag.strip()))).scalars().first()
    if existing_tag:
        raise HTTPException(
            status_code=409,
            detail=f"Tag '{folder.tag.strip()}' already used by folder '{existing_tag.folder_name or existing_tag.google_folder_id}'. Tags must be unique."
        )

    # Récupération automatique du nom du dossier Drive (nomenclature Zenika "Prénom Nom")
    resolved_folder_name = folder.folder_name  # Fallback sur la valeur manuelle si fournie
    try:
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

    db_f = DriveFolder(google_folder_id=raw_id, tag=folder.tag.strip(), folder_name=resolved_folder_name, excluded_folders=folder.excluded_folders)
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


@router.patch("/folders/{folder_id}", response_model=FolderResponse)
async def update_folder(folder_id: int, folder_update: FolderUpdate, db: AsyncSession = Depends(get_db), _: dict = Depends(_require_admin)):
    folder = (await db.execute(select(DriveFolder).filter(DriveFolder.id == folder_id))).scalars().first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    if folder_update.tag is not None:
        new_tag = folder_update.tag.strip()
        existing_tag = (await db.execute(select(DriveFolder).filter(DriveFolder.tag == new_tag, DriveFolder.id != folder_id))).scalars().first()
        if existing_tag:
            raise HTTPException(
                status_code=409,
                detail=f"Tag '{new_tag}' already used by folder '{existing_tag.folder_name or existing_tag.google_folder_id}'. Tags must be unique."
            )
        folder.tag = new_tag

    if folder_update.excluded_folders is not None:
        folder.excluded_folders = folder_update.excluded_folders

    await db.commit()
    await db.refresh(folder)

    try:
        get_redis().delete("drive:roots")
        logger.info(f"[Cache] drive:roots invalidé (folder {folder_id} mis à jour).")
    except Exception as e_redis:
        logger.warning(f"[Cache] Impossible d'invalider drive:roots (Redis indisponible): {e_redis}")

    # Injecting stats as None to respect FolderResponse
    f_response = FolderResponse.model_validate(folder)
    return f_response


@router.get("/folders", response_model=list[FolderResponse])
async def list_folders(db: AsyncSession = Depends(get_db)):
    folders = (await db.execute(select(DriveFolder))).scalars().all()
    
    
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
async def reset_folder_sync(tag: str | None = None, db: AsyncSession = Depends(get_db), _: dict = Depends(_require_admin)):
    stmt = update(DriveFolder).values(is_initial_sync_done=False)
    if tag:
        stmt = stmt.where(DriveFolder.tag.ilike(f"%{tag}%"))
    res = await db.execute(stmt)
    await db.commit()
    return {"status": "success", "rows_updated": res.rowcount}


@router.post("/folders/rebuild-tree")
async def rebuild_folder_tree(background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db), _: dict = Depends(_require_admin)):
    """
    Force un scan complet de l'arbre Drive pour réparer les structures parent_folder_name manquantes,
    SANS repasser les statuts en PENDING pour les fichiers déjà importés et non modifiés.
    """
    async def run_rebuild():
        from src.drive_service import DriveService
        from database import SessionLocal
        redis = get_redis()
        try:
            redis.set("drive:sync:rebuild_running", "1", ex=1800) # 30 min max
            async with SessionLocal() as session:
                service = DriveService(session)
                await service.discover_files(force_full=True)
        finally:
            redis.delete("drive:sync:rebuild_running")
            
    background_tasks.add_task(run_rebuild)
    return {"status": "success", "message": "Reconstruction de l'arbre lancée en arrière-plan"}


@router.post("/folders/invalidate-cache")
async def invalidate_drive_cache(_: dict = Depends(_require_admin)):
    redis = get_redis()
    keys_to_delete = []
    for pattern in ["drive:graph:*", "drive:oos:*", "drive:name:*"]:
        for key in redis.scan_iter(pattern):
            keys_to_delete.append(key)
            
    # Supprimer aussi le verrou de reconstruction s'il est bloqué
    redis.delete("drive:sync:rebuild_running")
    
    if keys_to_delete:
        redis.delete(*keys_to_delete)
        logger.info(f"Purge du cache Redis Drive : {len(keys_to_delete)} cles supprimees.")
    return {"status": "success", "keys_deleted": len(keys_to_delete)}


@router.delete("/folders/{folder_id}")
async def delete_folder(folder_id: int, db: AsyncSession = Depends(get_db), _: dict = Depends(_require_admin)):
    f = (await db.execute(select(DriveFolder).filter(DriveFolder.id == folder_id))).scalars().first()
    if not f:
        raise HTTPException(status_code=404, detail="Not Found")

    # Cascade manuel : supprime les fichiers trackés avant le dossier
    # (la FK fk_drive_sync_folder n'a pas ON DELETE CASCADE en base)
    files_count_result = await db.execute(select(func.count()).select_from(DriveSyncState).filter(DriveSyncState.folder_id == folder_id))
    files_count = files_count_result.scalar() or 0
    if files_count > 0:
        await db.execute(
            DriveSyncState.__table__.delete().where(DriveSyncState.folder_id == folder_id)
        )
        logger.info(f"[delete_folder] {files_count} fichiers de sync supprimés pour le dossier {folder_id}.")

    await db.delete(f)
    await db.commit()
    # Invalider le cache drive:roots
    try:
        get_redis().delete("drive:roots")
        logger.info(f"[Cache] drive:roots invalidé (folder {folder_id} supprimé).")
    except Exception as e_redis:
        logger.warning(f"[Cache] Impossible d'invalider drive:roots (Redis indisponible): {e_redis}")
    return {"status": "deleted", "files_removed": files_count}

