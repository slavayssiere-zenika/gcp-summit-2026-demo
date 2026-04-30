"""ingestion_router.py — Ingestion KPIs, quality gate, batch-retry, history."""
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

router = APIRouter(prefix="", tags=["Drive Ingestion"], dependencies=[Depends(verify_jwt)])

@router.get("/ingestion/stats")
async def get_ingestion_stats(db: AsyncSession = Depends(get_db)):
    """
    Retourne les KPIs de data quality pour le pipeline d'ingestion Drive → CV.
    Utilisé par AdminDriveIngestion pour afficher le grade global et les métriques.
    """
    from sqlalchemy import and_, or_

    total = (await db.execute(select(func.count()).select_from(DriveSyncState))).scalar() or 0
    imported = (await db.execute(
        select(func.count()).select_from(DriveSyncState).where(DriveSyncState.status == DriveSyncStatus.IMPORTED_CV)
    )).scalar() or 0
    errors = (await db.execute(
        select(func.count()).select_from(DriveSyncState).where(DriveSyncState.status == DriveSyncStatus.ERROR)
    )).scalar() or 0
    pending = (await db.execute(
        select(func.count()).select_from(DriveSyncState).where(DriveSyncState.status == DriveSyncStatus.PENDING)
    )).scalar() or 0
    queued = (await db.execute(
        select(func.count()).select_from(DriveSyncState).where(DriveSyncState.status == DriveSyncStatus.QUEUED)
    )).scalar() or 0
    processing = (await db.execute(
        select(func.count()).select_from(DriveSyncState).where(DriveSyncState.status == DriveSyncStatus.PROCESSING)
    )).scalar() or 0
    ignored = (await db.execute(
        select(func.count()).select_from(DriveSyncState).where(DriveSyncState.status == DriveSyncStatus.IGNORED_NOT_CV)
    )).scalar() or 0

    kpi_import_rate = _compute_kpi_metric(imported, total, 90.0, 75.0)
    kpi_error_rate = _compute_kpi_metric(imported, imported + errors, 95.0, 85.0)

    named = (await db.execute(
        select(func.count()).select_from(DriveSyncState).where(
            and_(
                DriveSyncState.status == DriveSyncStatus.IMPORTED_CV,
                DriveSyncState.parent_folder_name.isnot(None),
                DriveSyncState.parent_folder_name != ""
            )
        )
    )).scalar() or 0
    kpi_naming = _compute_kpi_metric(named, imported, 95.0, 80.0)

    linked = (await db.execute(
        select(func.count()).select_from(DriveSyncState).where(
            and_(
                DriveSyncState.status == DriveSyncStatus.IMPORTED_CV,
                DriveSyncState.user_id.isnot(None)
            )
        )
    )).scalar() or 0
    kpi_user_link = _compute_kpi_metric(linked, imported, 95.0, 80.0)

    avg_ms_result = (await db.execute(
        select(func.avg(DriveSyncState.processing_duration_ms)).where(
            and_(
                DriveSyncState.status == DriveSyncStatus.IMPORTED_CV,
                DriveSyncState.processing_duration_ms.isnot(None)
            )
        )
    )).scalar()
    avg_ms = round(float(avg_ms_result), 0) if avg_ms_result else None
    duration_status = "ok"
    if avg_ms is not None:
        if avg_ms > 60000:
            duration_status = "critical"
        elif avg_ms > 30000:
            duration_status = "warning"
    kpi_duration = {
        "value": round(avg_ms / 1000, 1) if avg_ms else 0.0,
        "pct": min(100, round((avg_ms or 0) / 60000 * 100, 1)),
        "ok": int(avg_ms / 1000) if avg_ms else 0,
        "total": 60,
        "status": duration_status,
        "unit": "s"
    }

    last_imported_at = (await db.execute(
        select(func.max(DriveSyncState.imported_at)).where(DriveSyncState.imported_at.isnot(None))
    )).scalar()
    last_processed = (await db.execute(
        select(func.max(DriveSyncState.last_processed_at))
    )).scalar()
    freshness_hours = None
    freshness_status = "ok"
    reference_time = last_imported_at or last_processed
    if reference_time:
        diff_hours = (datetime.utcnow() - reference_time).total_seconds() / 3600
        freshness_hours = round(diff_hours, 1)
        if diff_hours > 48:
            freshness_status = "critical"
        elif diff_hours > 24:
            freshness_status = "warning"

    scores = [
        kpi_import_rate["pct"] * 0.25,
        kpi_user_link["pct"] * 0.30,
        kpi_naming["pct"] * 0.15,
        kpi_error_rate["pct"] * 0.15,
        (100 if freshness_status == "ok" else 50 if freshness_status == "warning" else 0) * 0.15,
    ]
    score = round(sum(scores), 1)
    grade = "A" if score >= 90 else "B" if score >= 75 else "C" if score >= 60 else "D" if score >= 40 else "F"

    issues = []
    if kpi_import_rate["status"] != "ok":
        issues.append(f"Taux d'import {kpi_import_rate['status']} : {kpi_import_rate['pct']}%")
    if kpi_user_link["status"] != "ok":
        issues.append(f"Liaison consultant {kpi_user_link['status']} : {kpi_user_link['pct']}%")
    if kpi_naming["status"] != "ok":
        issues.append(f"Nommage non résolu : {kpi_naming['pct']}%")
    if freshness_status != "ok":
        issues.append(f"Pipeline inactif depuis {freshness_hours}h")
    if errors > 0 and total > 0 and (errors / total) > 0.1:
        issues.append(f"{errors} fichiers en erreur ({round(errors/total*100,1)}%) — lancez un Quality Gate Batch")

    recommendation = (
        "\u2705 Pipeline en bonne santé." if not issues
        else "\u26a0\ufe0f Lancez un Quality Gate Batch pour corriger les données incomplètes."
    )

    redis = get_redis()
    is_rebuilding_tree = bool(redis.get("drive:sync:rebuild_running"))

    return {
        "total_files": total, "imported": imported, "errors": errors,
        "pending": pending, "queued": queued, "processing": processing, "ignored": ignored,
        "freshness_hours": freshness_hours,
        "is_rebuilding_tree": is_rebuilding_tree,
        "metrics": {
            "Taux d'import réussi": kpi_import_rate,
            "Taux sans erreur": kpi_error_rate,
            "Nommage résolu": kpi_naming,
            "Liaison consultant": kpi_user_link,
            "Durée de traitement": kpi_duration,
        },
        "score": score, "grade": grade,
        "computed_at": datetime.utcnow().isoformat(),
        "issues": issues, "recommendation": recommendation,
    }



