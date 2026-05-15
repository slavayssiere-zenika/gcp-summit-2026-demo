"""files_router.py — Statut des fichiers, sync, retry, tokens, consultant search.
Shared imports for drive_api sub-routers."""
import logging
import os as _os
from datetime import datetime, timezone

import google.auth
from shared.database import get_db
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from shared.auth.jwt import verify_jwt
from src.google_auth import get_google_access_token
from src.models import DriveSyncState, DriveSyncStatus
from src.redis_client import get_redis
from src.schemas import (FileStateResponse, FileUpdate, PaginatedFilesResponse,
                         StatusResponse)

from src.routers.sync_router import (  # noqa: F401 — ré-export pour rétrocompatibilité
    _reset_errors_to_pending, public_router,
)

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


@router.get("/status", response_model=StatusResponse)
async def get_status(db: AsyncSession = Depends(get_db)):
    total = (await db.execute(select(func.count()).select_from(DriveSyncState))).scalar()

    pending_q = select(func.count()).select_from(select(DriveSyncState).filter(
        DriveSyncState.status == DriveSyncStatus.PENDING).subquery())
    pending = (await db.execute(pending_q)).scalar()

    proc_q = select(func.count()).select_from(select(DriveSyncState).filter(
        DriveSyncState.status == DriveSyncStatus.PROCESSING).subquery())
    proc = (await db.execute(proc_q)).scalar()

    imp_q = select(func.count()).select_from(select(DriveSyncState).filter(
        DriveSyncState.status == DriveSyncStatus.IMPORTED_CV).subquery())
    imp = (await db.execute(imp_q)).scalar()

    ign_q = select(func.count()).select_from(select(DriveSyncState).filter(
        DriveSyncState.status == DriveSyncStatus.IGNORED_NOT_CV).subquery())
    ign = (await db.execute(ign_q)).scalar()

    queued_q = select(func.count()).select_from(select(DriveSyncState).filter(
        DriveSyncState.status == DriveSyncStatus.QUEUED).subquery())
    queued = (await db.execute(queued_q)).scalar()

    err_q = select(func.count()).select_from(select(DriveSyncState).filter(
        DriveSyncState.status == DriveSyncStatus.ERROR).subquery())
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


