import base64 as _b64
import os as _os
import json as _json
import google.auth
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from google.cloud import pubsub_v1
from google.api_core.exceptions import DeadlineExceeded
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, func
from src.schemas import FolderCreate, FolderResponse, StatusResponse, FileStateResponse, FileUpdate, FolderStats
from src.models import DriveFolder, DriveSyncState, DriveSyncStatus
from src.google_auth import get_google_access_token, get_drive_service
from database import get_db
import re
import asyncio
import traceback
from datetime import datetime, timedelta

from src.drive_service import DriveService
from src.redis_client import get_redis
from src.auth import verify_jwt
import logging

logger = logging.getLogger(__name__)

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
async def reset_folder_sync(tag: str | None = None, db: AsyncSession = Depends(get_db)):
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
async def retry_errors(force: bool = False, db: AsyncSession = Depends(get_db)):
    """
    Remet en PENDING tous les fichiers en erreur ou bloqués (QUEUED/PROCESSING zombies).
    Appelé manuellement depuis le Frontend ("Réessayer Tout") — requiert JWT.
    Paramètre `force=true` : bypass du seuil zombie (10 min) — reset immédiat de TOUS les QUEUED/PROCESSING.
    Délègue à la logique métier partagée _reset_errors_to_pending.
    """
    result = await _reset_errors_to_pending(db, force=force)
    return result



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
async def get_google_token():
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


@router.get("/dlq/status")
async def get_dlq_status(db: AsyncSession = Depends(get_db)):
    """
    Retourne le nombre et la liste des fichiers dans la DLQ Pub/Sub.
    Pull sans ACK — les messages restent dans la DLQ.
    Croise les google_file_id avec DriveSyncState pour afficher les noms.
    Les payloads illisibles sont retournes dans unknown_files avec leur message_id
    pour permettre la suppression individuelle.
    """
    try:
        sub_path = _get_dlq_subscription_path()
        subscriber = pubsub_v1.SubscriberClient()

        try:
            response = await asyncio.to_thread(
                subscriber.pull,
                request={
                    "subscription": sub_path,
                    "max_messages": 1000,
                },
                timeout=10.0
            )
            messages = response.received_messages
        except Exception as e:
            if isinstance(e, DeadlineExceeded) or "504" in str(e) or "Deadline" in str(e):
                return {
                    "subscription": sub_path.split("/")[-1],
                    "message_count": 0,
                    "files": [],
                    "unknown_files": [],
                    "unknown_payloads": 0,
                }
            raise e

        try:
            # Étendre le deadline à 600s (max Pub/Sub) pour garder les ack_ids valides
            # assez longtemps pour que l'utilisateur peut cliquer "Supprimer" sans re-pull.
            # NE PAS appeler modify_ack_deadline(0) ici — cela cause des oscillations du compteur
            # car les messages clignottent entre "in flight" et "disponibles" à chaque poll.
            if messages:
                all_ack_ids = [m.ack_id for m in messages]
                await asyncio.to_thread(
                    subscriber.modify_ack_deadline,
                    request={
                        "subscription": sub_path,
                        "ack_ids": all_ack_ids,
                        "ack_deadline_seconds": 600,  # 10min — max Pub/Sub
                    }
                )
        finally:
            subscriber.close()

        # Extraire les google_file_id + collecter les payloads inconnus
        # On conserve l'ack_id pour permettre la suppression directe (sans re-pull)
        file_ids = []
        unknown_files = []
        file_ack_map = {}  # google_file_id|msg_id -> ack_id
        for msg in messages:
            msg_id = msg.message.message_id
            ack_id = msg.ack_id
            try:
                raw = _b64.b64decode(msg.message.data).decode("utf-8")
                payload = _json.loads(raw)
                fid = payload.get("google_file_id", "")
                if fid:
                    file_ids.append(fid)
                    file_ack_map[fid] = ack_id
                else:
                    safe_payload = {
                        k: ("<token masqué>" if k in ("google_access_token", "oidc_token", "jwt") else v)
                        for k, v in payload.items()
                    }
                    unknown_files.append({
                        "message_id": msg_id,
                        "ack_id": ack_id,
                        "raw_data": safe_payload,
                        "parse_error": None,
                    })
            except Exception as e:
                raw_preview = msg.message.data[:500].decode("utf-8", errors="replace") if msg.message.data else ""
                unknown_files.append({
                    "message_id": msg_id,
                    "ack_id": ack_id,
                    "raw_data": raw_preview,
                    "parse_error": str(e),
                })

        # Enrichissement depuis la DB (noms + folder)
        files = []
        if file_ids:
            stmt = select(DriveSyncState).where(DriveSyncState.google_file_id.in_(file_ids))
            rows = (await db.execute(stmt)).scalars().all()
            db_map = {r.google_file_id: r for r in rows}

            for fid in file_ids:
                row = db_map.get(fid)
                files.append({
                    "google_file_id": fid,
                    "ack_id": file_ack_map.get(fid, ""),
                    "file_name": row.file_name if row else None,
                    "parent_folder_name": row.parent_folder_name if row else None,
                    "status": row.status.value if row and row.status else "UNKNOWN",
                    "last_processed_at": row.last_processed_at.isoformat() if row and row.last_processed_at else None,
                })

        return {
            "subscription": sub_path.split("/")[-1],
            "message_count": len(response.received_messages),
            "files": files,
            "unknown_files": unknown_files,
            "unknown_payloads": len(unknown_files),
        }
    except Exception as e:
        logger.warning(f"[DLQ] Impossible de lire le statut DLQ: {e}")
        return {"subscription": "unknown", "message_count": -1, "files": [], "unknown_files": [], "error": str(e)}


