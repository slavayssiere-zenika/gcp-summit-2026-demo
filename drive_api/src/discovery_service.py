import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, literal, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from shared.cache import delete_cache, get_cache, set_cache
from src.models import DriveFolder, DriveSyncState, DriveSyncStatus
from src.services.google_api_client import DriveApiClient
from src.services.tree_resolution import TreeResolver
import asyncio as _asyncio

logger = logging.getLogger(__name__)

REDIS_TTL_KNOWN_FILE = 86400

_SUPPORTED_CV_MIME_TYPES: dict[str, str] = {
    "application/vnd.google-apps.document": "google_doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}


class DiscoveryService:
    def __init__(self, db: AsyncSession, drive):
        """DiscoveryService ne prend plus de redis en paramètre (partagé via shared.cache)."""
        self.db = db
        self.drive_api = DriveApiClient(drive)
        self.tree_resolver = TreeResolver(db, self.drive_api)

    def invalidate_roots_cache(self) -> None:
        self.tree_resolver.invalidate_roots_cache()

    async def _is_file_known(self, file_id: str) -> bool:
        return bool(await get_cache(f"drive:file:known:{file_id}"))

    async def _mark_file_known(self, file_id: str) -> None:
        await set_cache(f"drive:file:known:{file_id}", "IMPORTED_CV", REDIS_TTL_KNOWN_FILE)

    async def discover_files(self, force_full: bool = False) -> int:
        roots = await self.tree_resolver.load_roots()
        if not roots:
            logger.warning("[discover_files] Aucun folder racine configuré — sync interrompue.")
            return 0

        await self.db.commit()
        total_discovered = 0

        if force_full:
            logger.info(f"Démarrage sync FULL Top-Down pour {len(roots)} racines.")
            total_discovered += await self._discover_full_top_down(roots)
        else:
            uninitialized_folders = (
                await self.db.execute(
                    select(DriveFolder).filter(not DriveFolder.is_initial_sync_done)
                )
            ).scalars().all()

            uninit_ids = {f.id for f in uninitialized_folders}
            target_roots = [r for r in roots if r["id"] in uninit_ids]

            if target_roots:
                logger.info(f"Démarrage sync Top-Down pour {len(target_roots)} NOUVELLES racines.")
                total_discovered += await self._discover_full_top_down(target_roots)

                for root_dict in target_roots:
                    await self.db.execute(
                        update(DriveFolder)
                        .where(DriveFolder.id == root_dict["id"])
                        .values(is_initial_sync_done=True)
                    )
                await self.db.commit()

            logger.info("Démarrage sync Bottom-Up Delta pour les autres fichiers.")
            total_discovered += await self._discover_delta_bottom_up(roots)

        logger.info(f"Discovery terminé. {total_discovered} fichiers découverts au total.")
        return total_discovered

    async def _discover_full_top_down(self, roots: list[dict]) -> int:
        new_discoveries = 0
        queue = []

        for root in roots:
            queue.append({
                "folder_id": root["google_folder_id"],
                "parent_name": root["tag"],
                "root": root
            })

        while queue:
            current = queue.pop(0)
            folder_id = current["folder_id"]
            parent_name = current["parent_name"]
            root = current["root"]

            q = f"'{folder_id}' in parents and trashed=false"
            page_token = None

            logger.info(f"[Top-Down] Traitement du dossier '{parent_name}' ({folder_id})")

            while True:
                results = await self.drive_api.list_files(
                    q=q,
                    page_token=page_token,
                    fields="nextPageToken, files(id, name, mimeType, modifiedTime, version)"
                )

                if not results:
                    break

                files = results.get("files", [])
                cvs_in_page = 0
                subfolders_in_page = 0

                for file in files:
                    file_id = file.get("id")
                    name = file.get("name", "Unknown")
                    mime = file.get("mimeType", "")
                    mod_time_str = file.get("modifiedTime")
                    version = str(file.get("version", "1"))

                    if mime == "application/vnd.google-apps.folder":
                        excluded_list = [e.lower() for e in root.get("excluded_folders", [])]
                        if name.startswith("_") or name.upper().endswith("_OLD") or name.lower() in excluded_list:
                            logger.info(f"[Top-Down] Dossier '{name}' exclu. On ne descend pas dedans.")
                            await set_cache(f"drive:oos:{file_id}", "1", 86400 * 30)
                            continue

                        queue.append({
                            "folder_id": file_id,
                            "parent_name": name,
                            "root": root
                        })
                        subfolders_in_page += 1

                        # Remplacement du pipeline() sync par deux set_cache() async en gather
                        await _asyncio.gather(
                            set_cache(f"drive:graph:{file_id}", folder_id, 86400 * 30),
                            set_cache(f"drive:name:{file_id}", name, 86400 * 30),
                        )

                    elif mime in _SUPPORTED_CV_MIME_TYPES:
                        file_type = _SUPPORTED_CV_MIME_TYPES[mime]
                        try:
                            mod_time = datetime.fromisoformat(mod_time_str.replace("Z", "+00:00"))

                            upsert_stmt = (
                                pg_insert(DriveSyncState)
                                .values(
                                    google_file_id=file_id,
                                    folder_id=root["id"],
                                    file_name=name,
                                    revision_id=version,
                                    modified_time=mod_time.replace(tzinfo=None),
                                    status=DriveSyncStatus.PENDING.value,
                                    parent_folder_name=parent_name,
                                    last_processed_at=datetime.now(timezone.utc),
                                    file_type=file_type,
                                )
                                .on_conflict_do_update(
                                    index_elements=["google_file_id"],
                                    set_=dict(
                                        file_name=name,
                                        parent_folder_name=parent_name,
                                        folder_id=root["id"],
                                        revision_id=version,
                                        modified_time=mod_time.replace(tzinfo=None),
                                        file_type=file_type,
                                        status=case(
                                            (
                                                DriveSyncState.__table__.c.revision_id != version,
                                                literal(DriveSyncStatus.PENDING.value),
                                            ),
                                            else_=DriveSyncState.__table__.c.status,
                                        ),
                                        last_processed_at=datetime.now(timezone.utc),
                                        # Auto-unblacklist si le fichier a été modifié
                                        extraction_blacklisted=case(
                                            (
                                                DriveSyncState.__table__.c.revision_id != version,
                                                literal(False),
                                            ),
                                            else_=DriveSyncState.__table__.c.extraction_blacklisted,
                                        ),
                                        extraction_attempt_count=case(
                                            (
                                                DriveSyncState.__table__.c.revision_id != version,
                                                literal(0),
                                            ),
                                            else_=DriveSyncState.__table__.c.extraction_attempt_count,
                                        ),
                                        extraction_blacklisted_at=case(
                                            (
                                                DriveSyncState.__table__.c.revision_id != version,
                                                literal(None),
                                            ),
                                            else_=DriveSyncState.__table__.c.extraction_blacklisted_at,
                                        ),
                                    ),
                                )
                            )
                            await self.db.execute(upsert_stmt)
                            await self.db.commit()
                            new_discoveries += 1
                            cvs_in_page += 1

                            await self._mark_file_known(file_id)
                            logger.debug(f"[Top-Down] '{name}' ({file_type}) enregistré (root: {root['tag']}).")
                        except Exception as e:
                            logger.error(f"[Top-Down] Erreur DB/parsing pour le fichier '{name}' ({file_id}): {e}")
                            await self.db.rollback()

                if cvs_in_page > 0 or subfolders_in_page > 0:
                    logger.info(
                        f"[Top-Down] Bilan dossier '{parent_name}' : "
                        f"{cvs_in_page} CV(s) insérés, {subfolders_in_page} sous-dossiers ajoutés."
                    )

                page_token = results.get("nextPageToken")
                if not page_token:
                    break

        return new_discoveries

    async def _discover_delta_bottom_up(self, roots: list[dict]) -> int:
        latest_file = (
            await self.db.execute(select(func.max(DriveSyncState.modified_time)))
        ).scalar()

        if latest_file:
            safe_time = latest_file - timedelta(minutes=1)
            date_query = f" and modifiedTime > '{safe_time.isoformat()}Z'"
        else:
            date_query = ""

        try:
            about = await self.drive_api.get_about()
            sa_email = about.get("user", {}).get("emailAddress", "Unknown")
            logger.info(f"Authentifié sur Google Drive (Bottom-Up) en tant que : {sa_email}")
        except Exception as e:
            logger.error(f"[DRIVE_API_AUTH_LOSS] Le Service Account a perdu l'accès au Drive: {e}")
            raise e

        mime_filter = (
            "mimeType='application/vnd.google-apps.document' or "
            "mimeType='application/vnd.openxmlformats-officedocument.wordprocessingml.document'"
        )
        q = f"({mime_filter}){date_query}"
        logger.info(f"Delta Query: {q}")

        new_discoveries = 0
        for corpus in ["allDrives", "user"]:
            page_token = None
            while True:
                results = await self.drive_api.list_files(q=q, page_token=page_token, corpora=corpus)
                if not results:
                    break

                files = results.get("files", [])
                logger.info(f"Corpus '{corpus}' — {len(files)} fichiers récupérés.")

                for file in files:
                    file_id = file.get("id")
                    name = file.get("name", "Unknown")
                    mod_time_str = file.get("modifiedTime")
                    version = str(file.get("version", "1"))
                    parents = file.get("parents", [])

                    if not parents:
                        continue

                    is_trashed = file.get("trashed", False)

                    try:
                        if await self._is_file_known(file_id):
                            existing = (
                                await self.db.execute(
                                    select(DriveSyncState).filter(
                                        DriveSyncState.google_file_id == file_id
                                    )
                                )
                            ).scalars().first()
                            if existing and existing.revision_id == version and existing.parent_folder_name:
                                continue
                            await delete_cache(f"drive:file:known:{file_id}")

                        mod_time = datetime.fromisoformat(mod_time_str.replace("Z", "+00:00"))

                        root, parent_id, parent_name = await self.tree_resolver.resolve_root_and_parent(
                            parents[0], roots
                        )

                        if root and not is_trashed:
                            upsert_stmt = (
                                pg_insert(DriveSyncState)
                                .values(
                                    google_file_id=file_id,
                                    folder_id=root["id"],
                                    file_name=name,
                                    revision_id=version,
                                    modified_time=mod_time.replace(tzinfo=None),
                                    status=DriveSyncStatus.PENDING.value,
                                    parent_folder_name=parent_name,
                                    last_processed_at=datetime.now(timezone.utc),
                                )
                                .on_conflict_do_update(
                                    index_elements=["google_file_id"],
                                    set_=dict(
                                        file_name=name,
                                        parent_folder_name=parent_name,
                                        folder_id=root["id"],
                                        revision_id=version,
                                        modified_time=mod_time.replace(tzinfo=None),
                                        status=case(
                                            (
                                                DriveSyncState.__table__.c.revision_id != version,
                                                literal(DriveSyncStatus.PENDING.value),
                                            ),
                                            else_=DriveSyncState.__table__.c.status,
                                        ),
                                        last_processed_at=datetime.now(timezone.utc),
                                        # Auto-unblacklist si le fichier a été modifié
                                        extraction_blacklisted=case(
                                            (
                                                DriveSyncState.__table__.c.revision_id != version,
                                                literal(False),
                                            ),
                                            else_=DriveSyncState.__table__.c.extraction_blacklisted,
                                        ),
                                        extraction_attempt_count=case(
                                            (
                                                DriveSyncState.__table__.c.revision_id != version,
                                                literal(0),
                                            ),
                                            else_=DriveSyncState.__table__.c.extraction_attempt_count,
                                        ),
                                        extraction_blacklisted_at=case(
                                            (
                                                DriveSyncState.__table__.c.revision_id != version,
                                                literal(None),
                                            ),
                                            else_=DriveSyncState.__table__.c.extraction_blacklisted_at,
                                        ),
                                    ),
                                )
                            )
                            await self.db.execute(upsert_stmt)
                            await self.db.commit()
                            new_discoveries += 1
                        else:
                            existing_for_oos = (
                                await self.db.execute(
                                    select(DriveSyncState).filter(
                                        DriveSyncState.google_file_id == file_id
                                    )
                                )
                            ).scalars().first()
                            terminal_statuses = (DriveSyncStatus.DELETED_OK.value, DriveSyncStatus.OUT_OF_SCOPE.value)
                            if existing_for_oos and existing_for_oos.status not in terminal_statuses:
                                existing_for_oos.status = DriveSyncStatus.OUT_OF_SCOPE.value
                                await self.db.commit()
                                logger.info(
                                    f"[Bottom-Up] Fichier '{name}' ({file_id}) passé en OUT_OF_SCOPE "
                                    f"(trashed={is_trashed}, root={root is not None})"
                                )
                    except Exception as e:
                        logger.error(f"[Bottom-Up] Erreur DB/parsing pour le fichier '{name}' ({file_id}): {e}")
                        await self.db.rollback()

                page_token = results.get("nextPageToken")
                if not page_token:
                    break

        try:
            await set_cache("drive:sync:last_delta_run", datetime.now(timezone.utc).isoformat(), 86400)
        except Exception as e:
            logger.warning(f"[Bottom-Up] Impossible de mettre à jour drive:sync:last_delta_run dans Redis : {e}")

        return new_discoveries
