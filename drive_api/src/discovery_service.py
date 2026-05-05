import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, literal, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import DriveFolder, DriveSyncState, DriveSyncStatus

logger = logging.getLogger(__name__)

# Cache TTLs
REDIS_TTL_ROOTS = 300
REDIS_TTL_GRAPH = 2592000
REDIS_TTL_KNOWN_FILE = 86400
REDIS_TTL_OUT_OF_SCOPE = 86400

REDIS_KEY_ROOTS = "drive:roots"

_SUPPORTED_CV_MIME_TYPES: dict[str, str] = {
    "application/vnd.google-apps.document": "google_doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}


class DiscoveryService:
    def __init__(self, db: AsyncSession, drive, redis):
        self.db = db
        self.drive = drive
        self.redis = redis

    # ── Cache helpers ────────────────────────────────────────────────────────

    def _get_cached_roots(self) -> list[dict] | None:
        raw = self.redis.get(REDIS_KEY_ROOTS)
        if raw:
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                logger.warning("[Cache] drive:roots — données corrompues, invalidation.")
                self.redis.delete(REDIS_KEY_ROOTS)
        return None

    def _set_cached_roots(self, roots: list[dict]) -> None:
        try:
            self.redis.set(REDIS_KEY_ROOTS, json.dumps(roots), ex=REDIS_TTL_ROOTS)
        except Exception as e:
            logger.warning(f"[Cache] Impossible d'écrire drive:roots: {e}")

    def invalidate_roots_cache(self) -> None:
        self.redis.delete(REDIS_KEY_ROOTS)
        logger.info("[Cache] drive:roots invalidé suite à une mutation de folder.")

    def _is_file_known(self, file_id: str) -> bool:
        return bool(self.redis.get(f"drive:file:known:{file_id}"))

    def _mark_file_known(self, file_id: str) -> None:
        self.redis.set(f"drive:file:known:{file_id}", "IMPORTED_CV", ex=REDIS_TTL_KNOWN_FILE)

    def _cache_path(self, path: list, root_folder_id: int) -> None:
        for intermediate_id in path:
            self.redis.set(f"drive:graph:{intermediate_id}", str(root_folder_id), ex=REDIS_TTL_GRAPH)

    # ── Résolution ascendante ────────────────────────────────────────────────

    async def _load_roots(self) -> list[dict]:
        cached = self._get_cached_roots()
        if cached is not None:
            logger.debug(f"[Cache] drive:roots — HIT ({len(cached)} folders)")
            return cached

        db_folders = (await self.db.execute(select(DriveFolder))).scalars().all()
        roots = [
            {
                "id": f.id,
                "google_folder_id": f.google_folder_id,
                "tag": f.tag,
                "folder_name": f.folder_name,
                "excluded_folders": f.excluded_folders or [],
            }
            for f in db_folders
        ]
        self._set_cached_roots(roots)
        logger.info(f"[Cache] drive:roots — MISS → {len(roots)} folders chargés depuis DB.")
        return roots

    def _find_root_in_cache(self, folder_id: str, roots: list[dict]) -> dict | None:
        for r in roots:
            if folder_id in r["google_folder_id"] or r["google_folder_id"] in folder_id:
                return r
        return None

    def _check_excluded(self, path_traversed_names: list, path_traversed: list, root: dict) -> bool:
        """Retourne True si un nœud parcouru est dans la liste d'exclusion de la racine."""
        excluded_list = [e.lower() for e in root.get("excluded_folders", [])]
        for node_name in path_traversed_names:
            if node_name.lower() in excluded_list:
                logger.info(
                    f"[_resolve_root_and_parent] Dossier '{node_name}' exclu (présent dans excluded_folders). Arrêt."
                )
                if path_traversed:
                    pipe = self.redis.pipeline()
                    for oos_id in path_traversed:
                        pipe.set(f"drive:oos:{oos_id}", "1", ex=REDIS_TTL_OUT_OF_SCOPE)
                    pipe.execute()
                return True
        return False

    async def _resolve_root_and_parent(
        self, start_parent_id: str, roots: list[dict]
    ) -> tuple[dict | None, str | None, str | None]:
        current_id = start_parent_id
        path_traversed = []
        path_traversed_names = []

        raw = self.redis.get(f"drive:name:{start_parent_id}")
        parent_folder_name = raw.decode("utf-8") if isinstance(raw, bytes) else raw

        if not parent_folder_name:
            try:
                folder_meta = await asyncio.to_thread(
                    lambda: self.drive.files().get(
                        fileId=start_parent_id,
                        fields="name",
                        supportsAllDrives=True,
                    ).execute()
                )
                parent_folder_name = folder_meta.get("name", "")
                self.redis.set(f"drive:name:{start_parent_id}", parent_folder_name, ex=REDIS_TTL_GRAPH)
            except Exception as e:
                logger.error(f"Erreur Drive API pour folder name {start_parent_id}: {e}")

        while current_id:
            logger.info(f"[_resolve_root_and_parent] Évaluation du nœud: {current_id}")

            root = self._find_root_in_cache(current_id, roots)
            if root:
                logger.info(f"[_resolve_root_and_parent] Trouvé racine: {current_id} → tag={root['tag']}")
                if self._check_excluded(path_traversed_names, path_traversed, root):
                    return None, None, None
                self._cache_path(path_traversed, root["id"])
                return root, start_parent_id, parent_folder_name

            if self.redis.get(f"drive:oos:{current_id}"):
                logger.debug(
                    f"[_resolve_root_and_parent] Nœud {current_id} blacklisté (hors périmètre) — skip."
                )
                return None, None, None

            cached_root_id = self.redis.get(f"drive:graph:{current_id}")
            if cached_root_id:
                logger.info(
                    f"[_resolve_root_and_parent] Cache graphe HIT: {current_id} → root_id={cached_root_id}"
                )
                root = next((r for r in roots if r["id"] == int(cached_root_id)), None)
                if root:
                    if self._check_excluded(path_traversed_names, path_traversed, root):
                        return None, None, None
                    self._cache_path(path_traversed, root["id"])
                    return root, start_parent_id, parent_folder_name
                else:
                    self.redis.delete(f"drive:graph:{current_id}")
                    logger.warning(
                        f"[_resolve_root_and_parent] Root {cached_root_id} en cache mais absent en DB. Cache purgé."
                    )

            try:
                logger.info(f"[_resolve_root_and_parent] Appel Drive API pour: {current_id}")
                folder_meta = None
                for attempt in range(3):
                    try:
                        folder_meta = await asyncio.to_thread(
                            lambda cid=current_id: self.drive.files().get(
                                fileId=cid,
                                fields="parents,name",
                                supportsAllDrives=True,
                            ).execute()
                        )
                        break
                    except Exception as e:
                        logger.warning(f"Erreur Drive API get pour {current_id} (attempt {attempt + 1}): {e}")
                        if attempt == 2:
                            raise
                        await asyncio.sleep(2 ** attempt)

                folder_name_raw = folder_meta.get("name", "")
                parents = folder_meta.get("parents", [])

                path_traversed_names.append(folder_name_raw)

                logger.info(
                    f"[_resolve_root_and_parent] Nœud '{folder_name_raw}' ({current_id}) — "
                    f"parents: {parents} | Chemins traversés (noms): {path_traversed_names}"
                )

                if folder_name_raw.startswith("_") or folder_name_raw.upper().endswith("_OLD"):
                    logger.info(
                        f"[_resolve_root_and_parent] Dossier '{folder_name_raw}' exclu "
                        f"(règle de nommage: préfixe _ ou suffixe _OLD). Arrêt de la résolution."
                    )
                    return None, None, None

                if parent_folder_name is None:
                    parent_folder_name = folder_name_raw
                    self.redis.set(f"drive:name:{start_parent_id}", folder_name_raw, ex=REDIS_TTL_GRAPH)

                if not parents:
                    logger.info(
                        f"[_resolve_root_and_parent] Racine absolue Drive atteinte pour {current_id} "
                        f"('{folder_name_raw}') — hors périmètre, mise en blacklist (24h)."
                    )
                    oos_ids = path_traversed + [current_id]
                    pipe = self.redis.pipeline()
                    for oos_id in oos_ids:
                        pipe.set(f"drive:oos:{oos_id}", "1", ex=REDIS_TTL_OUT_OF_SCOPE)
                    pipe.execute()
                    logger.info(
                        f"[_resolve_root_and_parent] {len(oos_ids)} nœuds blacklistés "
                        f"(racine='{folder_name_raw}')."
                    )
                    break

                path_traversed.append(current_id)
                path_traversed_names.append(folder_name_raw)
                current_id = parents[0]

            except Exception as e:
                logger.error(f"Erreur Drive API pour {current_id}: {e}")
                break

        return None, None, None

    # ── Découverte des fichiers (Delta et Full) ──────────────────────────────

    async def discover_files(self, force_full: bool = False) -> int:
        roots = await self._load_roots()
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
                results = None
                for attempt in range(3):
                    try:
                        results = await asyncio.to_thread(
                            lambda pt=page_token: self.drive.files().list(
                                q=q,
                                spaces="drive",
                                corpora="allDrives",
                                includeItemsFromAllDrives=True,
                                supportsAllDrives=True,
                                fields="nextPageToken, files(id, name, mimeType, modifiedTime, version)",
                                pageToken=pt,
                                pageSize=1000,
                            ).execute()
                        )
                        break
                    except Exception as e:
                        logger.warning(f"Erreur Drive API list (Top-Down, attempt {attempt + 1}): {e}")
                        if attempt == 2:
                            logger.error(f"Echec Drive API list pour {folder_id}, on saute ce dossier.")
                            break
                        await asyncio.sleep(2 ** attempt)

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
                            self.redis.set(f"drive:oos:{file_id}", "1", ex=86400 * 30)
                            continue

                        queue.append({
                            "folder_id": file_id,
                            "parent_name": name,
                            "root": root
                        })
                        subfolders_in_page += 1

                        pipe = self.redis.pipeline()
                        pipe.set(f"drive:graph:{file_id}", folder_id, ex=86400 * 30)
                        pipe.set(f"drive:name:{file_id}", name, ex=86400 * 30)
                        pipe.execute()

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
                                    ),
                                )
                            )
                            await self.db.execute(upsert_stmt)
                            await self.db.commit()
                            new_discoveries += 1
                            cvs_in_page += 1

                            self.redis.set(f"drive:file:known:{file_id}", "1", ex=86400 * 30)

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
            about = await asyncio.to_thread(
                lambda: self.drive.about().get(fields="user").execute()
            )
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
                results = None
                for attempt in range(3):
                    try:
                        results = await asyncio.to_thread(
                            lambda pt=page_token: self.drive.files().list(
                                q=q,
                                spaces="drive",
                                corpora=corpus,
                                includeItemsFromAllDrives=True,
                                supportsAllDrives=True,
                                fields="nextPageToken, files(id, name, modifiedTime, version, parents, trashed)",
                                pageToken=pt,
                                pageSize=1000,
                            ).execute()
                        )
                        break
                    except Exception as e:
                        logger.warning(f"Erreur Drive API list (Bottom-Up, attempt {attempt + 1}): {e}")
                        if attempt == 2:
                            raise
                        await asyncio.sleep(2 ** attempt)

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
                        if self._is_file_known(file_id):
                            existing = (
                                await self.db.execute(
                                    select(DriveSyncState).filter(
                                        DriveSyncState.google_file_id == file_id
                                    )
                                )
                            ).scalars().first()
                            if existing and existing.revision_id == version and existing.parent_folder_name:
                                continue
                            self.redis.delete(f"drive:file:known:{file_id}")

                        mod_time = datetime.fromisoformat(mod_time_str.replace("Z", "+00:00"))

                        root, parent_id, parent_name = await self._resolve_root_and_parent(
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

        return new_discoveries