@router.delete("/dlq/message")
async def delete_dlq_message(
    google_file_id: str = "",
    pubsub_message_id: str = "",
    ack_id: str = "",
    db: AsyncSession = Depends(get_db)
):
    """
    Supprime un message spécifique de la DLQ.

    Stratégie 1 (rapide) : si ack_id est fourni, ACK direct sans re-pull.
    Stratégie 2 (fallback) : re-pull et match par google_file_id ou pubsub_message_id.
    """
    if not google_file_id and not pubsub_message_id and not ack_id:
        raise HTTPException(status_code=422, detail="ack_id, google_file_id ou pubsub_message_id requis")

    try:
        sub_path = _get_dlq_subscription_path()
        subscriber = pubsub_v1.SubscriberClient()

        # ── Mise à jour BDD (Stop Infinite Retry Loop) ──
        if google_file_id:
            try:
                stmt = (
                    update(DriveSyncState)
                    .where(DriveSyncState.google_file_id == google_file_id)
                    .values(
                        status=DriveSyncStatus.IGNORED_NOT_CV,
                        error_message="Supprimé définitivement depuis la DLQ",
                        last_processed_at=datetime.utcnow()
                    )
                )
                await db.execute(stmt)
                await db.commit()
                logger.info(f"[DLQ] Statut BDD de {google_file_id} passé à IGNORED_NOT_CV.")
            except Exception as db_e:
                logger.warning(f"[DLQ] Impossible de màj le statut bdd pour {google_file_id}: {db_e}")

        try:
            # ── Stratégie 1 : ACK direct via ack_id (pas de re-pull nécessaire) ──
            if ack_id:
                try:
                    await asyncio.to_thread(
                        subscriber.acknowledge,
                        request={"subscription": sub_path, "ack_ids": [ack_id]}
                    )
                    identifier = google_file_id or pubsub_message_id or "(ack_id direct)"
                    logger.info(f"[DLQ] Message '{identifier}' supprimé via ack_id direct.")
                    return {"status": "deleted", "method": "direct_ack", "identifier": identifier}
                except Exception as ack_err:
                    logger.warning(f"[DLQ] ACK direct échoué ({ack_err}), fallback re-pull...")
                    # ack_id expiré → fallback pull

            # ── Stratégie 2 : Re-pull et match ──
            try:
                response = await asyncio.to_thread(
                    subscriber.pull,
                    request={"subscription": sub_path, "max_messages": 1000},
                    timeout=15.0
                )
                messages = response.received_messages
            except Exception as e:
                from google.api_core.exceptions import DeadlineExceeded
                if isinstance(e, DeadlineExceeded) or "504" in str(e) or "Deadline" in str(e):
                    messages = []
                else:
                    raise e

            target_ack_id = None
            other_ack_ids = []

            for msg in messages:
                try:
                    raw = _b64.b64decode(msg.message.data).decode("utf-8")
                    payload = _json.loads(raw)
                    fid = payload.get("google_file_id", "")
                except Exception:
                    fid = ""

                is_target = (
                    (google_file_id and fid == google_file_id) or
                    (pubsub_message_id and msg.message.message_id == pubsub_message_id)
                )
                if is_target:
                    target_ack_id = msg.ack_id
                else:
                    other_ack_ids.append(msg.ack_id)

            if not target_ack_id:
                if other_ack_ids:
                    await asyncio.to_thread(
                        subscriber.modify_ack_deadline,
                        request={"subscription": sub_path, "ack_ids": other_ack_ids, "ack_deadline_seconds": 0}
                    )
                identifier = google_file_id or pubsub_message_id
                raise HTTPException(
                    status_code=404,
                    detail=f"Message '{identifier}' introuvable dans la DLQ"
                )

            await asyncio.to_thread(
                subscriber.acknowledge,
                request={"subscription": sub_path, "ack_ids": [target_ack_id]}
            )
            if other_ack_ids:
                await asyncio.to_thread(
                    subscriber.modify_ack_deadline,
                    request={"subscription": sub_path, "ack_ids": other_ack_ids, "ack_deadline_seconds": 0}
                )
            
            return {"status": "deleted", "method": "repull", "remaining_in_dlq": len(other_ack_ids)}
        finally:
            subscriber.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[DLQ] Erreur suppression: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur suppression DLQ: {e}")