@router.get("/files/blacklisted")
async def list_blacklisted_files(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """
    Liste paginée des fichiers Drive blacklistés pour qualité d'extraction insuffisante.
    Un fichier est blacklisté après N tentatives consécutives avec score < seuil.
    Il sera automatiquement déblaclisté si le consultant met à jour son CV sur Drive.
    """
    count_stmt = select(func.count(DriveSyncState.google_file_id)).where(
        DriveSyncState.extraction_blacklisted.is_(True)
    )
    total = (await db.execute(count_stmt)).scalar_one() or 0

    stmt = (
        select(DriveSyncState)
        .where(DriveSyncState.extraction_blacklisted.is_(True))
        .order_by(DriveSyncState.extraction_blacklisted_at.desc().nullslast())
        .offset(skip)
        .limit(limit)
    )
    files = (await db.execute(stmt)).scalars().all()
    return {
        "items": [
            {
                "google_file_id": f.google_file_id,
                "file_name": f.file_name,
                "parent_folder_name": f.parent_folder_name,
                "user_id": f.user_id,
                "extraction_attempt_count": f.extraction_attempt_count,
                "extraction_blacklisted_at": (
                    f.extraction_blacklisted_at.isoformat() if f.extraction_blacklisted_at else None
                ),
                "modified_time": f.modified_time.isoformat() if f.modified_time else None,
                "status": f.status.value if hasattr(f.status, "value") else str(f.status),
            }
            for f in files
        ],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.post("/files/{google_file_id}/blacklist-attempt")
async def record_blacklist_attempt(google_file_id: str, db: AsyncSession = Depends(get_db)):
    """
    Appelé par cv_api après une extraction avec score < EXTRACTION_RELIABILITY_THRESHOLD.
    Incrémente extraction_attempt_count. Si count >= EXTRACTION_MAX_ATTEMPTS → blacklist automatique.
    Le fichier passe en EXTRACTION_BLACKLISTED et ne sera plus re-ingéré depuis Drive
    jusqu'à ce que le consultant mette à jour son CV (revision_id change → auto-unblacklist).
    """
    max_attempts = int(_os.getenv("EXTRACTION_MAX_ATTEMPTS", "3"))
    state = (
        await db.execute(select(DriveSyncState).filter(DriveSyncState.google_file_id == google_file_id))
    ).scalars().first()
    if not state:
        raise HTTPException(status_code=404, detail=f"Fichier Drive '{google_file_id}' inconnu.")

    state.extraction_attempt_count = (state.extraction_attempt_count or 0) + 1
    now_blacklisted = state.extraction_attempt_count >= max_attempts

    if now_blacklisted and not state.extraction_blacklisted:
        state.extraction_blacklisted = True
        state.extraction_blacklisted_at = datetime.now(timezone.utc)
        state.status = DriveSyncStatus.EXTRACTION_BLACKLISTED
        logger.warning(
            "[EXTRACTION_BLACKLIST] Fichier '%s' (%s) blacklisté après %d tentatives d'extraction échouées.",
            state.file_name, google_file_id, state.extraction_attempt_count,
            extra={"google_file_id": google_file_id, "attempts": state.extraction_attempt_count},
        )

    await db.commit()
    return {
        "success": True,
        "google_file_id": google_file_id,
        "file_name": state.file_name,
        "extraction_attempt_count": state.extraction_attempt_count,
        "blacklisted": state.extraction_blacklisted,
        "max_attempts": max_attempts,
    }


@router.delete("/files/{google_file_id}/blacklist")
async def unblacklist_file(
    google_file_id: str,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(_require_admin),
):
    """
    Réinitialise manuellement le blacklist d'un fichier (admin uniquement).
    Remet status → PENDING : le fichier sera re-ingéré au prochain /sync.
    Cas d'usage : après qu'un consultant a fourni une version lisible de son CV.
    """
    state = (
        await db.execute(select(DriveSyncState).filter(DriveSyncState.google_file_id == google_file_id))
    ).scalars().first()
    if not state:
        raise HTTPException(status_code=404, detail=f"Fichier Drive '{google_file_id}' inconnu.")

    state.extraction_blacklisted = False
    state.extraction_attempt_count = 0
    state.extraction_blacklisted_at = None
    state.status = DriveSyncStatus.PENDING
    state.error_message = "Blacklist réinitialisé manuellement par un administrateur"

    try:
        get_redis().delete(f"drive:file:known:{google_file_id}")
        logger.info("[Cache] drive:file:known:%s invalidé (unblacklist admin).", google_file_id)
    except Exception as e_redis:
        logger.warning("[Cache] Impossible d'invalider drive:file:known:%s : %s", google_file_id, e_redis)

    await db.commit()
    logger.info("[EXTRACTION_UNBLACKLIST] Fichier '%s' (%s) déblaclisté manuellement.", state.file_name, google_file_id)
    return {
        "success": True,
        "google_file_id": google_file_id,
        "file_name": state.file_name,
        "status": "PENDING",
        "message": f"Fichier '{state.file_name}' déblaclisté — sera réingéré au prochain /sync.",
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
        pending_val = DriveSyncStatus.PENDING
        if update_data.status == pending_val or str(update_data.status) == pending_val.value:
            try:
                get_redis().delete(f"drive:file:known:{file_id}")
                logger.info(f"[Cache] drive:file:known:{file_id} invalidé (status → PENDING).")
            except Exception as e_redis:
                logger.warning(f"[Cache] Impossible d'invalider drive:file:known:{file_id}: {e_redis}")
    if update_data.error_message is not None:
        file_state.error_message = update_data.error_message
    if update_data.processing_duration_ms is not None:
        file_state.processing_duration_ms = update_data.processing_duration_ms

    if str(update_data.status) == DriveSyncStatus.IMPORTED_CV.value or update_data.status == DriveSyncStatus.IMPORTED_CV:  # noqa: E501
        file_state.imported_at = datetime.now(timezone.utc)

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