@router.get("/ingestion/folder-kpis")
async def get_folder_kpis(db: AsyncSession = Depends(get_db)):
    """
    Retourne les KPIs d'ingestion par folder/agence.
    Utilisé par AdminDriveIngestion pour le tableau par agence.
    """
    from sqlalchemy import and_, or_

    folders = (await db.execute(select(DriveFolder))).scalars().all()
    result = []

    for folder in folders:
        fid = folder.id
        fid_filter = DriveSyncState.folder_id == fid

        total = (await db.execute(
            select(func.count()).select_from(DriveSyncState).where(fid_filter)
        )).scalar() or 0
        imported = (await db.execute(
            select(func.count()).select_from(DriveSyncState).where(
                fid_filter, DriveSyncState.status == DriveSyncStatus.IMPORTED_CV)
        )).scalar() or 0
        errors = (await db.execute(
            select(func.count()).select_from(DriveSyncState).where(
                fid_filter, DriveSyncState.status == DriveSyncStatus.ERROR)
        )).scalar() or 0
        pending = (await db.execute(
            select(func.count()).select_from(DriveSyncState).where(
                fid_filter, DriveSyncState.status == DriveSyncStatus.PENDING)
        )).scalar() or 0
        queued = (await db.execute(
            select(func.count()).select_from(DriveSyncState).where(
                fid_filter, DriveSyncState.status == DriveSyncStatus.QUEUED)
        )).scalar() or 0
        processing = (await db.execute(
            select(func.count()).select_from(DriveSyncState).where(
                fid_filter, DriveSyncState.status == DriveSyncStatus.PROCESSING)
        )).scalar() or 0
        ignored = (await db.execute(
            select(func.count()).select_from(DriveSyncState).where(
                fid_filter, DriveSyncState.status == DriveSyncStatus.IGNORED_NOT_CV)
        )).scalar() or 0

        linked = (await db.execute(
            select(func.count()).select_from(DriveSyncState).where(
                fid_filter,
                DriveSyncState.status == DriveSyncStatus.IMPORTED_CV,
                DriveSyncState.user_id.isnot(None))
        )).scalar() or 0

        avg_ms_row = (await db.execute(
            select(func.avg(DriveSyncState.processing_duration_ms)).where(
                fid_filter, DriveSyncState.processing_duration_ms.isnot(None))
        )).scalar()

        last_import_row = (await db.execute(
            select(func.max(DriveSyncState.imported_at)).where(
                fid_filter, DriveSyncState.imported_at.isnot(None))
        )).scalar()

        import_rate = round((imported / total * 100), 1) if total > 0 else 0.0
        error_rate = round((errors / total * 100), 1) if total > 0 else 0.0
        user_link_rate = round((linked / imported * 100), 1) if imported > 0 else 0.0

        if error_rate > 15 or (imported > 0 and user_link_rate < 80):
            folder_status = "critical"
        elif error_rate > 5 or (imported > 0 and user_link_rate < 90) or import_rate < 90:
            folder_status = "warning"
        else:
            folder_status = "ok"

        result.append({
            "folder_id": fid, "folder_name": folder.folder_name, "tag": folder.tag,
            "total": total, "imported": imported, "errors": errors,
            "pending": pending, "queued": queued, "processing": processing, "ignored": ignored,
            "import_rate_pct": import_rate, "error_rate_pct": error_rate,
            "user_link_rate_pct": user_link_rate,
            "avg_processing_ms": round(float(avg_ms_row), 0) if avg_ms_row else None,
            "last_import_at": last_import_row.isoformat() if last_import_row else None,
            "status": folder_status,
        })

    priority = {"critical": 0, "warning": 1, "ok": 2}
    result.sort(key=lambda x: (priority.get(x["status"], 3), -x["error_rate_pct"]))
    return result