@router.post("/dlq/replay")
async def replay_dlq(db: AsyncSession = Depends(get_db)):
    """
    Rejoue les messages de la DLQ :
    1. Pull tous les messages de la DLQ subscription
    2. Extrait les google_file_id des payloads
    3. Les remet en PENDING dans la DB (+ reset last_processed_at)
    4. ACK les messages (les supprime de la DLQ)
    5. Le frontend doit ensuite appeler POST /sync pour republier

    Idempotent : si un google_file_id n'existe pas en DB, il est ignoré.
    """
    try:
        sub_path = _get_dlq_subscription_path()
        subscriber = pubsub_v1.SubscriberClient()

        all_ack_ids = []
        all_file_ids = []
        unknown_file_ids = []

        # Pull par batch de 1000 jusqu'à épuisement
        try:
            while True:
                try:
                    response = await asyncio.to_thread(
                        subscriber.pull,
                        request={
                            "subscription": sub_path,
                            "max_messages": 1000,
                        },
                        timeout=15.0
                    )
                    messages = response.received_messages
                except Exception as e:
                    from google.api_core.exceptions import DeadlineExceeded
                    if isinstance(e, DeadlineExceeded) or "504" in str(e) or "Deadline" in str(e):
                        messages = []
                    else:
                        raise e

                if not messages:
                    break

                for msg in messages:
                    all_ack_ids.append(msg.ack_id)
                    try:
                        raw = _b64.b64decode(msg.message.data).decode("utf-8")
                        payload = _json.loads(raw)
                        file_id = payload.get("google_file_id", "")
                        if file_id:
                            all_file_ids.append(file_id)
                        else:
                            # Payload JSON valide mais sans google_file_id — masquer les tokens
                            _SENSITIVE_KEYS = {"google_access_token", "oidc_token", "jwt", "access_token"}
                            safe_payload = {
                                k: ("<redacted>" if k in _SENSITIVE_KEYS else v)
                                for k, v in payload.items()
                            }
                            logger.warning(
                                f"[DLQ] Payload sans google_file_id {msg.message.message_id}: "
                                f"clés={list(safe_payload.keys())}"
                            )
                            unknown_file_ids.append(msg.message.message_id)
                    except Exception as parse_err:
                        # Payload illisible — loguer le début du data brut pour diagnostic
                        raw_preview = str(msg.message.data)[:200] if msg.message.data else "(vide)"
                        logger.warning(
                            f"[DLQ] Payload illisible {msg.message.message_id} ({parse_err}): "
                            f"data_preview={raw_preview}"
                        )
                        unknown_file_ids.append(msg.message.message_id)


                if len(messages) < 1000:
                    break
        except Exception as pull_err:
            logger.error(f"Error pulling from DLQ: {pull_err}")
            # on continue avec ce qu'on a déjà pullé

        logger.info(f"[DLQ] {len(all_ack_ids)} messages pullés, {len(all_file_ids)} file_ids extraits.")

        # Reset PENDING pour tous les file_ids trouvés
        reset_count = 0
        if all_file_ids:
            stmt = (
                update(DriveSyncState)
                .where(DriveSyncState.google_file_id.in_(all_file_ids))
                .values(
                    status=DriveSyncStatus.PENDING,
                    error_message="Rejoué depuis DLQ",
                    last_processed_at=datetime.utcnow()
                )
                .returning(DriveSyncState.google_file_id)
            )
            result = await db.execute(stmt)
            reset_ids = [r[0] for r in result.fetchall()]
            reset_count = len(reset_ids)
            await db.commit()
            logger.info(f"[DLQ] {reset_count} fichiers remis en PENDING.")

        # ACK tous les messages (même ceux sans file_id valide — ils ne peuvent pas être rejoués)
        if all_ack_ids:
            try:
                # Pub/Sub allow max 1000 acks per request
                BATCH_SIZE = 1000
                for i in range(0, len(all_ack_ids), BATCH_SIZE):
                    await asyncio.to_thread(
                        subscriber.acknowledge,
                        request={"subscription": sub_path, "ack_ids": all_ack_ids[i:i + BATCH_SIZE]}
                    )
                logger.info(f"[DLQ] {len(all_ack_ids)} messages ACKés et supprimés de la DLQ.")
            finally:
                subscriber.close()
        else:
            subscriber.close()

        return {
            "status": "success",
            "dlq_messages_pulled": len(all_ack_ids),
            "files_reset_to_pending": reset_count,
            "unknown_payloads": len(unknown_file_ids),
            "message": f"{reset_count} CV(s) remis en PENDING — appelez /sync pour les republier en Pub/Sub"
        }

    except Exception as e:
        logger.error(f"[DLQ] Erreur lors du replay: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur DLQ replay: {e}")


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
        
    await db.commit()
    await db.refresh(file_state)
    return file_state
