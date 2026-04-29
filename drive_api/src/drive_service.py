import json
import os
import asyncio
import logging
from datetime import datetime, timedelta

import httpx
from google.cloud import pubsub_v1
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, update, case, literal
from sqlalchemy.dialects.postgresql import insert as pg_insert
from opentelemetry.propagate import inject

from src.models import DriveFolder, DriveSyncState, DriveSyncStatus
from src.redis_client import get_redis
from src.google_auth import get_drive_service, get_m2m_jwt_token, get_google_access_token, get_google_oidc_id_token

logger = logging.getLogger(__name__)

MAX_DRIVE_CV_IMPORT = int(os.getenv("MAX_DRIVE_CV_IMPORT", "15"))
PUBSUB_CV_IMPORT_TOPIC = os.getenv("PUBSUB_CV_IMPORT_TOPIC", "")
_GCP_PROJECT_ID_ENV = os.getenv("GCP_PROJECT_ID", "")

# Mapping MIME type Drive → label file_type stocké en base et transmis dans le payload Pub/Sub.
# Ajouter ici tout nouveau format à supporter (PDF exclut : nécessite OCR externe).
_SUPPORTED_CV_MIME_TYPES: dict[str, str] = {
    "application/vnd.google-apps.document": "google_doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}


def _resolve_gcp_project_id() -> str:
    """
    Résout le GCP project ID dans l'ordre de priorité suivant :
    1. Variable d'environnement GCP_PROJECT_ID (si présente et non-placeholder)
    2. Project ID détecté via google.auth.default() (ADC — fonctionne sur Cloud Run nativement)
    3. Chaîne vide (la publication Pub/Sub sera sautée avec un log d'erreur)

    google.auth.default() retourne (credentials, project_id) où project_id
    est lu depuis GOOGLE_CLOUD_PROJECT, gcloud config, ou les métadonnées Cloud Run.
    """
    # Rejeter les valeurs env manquantes ou placeholder non configurées
    env_val = _GCP_PROJECT_ID_ENV.strip()
    if env_val and env_val not in ("your-gcp-project-id", "YOUR_GCP_PROJECT_ID", ""):
        return env_val

    # Fallback : détection automatique via ADC (sans réseau supplémentaire)
    try:
        import google.auth as _google_auth  # noqa: PLC0415 — lazy import requis (évite circular si ADC absent)
        _, project_id = _google_auth.default()
        if project_id:
            logger.info(f"[PubSub] GCP project ID résolu via ADC : '{project_id}'")
            return project_id
    except Exception as e:
        logger.warning(f"[PubSub] Impossible de résoudre le project ID via google.auth.default(): {e}")

    logger.error("[PubSub] GCP project ID introuvable — publication Pub/Sub impossible.")
    return ""

# Cache TTLs
REDIS_TTL_ROOTS = 300        # 5 minutes pour la liste des folders racines
REDIS_TTL_GRAPH = 2592000    # 30 jours pour le mapping ascendant (inchangé)
REDIS_TTL_KNOWN_FILE = 86400 # 24 heures pour les fichiers déjà importés
REDIS_TTL_OUT_OF_SCOPE = 86400  # 24 heures pour les racines Drive hors périmètre

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
                "excluded_folders": f.excluded_folders or [],
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
        path_traversed_names = []  # Pour vérifier les exclusions plus tard
        parent_folder_name = self.redis.get(f"drive:name:{start_parent_id}")
        if parent_folder_name:
            parent_folder_name = parent_folder_name.decode('utf-8') if isinstance(parent_folder_name, bytes) else parent_folder_name
            
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

            # 1. Est-ce un folder racine configuré ?
            root = self._find_root_in_cache(current_id, roots)
            if root:
                logger.info(
                    f"[_resolve_root_and_parent] Trouvé racine: {current_id} → tag={root['tag']}"
                )
                
                # Vérifier les exclusions sur les dossiers parcourus jusqu'ici
                excluded_list = [e.lower() for e in root.get("excluded_folders", [])]
                for node_name in path_traversed_names:
                    if node_name.lower() in excluded_list:
                        logger.info(
                            f"[_resolve_root_and_parent] Dossier '{node_name}' exclu (présent dans excluded_folders). Arrêt."
                        )
                        # Blacklister ce chemin pour les prochaines fois, MAIS SURTOUT PAS LE ROOT (current_id) !
                        oos_ids = path_traversed
                        if oos_ids:
                            pipe = self.redis.pipeline()
                            for oos_id in oos_ids:
                                pipe.set(f"drive:oos:{oos_id}", "1", ex=REDIS_TTL_OUT_OF_SCOPE)
                            pipe.execute()
                        return None, None, None

                self._cache_path(path_traversed, root["id"])
                return root, start_parent_id, parent_folder_name

            # 1b. Ce nœud est-il en blacklist (racine hors périmètre connue) ?
            if self.redis.get(f"drive:oos:{current_id}"):
                logger.debug(
                    f"[_resolve_root_and_parent] Nœud {current_id} blacklisté (hors périmètre) — skip."
                )
                return None, None, None

            # 2. Cache graphe pour le chemin intermédiaire
            cached_root_id = self.redis.get(f"drive:graph:{current_id}")
            if cached_root_id:
                logger.info(f"[_resolve_root_and_parent] Cache graphe HIT: {current_id} → root_id={cached_root_id}")
                root = next((r for r in roots if r["id"] == int(cached_root_id)), None)
                if root:
                    # Vérifier les exclusions sur les dossiers parcourus (le cache graphe indique juste que current_id -> root est valide)
                    excluded_list = [e.lower() for e in root.get("excluded_folders", [])]
                    for node_name in path_traversed_names:
                        if node_name.lower() in excluded_list:
                            logger.info(
                                f"[_resolve_root_and_parent] Dossier '{node_name}' exclu (présent dans excluded_folders). Arrêt."
                            )
                            # Blacklister les enfants parcourus
                            oos_ids = path_traversed
                            if oos_ids:
                                pipe = self.redis.pipeline()
                                for oos_id in oos_ids:
                                    pipe.set(f"drive:oos:{oos_id}", "1", ex=REDIS_TTL_OUT_OF_SCOPE)
                                pipe.execute()
                            return None, None, None

                    self._cache_path(path_traversed, root["id"])
                    return root, start_parent_id, parent_folder_name
                else:
                    # Root supprimé mais encore dans le cache — invalider silencieusement
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
                        logger.warning(f"Erreur Drive API get pour {current_id} (attempt {attempt+1}): {e}")
                        if attempt == 2:
                            raise
                        await asyncio.sleep(2 ** attempt)

                folder_name_raw = folder_meta.get("name", "")
                parents = folder_meta.get("parents", [])
                
                path_traversed_names.append(folder_name_raw)

                logger.info(
                    f"[_resolve_root_and_parent] Nœud '{folder_name_raw}' ({current_id}) — parents: {parents} | Chemins traversés (noms): {path_traversed_names}"
                )

                # Règle d'exclusion : les répertoires commençant par '_' ou se terminant par '_OLD' sont ignorés
                if folder_name_raw.startswith("_") or folder_name_raw.upper().endswith("_OLD"):
                    logger.info(
                        f"[_resolve_root_and_parent] Dossier '{folder_name_raw}' exclu "
                        f"(règle de nommage: préfixe _ ou suffixe _OLD). Arrêt de la résolution."
                    )
                    return None, None, None

                # Mémoriser le nom du dossier le plus proche du fichier
                # (premier nœud remontant depuis start_parent_id)
                if parent_folder_name is None:
                    parent_folder_name = folder_name_raw
                    self.redis.set(f"drive:name:{start_parent_id}", folder_name_raw, ex=REDIS_TTL_GRAPH)

                if not parents:
                    logger.info(
                        f"[_resolve_root_and_parent] Racine absolue Drive atteinte pour {current_id} "
                        f"('{folder_name_raw}') — hors périmètre, mise en blacklist (24h)."
                    )
                    # Blacklister la racine absolue et tout le chemin parcouru
                    # pour éviter les appels Drive API redondants au prochain cycle.
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
        """
        Orchestrateur de la découverte.
        - force_full=True : Top-Down récursif sur tous les dossiers (rapide pour reconstruire l'arbre)
        - force_full=False : Top-Down pour les nouveaux dossiers, puis Bottom-Up (Delta) pour le reste.
        """
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
            # 1. Nouveaux dossiers (Top-Down)
            uninitialized_folders = (
                await self.db.execute(
                    select(DriveFolder).filter(DriveFolder.is_initial_sync_done == False)
                )
            ).scalars().all()
            
            uninit_ids = {f.id for f in uninitialized_folders}
            target_roots = [r for r in roots if r["id"] in uninit_ids]
            
            if target_roots:
                logger.info(f"Démarrage sync Top-Down pour {len(target_roots)} NOUVELLES racines.")
                total_discovered += await self._discover_full_top_down(target_roots)
                
                # Marquer comme initialisé
                for root_dict in target_roots:
                    await self.db.execute(
                        update(DriveFolder).where(DriveFolder.id == root_dict["id"]).values(is_initial_sync_done=True)
                    )
                await self.db.commit()

            # 2. Delta sur les dossiers existants (Bottom-Up)
            logger.info("Démarrage sync Bottom-Up Delta pour les autres fichiers.")
            total_discovered += await self._discover_delta_bottom_up(roots)

        logger.info(f"Discovery terminé. {total_discovered} fichiers découverts au total.")
        return total_discovered

    async def _discover_full_top_down(self, roots: list[dict]) -> int:
        """
        Parcours descendant (Top-Down BFS) ultra-rapide depuis les racines fournies.
        """
        new_discoveries = 0
        queue = []
        
        # Initialiser la queue avec les racines
        for root in roots:
            queue.append({
                "folder_id": root["google_folder_id"],
                "parent_name": root["tag"], # Au niveau 0, le parent est le nom du tag ou root
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
                        logger.warning(f"Erreur Drive API list (Top-Down, attempt {attempt+1}): {e}")
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
                        # Vérification des exclusions
                        excluded_list = [e.lower() for e in root.get("excluded_folders", [])]
                        if name.startswith("_") or name.upper().endswith("_OLD") or name.lower() in excluded_list:
                            logger.info(f"[Top-Down] Dossier '{name}' exclu. On ne descend pas dedans.")
                            self.redis.set(f"drive:oos:{file_id}", "1", ex=86400 * 30) # 30 jours
                            continue
                        
                        queue.append({
                            "folder_id": file_id,
                            "parent_name": name,
                            "root": root
                        })
                        subfolders_in_page += 1
                        
                        # Remplissage proactif du cache du graphe
                        pipe = self.redis.pipeline()
                        pipe.set(f"drive:graph:{file_id}", folder_id, ex=86400 * 30)
                        pipe.set(f"drive:name:{file_id}", name, ex=86400 * 30)
                        pipe.execute()
                    
                    elif mime in _SUPPORTED_CV_MIME_TYPES:
                        file_type = _SUPPORTED_CV_MIME_TYPES[mime]
                        try:
                            # C'est un CV (Google Doc natif ou DOCX) !
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
                                    last_processed_at=datetime.utcnow(),
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
                                        last_processed_at=datetime.utcnow(),
                                    ),
                                )
                            )
                            await self.db.execute(upsert_stmt)
                            await self.db.commit()
                            new_discoveries += 1
                            cvs_in_page += 1

                            # Remplissage proactif du cache "connu" pour le Bottom-Up
                            self.redis.set(f"drive:file:known:{file_id}", "1", ex=86400 * 30)

                            logger.debug(f"[Top-Down] '{name}' ({file_type}) enregistré (root: {root['tag']}).")
                        except Exception as e:
                            logger.error(f"[Top-Down] Erreur DB/parsing pour le fichier '{name}' ({file_id}): {e}")
                            await self.db.rollback()
                
                if cvs_in_page > 0 or subfolders_in_page > 0:
                    logger.info(f"[Top-Down] Bilan dossier '{parent_name}' : {cvs_in_page} CV(s) insérés, {subfolders_in_page} sous-dossiers ajoutés à la file d'attente.")
                
                page_token = results.get("nextPageToken")
                if not page_token:
                    break
                    
        return new_discoveries

    async def _discover_delta_bottom_up(self, roots: list[dict]) -> int:
        """
        Étape Delta global (Bottom-Up) : détecte uniquement les fichiers modifiés récemment.
        """
        latest_file = (
            await self.db.execute(select(func.max(DriveSyncState.modified_time)))
        ).scalar()

        if latest_file:
            # On recule d'1 minute par sécurité
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

        q = f"mimeType='application/vnd.google-apps.document' and trashed=false{date_query}"
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
                                fields="nextPageToken, files(id, name, modifiedTime, version, parents)",
                                pageToken=pt,
                                pageSize=1000,
                            ).execute()
                        )
                        break
                    except Exception as e:
                        logger.warning(f"Erreur Drive API list (Bottom-Up, attempt {attempt+1}): {e}")
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

                    try:
                        # Cache hit : fichier déjà importé et version inchangée → skip DB
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
    
                        if root:
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
                                    last_processed_at=datetime.utcnow(),
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
                                        last_processed_at=datetime.utcnow(),
                                    ),
                                )
                            )
                            await self.db.execute(upsert_stmt)
                            await self.db.commit()
                            new_discoveries += 1
                    except Exception as e:
                        logger.error(f"[Bottom-Up] Erreur DB/parsing pour le fichier '{name}' ({file_id}): {e}")
                        await self.db.rollback()
                        
                page_token = results.get("nextPageToken")
                if not page_token:
                    break

        return new_discoveries

    # ── Ingestion par batch ───────────────────────────────────────────────────

    async def ingest_batch(self) -> int:
        """
        Étape 2 : Publication des fichiers PENDING dans Pub/Sub (zenika-cv-import-events).
        
        Architecture Event-Driven :
        - drive_api = Publisher : publie un message JSON dans le topic GCP et bascule en QUEUED.
        - cv_api   = Worker    : reçoit la push notification, exécute le pipeline LLM+Compétences+Missions,
                                 puis notifie drive_api (PATCH /files/{id}) avec IMPORTED_CV ou ERROR.
        - Pub/Sub gère le retry (backoff 30s→600s) et la DLQ après 5 échecs.
        """
        # 0. Libération des zombies (fichiers bloqués en PROCESSING/QUEUED suite à un redémarrage)
        zombie_threshold = datetime.utcnow() - timedelta(minutes=15)
        zombie_stmt = (
            update(DriveSyncState)
            .where(DriveSyncState.status.in_([DriveSyncStatus.PROCESSING, DriveSyncStatus.QUEUED]))
            .where(DriveSyncState.last_processed_at < zombie_threshold)
            .values(status=DriveSyncStatus.PENDING, error_message="Réinitialisé automatiquement (Interruption processus)")
        )
        await self.db.execute(zombie_stmt)
        await self.db.commit()

        base_query = (
            select(DriveSyncState)
            .filter(DriveSyncState.status == DriveSyncStatus.PENDING)
            .order_by(DriveSyncState.modified_time.asc())
            .limit(MAX_DRIVE_CV_IMPORT)
        )
        pending_files = (await self.db.execute(base_query)).scalars().all()

        if not pending_files:
            return 0

        # Tentative OIDC token (production Cloud Run) — validité 1h, éliminé les JWTError 'expired'
        # en cas de backoff Pub/Sub. En local (USE_IAM_AUTH != true) — fallback sur M2M JWT.
        oidc_token = get_google_oidc_id_token()
        m2m_jwt = get_m2m_jwt_token() if not oidc_token else ""
        google_access_token = await asyncio.to_thread(get_google_access_token)
        pubsub_topic = PUBSUB_CV_IMPORT_TOPIC
        gcp_project_id = _resolve_gcp_project_id()

        # Résolution des folders (une seule requête DB)
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

            # URL selon le type de fichier
            ft = state.file_type or "google_doc"
            if ft == "docx":
                doc_url = f"https://drive.google.com/file/d/{state.google_file_id}"
            else:
                doc_url = f"https://docs.google.com/document/d/{state.google_file_id}"

            payloads_to_publish.append({
                "state": state,
                "message": {
                    "google_file_id": state.google_file_id,
                    "url": doc_url,
                    "source_tag": folder.tag,
                    "folder_name": state.parent_folder_name or folder.folder_name or "",
                    "google_access_token": google_access_token,
                    "file_type": ft,
                    # Fix #4 : OIDC token (validité 1h, non expirable pendant le backoff Pub/Sub)
                    # En prod : oidc_token contient un token frais, jwt = ""
                    # En local : oidc_token = "", jwt = MOCK_M2M_JWT
                    "oidc_token": oidc_token,
                    "jwt": m2m_jwt,
                }
            })
            state.status = DriveSyncStatus.QUEUED
            state.last_processed_at = datetime.utcnow()
            state.queued_at = datetime.utcnow()
            logger.info(f"[PubSub] Enqueue CV — fichier='{state.file_name}', folder='{state.parent_folder_name}', tag={folder.tag}")

        await self.db.commit()

        if not payloads_to_publish:
            return 0

        # Publication dans Pub/Sub (blocking I/O dans thread pool pour compatibilité asyncio)
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
