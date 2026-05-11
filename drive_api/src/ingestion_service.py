import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone

from google.cloud import pubsub_v1
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.google_auth import get_google_access_token, get_google_oidc_id_token, get_m2m_jwt_token
from src.models import DriveFolder, DriveSyncState, DriveSyncStatus

logger = logging.getLogger(__name__)

MAX_DRIVE_CV_IMPORT = int(os.getenv("MAX_DRIVE_CV_IMPORT", "15"))
PUBSUB_CV_IMPORT_TOPIC = os.getenv("PUBSUB_CV_IMPORT_TOPIC", "")
_GCP_PROJECT_ID_ENV = os.getenv("GCP_PROJECT_ID", "")


def _resolve_gcp_project_id() -> str:
    env_val = _GCP_PROJECT_ID_ENV.strip()
    if env_val and env_val not in ("your-gcp-project-id", "YOUR_GCP_PROJECT_ID", ""):
        return env_val

    try:
        import google.auth as _google_auth
        _, project_id = _google_auth.default()
        if project_id:
            logger.info(f"[PubSub] GCP project ID résolu via ADC : '{project_id}'")
            return project_id
    except Exception as e:
        logger.warning(f"[PubSub] Impossible de résoudre le project ID via google.auth.default(): {e}")

    logger.error("[PubSub] GCP project ID introuvable — publication Pub/Sub impossible.")
    return ""


class IngestionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def ingest_batch(self) -> int:
        zombie_threshold = datetime.now(timezone.utc) - timedelta(minutes=15)
        zombie_stmt = (
            update(DriveSyncState)
            .where(DriveSyncState.status.in_([DriveSyncStatus.PROCESSING, DriveSyncStatus.QUEUED]))
            .where(DriveSyncState.last_processed_at < zombie_threshold)
            .values(
                status=DriveSyncStatus.PENDING,
                error_message="Réinitialisé automatiquement (Interruption processus)"
            )
        )
        await self.db.execute(zombie_stmt)
        await self.db.commit()

        base_query = (
            select(DriveSyncState)
            .filter(DriveSyncState.status.in_([DriveSyncStatus.PENDING.value, DriveSyncStatus.OUT_OF_SCOPE.value]))
            .order_by(DriveSyncState.modified_time.asc())
            .limit(MAX_DRIVE_CV_IMPORT)
        )
        pending_files = (await self.db.execute(base_query)).scalars().all()

        if not pending_files:
            return 0

        oidc_token = get_google_oidc_id_token()
        m2m_jwt = await get_m2m_jwt_token() if not oidc_token else ""
        google_access_token = await asyncio.to_thread(get_google_access_token)
        pubsub_topic = PUBSUB_CV_IMPORT_TOPIC
        gcp_project_id = _resolve_gcp_project_id()

        payloads_to_publish = []
        for state in pending_files:
            folder = (
                await self.db.execute(
                    select(DriveFolder).filter(DriveFolder.id == state.folder_id)
                )
            ).scalars().first()
            if not folder:
                state.status = DriveSyncStatus.ERROR
                state.error_message = f"Dossier racine introuvable (folder_id={state.folder_id})"
                continue

            ft = state.file_type or "google_doc"

            # Fix: If the database has "google_doc" but the filename clearly indicates a DOCX, override it.
            if state.file_name and state.file_name.lower().endswith(".docx"):
                ft = "docx"

            if ft == "docx":
                doc_url = f"https://drive.google.com/file/d/{state.google_file_id}"
            else:
                doc_url = f"https://docs.google.com/document/d/{state.google_file_id}"

            action = "delete" if state.status == DriveSyncStatus.OUT_OF_SCOPE.value else "upsert"

            payloads_to_publish.append({
                "state": state,
                "message": {
                    "google_file_id": state.google_file_id,
                    "url": doc_url,
                    "source_tag": folder.tag,
                    "folder_name": state.parent_folder_name or folder.folder_name or "",
                    "google_access_token": google_access_token,
                    "file_type": ft,
                    "oidc_token": oidc_token,
                    "jwt": m2m_jwt,
                    "action": action,
                }
            })
            state.status = DriveSyncStatus.QUEUED
            state.last_processed_at = datetime.now(timezone.utc)
            state.queued_at = datetime.now(timezone.utc)
            logger.info(
                f"[PubSub] Enqueue CV — fichier='{state.file_name}', "
                f"folder='{state.parent_folder_name}', tag={folder.tag}"
            )

        await self.db.commit()

        if not payloads_to_publish:
            return 0

        published_count = 0
        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path(gcp_project_id, pubsub_topic) if gcp_project_id and pubsub_topic else None

        if not topic_path:
            logger.error("[PubSub] PUBSUB_CV_IMPORT_TOPIC ou GCP_PROJECT_ID non résolu (env + ADC) — fallback PENDING.")
            for item in payloads_to_publish:
                item["state"].status = DriveSyncStatus.PENDING
            await self.db.commit()
            return 0

        for item in payloads_to_publish:
            try:
                data = json.dumps(item["message"]).encode("utf-8")
                future = await asyncio.to_thread(publisher.publish, topic_path, data)
                message_id = await asyncio.to_thread(future.result, timeout=10)
                logger.info(f"[PubSub] Message publié — file_id={item['state'].google_file_id}, msg_id={message_id}")
                published_count += 1
            except Exception as e:
                logger.error(f"[PubSub] Échec publication pour {item['state'].google_file_id}: {e}")
                item["state"].status = DriveSyncStatus.ERROR
                item["state"].error_message = f"Échec publication Pub/Sub: {e}"

        await self.db.commit()
        logger.info(f"[PubSub] Batch terminé — {published_count}/{len(payloads_to_publish)} messages publiés.")
        return len(pending_files)