@router.get("/ingestion/history")
async def get_ingestion_history(limit: int = 50, db: AsyncSession = Depends(get_db)):
    """Retourne les dernières ingestions réussies avec horodatages."""
    limit = min(limit, 200)
    stmt = (
        select(DriveSyncState)
        .where(DriveSyncState.status == DriveSyncStatus.IMPORTED_CV)
        .order_by(DriveSyncState.imported_at.desc().nullslast(), DriveSyncState.last_processed_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "google_file_id": r.google_file_id, "file_name": r.file_name,
            "parent_folder_name": r.parent_folder_name, "user_id": r.user_id,
            "queued_at": r.queued_at.isoformat() if r.queued_at else None,
            "imported_at": r.imported_at.isoformat() if r.imported_at else None,
            "processing_duration_ms": r.processing_duration_ms,
        }
        for r in rows
    ]



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
    result = await _reset_errors_to_pending(db, force=force)

    async def run_sync_after_retry():
        from database import SessionLocal
        async with SessionLocal() as session:
            try:
                service = DriveService(session)
                processed = await service.ingest_batch()
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

    Cas traités :
    1. IMPORTED_CV sans user_id (liaison consultant non résolue)
    2. IMPORTED_CV sans parent_folder_name (nommage absent — RAG incomplet)
    3. ERROR persistants > 30 min
    """
    from sqlalchemy import and_, or_

    now = datetime.utcnow()
    reason_breakdown: dict[str, int] = {}
    all_fixed_ids: list[str] = []

    stmt_no_user = (
        update(DriveSyncState)
        .where(and_(DriveSyncState.status == DriveSyncStatus.IMPORTED_CV, DriveSyncState.user_id.is_(None)))
        .values(status=DriveSyncStatus.PENDING, error_message="Quality Gate: user_id manquant", last_processed_at=now)
        .returning(DriveSyncState.google_file_id)
    )
    ids_no_user = [r[0] for r in (await db.execute(stmt_no_user)).fetchall()]
    reason_breakdown["user_id_manquant"] = len(ids_no_user)
    all_fixed_ids.extend(ids_no_user)

    stmt_no_name = (
        update(DriveSyncState)
        .where(and_(
            DriveSyncState.status == DriveSyncStatus.IMPORTED_CV,
            or_(DriveSyncState.parent_folder_name.is_(None), DriveSyncState.parent_folder_name == ""),
            DriveSyncState.google_file_id.notin_(ids_no_user)
        ))
        .values(status=DriveSyncStatus.PENDING, error_message="Quality Gate: nommage manquant", last_processed_at=now)
        .returning(DriveSyncState.google_file_id)
    )
    ids_no_name = [r[0] for r in (await db.execute(stmt_no_name)).fetchall()]
    reason_breakdown["nommage_manquant"] = len(ids_no_name)
    all_fixed_ids.extend(ids_no_name)

    error_threshold = now - timedelta(minutes=30)
    stmt_errors = (
        update(DriveSyncState)
        .where(and_(DriveSyncState.status == DriveSyncStatus.ERROR, DriveSyncState.last_processed_at < error_threshold))
        .values(status=DriveSyncStatus.PENDING, error_message="Quality Gate: erreur persistante", last_processed_at=now)
        .returning(DriveSyncState.google_file_id)
    )
    ids_errors = [r[0] for r in (await db.execute(stmt_errors)).fetchall()]
    reason_breakdown["erreur_persistante"] = len(ids_errors)
    all_fixed_ids.extend(ids_errors)

    await db.commit()

    if all_fixed_ids:
        try:
            redis = get_redis()
            pipe = redis.pipeline()
            for fid in all_fixed_ids:
                pipe.delete(f"drive:file:known:{fid}")
            pipe.execute()
        except Exception as e_redis:
            logger.warning(f"[QualityGate] Redis cache invalidation partielle : {e_redis}")

    total_queued = sum(reason_breakdown.values())
    logger.info(f"[QualityGate] {total_queued} fichiers remis en PENDING — {reason_breakdown}")

    async def run_sync_after_gate():
        from database import SessionLocal
        async with SessionLocal() as session:
            try:
                service = DriveService(session)
                processed = await service.ingest_batch()
                logger.info(f"[QualityGate] {processed} fichier(s) republié(s) dans Pub/Sub.")
            except Exception as e:
                logger.error(f"[QualityGate] Erreur sync post-gate : {e}")

    if total_queued > 0:
        background_tasks.add_task(run_sync_after_gate)

    return {
        "status": "success",
        "files_queued_for_retry": total_queued,
        "reason_breakdown": reason_breakdown,
        "sync_triggered": total_queued > 0,
        "message": (
            f"{total_queued} CV(s) avec données incomplètes republiés dans Pub/Sub."
            if total_queued > 0
            else "Aucun CV incomplet détecté — data quality satisfaisante."
        ),
    }

