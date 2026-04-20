import json
import os
import logging
from datetime import datetime, timedelta

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from opentelemetry.propagate import inject

from src.models import DriveFolder, DriveSyncState, DriveSyncStatus
from src.redis_client import get_redis
from src.google_auth import get_drive_service, get_m2m_jwt_token, get_google_access_token

logger = logging.getLogger(__name__)

CV_API_URL = os.getenv("CV_API_URL", "http://cv_api:8004")
MAX_DRIVE_CV_IMPORT = int(os.getenv("MAX_DRIVE_CV_IMPORT", "10"))

# Cache TTLs
REDIS_TTL_ROOTS = 300        # 5 minutes pour la liste des folders racines
REDIS_TTL_GRAPH = 2592000    # 30 jours pour le mapping ascendant (inchangé)
REDIS_TTL_KNOWN_FILE = 86400 # 24 heures pour les fichiers déjà importés

REDIS_KEY_ROOTS = "drive:roots"


class DriveService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.drive = get_drive_service()
        self.redis = get_redis()

    # ── Cache helpers ────────────────────────────────────────────────────────

    def _get_cached_roots(self) -> list[dict] | None:
        """
        Retourne la liste des DriveFolder racines depuis Redis.
        Clé: drive:roots — TTL 5 min.
        Retourne None si cache miss.
        """
        raw = self.redis.get(REDIS_KEY_ROOTS)
        if raw:
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                logger.warning("[Cache] drive:roots — données corrompues, invalidation.")
                self.redis.delete(REDIS_KEY_ROOTS)
        return None

    def _set_cached_roots(self, roots: list[dict]) -> None:
        """Écrit la liste des DriveFolder racines dans Redis."""
        try:
            self.redis.set(REDIS_KEY_ROOTS, json.dumps(roots), ex=REDIS_TTL_ROOTS)
        except Exception as e:
            logger.warning(f"[Cache] Impossible d'écrire drive:roots: {e}")

    def invalidate_roots_cache(self) -> None:
        """Invalide le cache des folders racines (appeler sur POST/DELETE /folders)."""
        self.redis.delete(REDIS_KEY_ROOTS)
        logger.info("[Cache] drive:roots invalidé suite à une mutation de folder.")

    def _is_file_known(self, file_id: str) -> bool:
        """True si le fichier est déjà marqué IMPORTED_CV dans le cache Redis."""
        return bool(self.redis.get(f"drive:file:known:{file_id}"))

    def _mark_file_known(self, file_id: str) -> None:
        """Mémorise un fichier comme importé avec succès (skip possible lors du prochain cycle)."""
        self.redis.set(f"drive:file:known:{file_id}", "IMPORTED_CV", ex=REDIS_TTL_KNOWN_FILE)

    def _cache_path(self, path: list, root_folder_id: int) -> None:
        """Sauvegarde les dossiers intermédiaires vers la racine dans Redis (30 jours)."""
        for intermediate_id in path:
            self.redis.set(f"drive:graph:{intermediate_id}", str(root_folder_id), ex=REDIS_TTL_GRAPH)

    # ── Résolution ascendante ────────────────────────────────────────────────

    async def _load_roots(self) -> list[dict]:
        """
        Charge la liste des DriveFolder racines depuis Redis ou DB.
        Format: [{"id": int, "google_folder_id": str, "tag": str, "folder_name": str|None}, ...]
        """
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
            }
            for f in db_folders
        ]
        self._set_cached_roots(roots)
        logger.info(f"[Cache] drive:roots — MISS → {len(roots)} folders chargés depuis DB.")
        return roots

    def _find_root_in_cache(self, folder_id: str, roots: list[dict]) -> dict | None:
        """Cherche un folder_id (exact ou substring) dans la liste des racines chargées."""
        for r in roots:
            if folder_id in r["google_folder_id"] or r["google_folder_id"] in folder_id:
                return r
        return None

    async def _resolve_root_and_parent(
        self, start_parent_id: str, roots: list[dict]
    ) -> tuple[dict | None, str | None, str | None]:
        """
        Résolution ascendante depuis le dossier parent d'un fichier.

        Remonte l'arbre Drive jusqu'à trouver un dossier racine configuré.
        Retourne:
            - root_folder (dict) ou None si hors périmètre
            - parent_folder_id: ID Drive du parent **direct** du fichier
            - parent_folder_name: Nom du parent direct (nomenclature "Prénom Nom" Zenika)

        Règle d'exclusion : tout dossier dont le nom commence par '_' est ignoré.

        Cache:
            - drive:roots (TTL 5 min) — liste des folders racines
            - drive:graph:{id} (TTL 30 j) — mapping intermédiaire → root_folder.id
        """
        current_id = start_parent_id
        path_traversed = []
        parent_folder_name = None  # Nom du dossier parent direct du fichier

        while current_id:
            logger.info(f"[_resolve_root_and_parent] Évaluation du nœud: {current_id}")

            # 1. Est-ce un folder racine configuré ?
            root = self._find_root_in_cache(current_id, roots)
            if root:
                logger.info(
                    f"[_resolve_root_and_parent] Trouvé racine: {current_id} → tag={root['tag']}"
                )
                self._cache_path(path_traversed, root["id"])
                return root, start_parent_id, parent_folder_name

            # 2. Cache graphe pour le chemin intermédiaire
            cached_root_id = self.redis.get(f"drive:graph:{current_id}")
            if cached_root_id:
                logger.info(f"[_resolve_root_and_parent] Cache graphe HIT: {current_id} → root_id={cached_root_id}")
                root = next((r for r in roots if r["id"] == int(cached_root_id)), None)
                if root:
                    self._cache_path(path_traversed, root["id"])
                    return root, start_parent_id, parent_folder_name
                else:
                    # Root supprimé mais encore dans le cache — invalider silencieusement
                    self.redis.delete(f"drive:graph:{current_id}")
                    logger.warning(
                        f"[_resolve_root_and_parent] Root {cached_root_id} en cache mais absent en DB. Cache purgé."
                    )

            # 3. Appel API Drive pour remonter d'un niveau
            try:
                logger.info(f"[_resolve_root_and_parent] Appel Drive API pour: {current_id}")
                folder_meta = self.drive.files().get(
                    fileId=current_id,
                    fields="parents,name",
                    supportsAllDrives=True,
                ).execute()
                folder_name_raw = folder_meta.get("name", "")
                parents = folder_meta.get("parents", [])

                logger.info(
                    f"[_resolve_root_and_parent] Nœud '{folder_name_raw}' ({current_id}) — parents: {parents}"
                )

                # Règle d'exclusion : les répertoires commençant par '_' sont ignorés
                if folder_name_raw.startswith("_"):
                    logger.info(
                        f"[_resolve_root_and_parent] Dossier '{folder_name_raw}' exclu "
                        f"(préfixe underscore). Arrêt de la résolution."
                    )
                    return None, None, None

                # Mémoriser le nom du dossier le plus proche du fichier
                # (premier nœud remontant depuis start_parent_id)
                if parent_folder_name is None:
                    parent_folder_name = folder_name_raw

                if not parents:
                    logger.info(
                        f"[_resolve_root_and_parent] Racine absolue Drive atteinte pour {current_id}."
                    )
                    break

                path_traversed.append(current_id)
                current_id = parents[0]

            except Exception as e:
                logger.error(f"Erreur Drive API pour {current_id}: {e}")
                break

        return None, None, None

    # ── Découverte des fichiers (Delta) ──────────────────────────────────────

    async def discover_files(self) -> int:
        """
        Étape 1 : Delta global — détecte les fichiers nouveaux ou modifiés depuis la dernière sync.

        Optimisations cache Redis :
        - drive:roots (TTL 5 min) : évite N SELECT DB pour résoudre l'arbre parent.
        - drive:file:known:{id} : skip immédiat des fichiers déjà IMPORTED_CV (sans hit DB).

        Règle d'exclusion :
        - Les dossiers dont le nom commence par '_' sont ignorés (et leurs descendants).
        """
        latest_file = (
            await self.db.execute(select(func.max(DriveSyncState.modified_time)))
        ).scalar()

        if latest_file:
            safe_time = latest_file - timedelta(minutes=1)
            date_query = f" and modifiedTime > '{safe_time.isoformat()}Z'"
        else:
            date_query = ""

        try:
            about = self.drive.about().get(fields="user").execute()
            sa_email = about.get("user", {}).get("emailAddress", "Unknown")
            logger.info(f"Authentifié sur Google Drive en tant que : {sa_email}")
        except Exception as e:
            logger.error(f"[DRIVE_API_AUTH_LOSS] Le Service Account a perdu l'accès au Drive: {e}")
            raise e

        q = f"mimeType='application/vnd.google-apps.document' and trashed=false{date_query}"
        logger.info(f"Delta Query: {q}")

        # Charger les roots une seule fois (cache Redis ou DB)
        roots = await self._load_roots()
        if not roots:
            logger.warning("[discover_files] Aucun folder racine configuré — sync interrompue.")
            return 0

        new_discoveries = 0
        for corpus in ["allDrives", "user"]:
            page_token = None
            while True:
                results = self.drive.files().list(
                    q=q,
                    spaces="drive",
                    corpora=corpus,
                    includeItemsFromAllDrives=True,
                    supportsAllDrives=True,
                    fields="nextPageToken, files(id, name, modifiedTime, version, parents)",
                    pageToken=page_token,
                    pageSize=100,
                ).execute()

                files = results.get("files", [])
                logger.info(f"Corpus '{corpus}' — {len(files)} fichiers récupérés.")

                for file in files:
                    file_id = file.get("id")
                    name = file.get("name", "Unknown")
                    mod_time_str = file.get("modifiedTime")
                    version = str(file.get("version", "1"))
                    parents = file.get("parents", [])

                    logger.info(f"Évaluation: '{name}' ({file_id}) — parents: {parents}")

                    if not parents:
                        logger.info(f"Fichier {file_id} sans parent, ignoré.")
                        continue

                    # Cache hit : fichier déjà importé et version inchangée → skip DB
                    if self._is_file_known(file_id):
                        # Vérifier tout de même si la version a changé (nécessite un accès DB minimal)
                        existing = (
                            await self.db.execute(
                                select(DriveSyncState).filter(
                                    DriveSyncState.google_file_id == file_id
                                )
                            )
                        ).scalars().first()
                        if existing and existing.revision_id == version:
                            logger.debug(
                                f"[Cache] Fichier '{name}' ({file_id}) déjà importé et non modifié → skip."
                            )
                            continue
                        # Version changée : invalider le cache et laisser passer
                        self.redis.delete(f"drive:file:known:{file_id}")
                        logger.info(
                            f"[Cache] Fichier '{name}' ({file_id}) mis à jour (v{version}) → réingestion."
                        )

                    mod_time = datetime.fromisoformat(mod_time_str.replace("Z", "+00:00"))

                    # Résolution ascendante (avec cache Redis optimisé)
                    root, parent_id, parent_name = await self._resolve_root_and_parent(
                        parents[0], roots
                    )

                    if root:
                        logger.info(
                            f"Fichier '{name}' → root tag={root['tag']}, "
                            f"parent_folder='{parent_name}'"
                        )
                        state = (
                            await self.db.execute(
                                select(DriveSyncState).filter(
                                    DriveSyncState.google_file_id == file_id
                                )
                            )
                        ).scalars().first()

                        if not state:
                            state = DriveSyncState(
                                google_file_id=file_id,
                                folder_id=root["id"],
                                file_name=name,
                                revision_id=version,
                                modified_time=mod_time.replace(tzinfo=None),
                                status=DriveSyncStatus.PENDING,
                                parent_folder_name=parent_name,
                            )
                            self.db.add(state)
                            new_discoveries += 1
                        else:
                            if state.file_name != name:
                                state.file_name = name
                            if parent_name and state.parent_folder_name != parent_name:
                                state.parent_folder_name = parent_name
                            if state.revision_id != version:
                                state.revision_id = version
                                state.modified_time = mod_time.replace(tzinfo=None)
                                state.status = DriveSyncStatus.PENDING
                                new_discoveries += 1
                    else:
                        logger.info(
                            f"Fichier '{name}' hors périmètre "
                            f"(parent: {parents[0]})."
                        )

                await self.db.commit()

                page_token = results.get("nextPageToken")
                if not page_token:
                    break

        logger.info(f"Delta Discovery terminé. {new_discoveries} fichiers en queue.")
        return new_discoveries

    # ── Ingestion par batch ───────────────────────────────────────────────────

    async def ingest_batch(self) -> int:
        """
        Étape 2 : Traitement des fichiers PENDING par batch (MAX_DRIVE_CV_IMPORT).

        Transmet à cv_api :
        - url : URL Google Docs
        - source_tag : tag du folder racine configuré
        - folder_name : nom du dossier parent direct (nomenclature "Prénom Nom" Zenika)
        - google_access_token : token ADC pour lecture du document

        Post-import : met à jour le cache drive:file:known:{id} si import réussi.
        """
        base_query = (
            select(DriveSyncState)
            .filter(DriveSyncState.status == DriveSyncStatus.PENDING)
            .order_by(DriveSyncState.modified_time.asc())
            .limit(MAX_DRIVE_CV_IMPORT)
        )
        pending_files = (await self.db.execute(base_query)).scalars().all()

        if not pending_files:
            return 0

        m2m_jwt = get_m2m_jwt_token()
        headers = {"Authorization": f"Bearer {m2m_jwt}"}
        google_access_token = get_google_access_token()

        processed_count = 0
        async with httpx.AsyncClient(timeout=60.0) as http_client:
            for state in pending_files:
                folder = (
                    await self.db.execute(
                        select(DriveFolder).filter(DriveFolder.id == state.folder_id)
                    )
                ).scalars().first()
                if not folder:
                    state.status = DriveSyncStatus.ERROR
                    continue

                doc_url = f"https://docs.google.com/document/d/{state.google_file_id}"

                payload = {
                    "url": doc_url,
                    "source_tag": folder.tag,
                    "google_access_token": google_access_token,
                    # Nomenclature Zenika : nom du dossier parent direct (ex: "Marie Dupont")
                    "folder_name": state.parent_folder_name,
                }

                inject(headers)  # OTel propagation (Golden Rule §5)

                try:
                    logger.info(
                        f"Ingestion CV — fichier='{state.file_name}', "
                        f"folder='{state.parent_folder_name}', tag={folder.tag}"
                    )
                    state.status = DriveSyncStatus.PROCESSING
                    await self.db.commit()

                    res = await http_client.post(
                        f"{CV_API_URL.rstrip('/')}/import",
                        json=payload,
                        headers=headers,
                    )
                    if res.status_code < 400:
                        data = res.json()
                        state.status = DriveSyncStatus.IMPORTED_CV
                        state.user_id = data.get("user_id")
                        processed_count += 1
                        # Mémoriser dans Redis pour skip lors du prochain cycle
                        self._mark_file_known(state.google_file_id)
                        logger.info(
                            f"Import OK — {state.google_file_id} ('{state.file_name}') "
                            f"→ user_id={state.user_id}"
                        )
                    else:
                        error_detail = res.json().get("detail", "")
                        if "LLM Parsing failed" in error_detail or "Not a CV" in error_detail:
                            state.status = DriveSyncStatus.IGNORED_NOT_CV
                            logger.info(f"Fichier ignoré (non-CV): {state.google_file_id}")
                        else:
                            state.status = DriveSyncStatus.ERROR
                            logger.error(
                                f"Import échoué '{state.file_name}' ({state.google_file_id}): "
                                f"{error_detail}"
                            )
                except Exception as e:
                    state.status = DriveSyncStatus.ERROR
                    logger.error(
                        f"Erreur réseau pour '{state.file_name}' ({state.google_file_id}): {e}"
                    )

                state.last_processed_at = datetime.utcnow()
                await self.db.commit()

        return processed_count
