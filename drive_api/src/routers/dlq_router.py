"""dlq_router.py — Dead Letter Queue management (Pub/Sub)."""
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
from src.routers.files_router import _get_dlq_subscription_path

logger = logging.getLogger(__name__)


def _require_admin(token_payload: dict = Depends(verify_jwt)) -> dict:
    """Guard : vérifie que l'appelant est administrateur."""
    if token_payload.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail="Privilèges administrateur requis pour cette opération Drive."
        )
    return token_payload

router = APIRouter(prefix="", tags=["Drive DLQ"], dependencies=[Depends(verify_jwt)])

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
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(_require_admin)
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
async def replay_dlq(db: AsyncSession = Depends(get_db), _: dict = Depends(_require_admin)):
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


