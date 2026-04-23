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
        import google.auth
        _, project_id = google.auth.default()
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
                folder_meta = await asyncio.to_thread(
                    lambda cid=current_id: self.drive.files().get(
                        fileId=cid,
                        fields="parents,name",
                        supportsAllDrives=True,
                    ).execute()
                )
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
        needs_initial_sync = (
            await self.db.execute(
                select(DriveFolder).filter(DriveFolder.is_initial_sync_done == False).limit(1)
            )
        ).scalars().first() is not None

        latest_file = (
            await self.db.execute(select(func.max(DriveSyncState.modified_time)))
        ).scalar()

        if latest_file and not needs_initial_sync:
            safe_time = latest_file - timedelta(minutes=1)
            date_query = f" and modifiedTime > '{safe_time.isoformat()}Z'"
        else:
            date_query = ""

        try:
            about = await asyncio.to_thread(
                lambda: self.drive.about().get(fields="user").execute()
            )
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
                results = await asyncio.to_thread(
                    lambda pt=page_token: self.drive.files().list(
                        q=q,
                        spaces="drive",
                        corpora=corpus,
                        includeItemsFromAllDrives=True,
                        supportsAllDrives=True,
                        fields="nextPageToken, files(id, name, modifiedTime, version, parents)",
                        pageToken=pt,
                        pageSize=100,
                    ).execute()
                )

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

                        # Upsert atomique (INSERT … ON CONFLICT DO UPDATE) :
                        # - NOUVEAU : évite d'écraser le status courant (QUEUED/PROCESSING/IMPORTED_CV)
                        #   quand le fichier n'a pas changé de révision.
                        # - Ne repasse à PENDING que si revision_id a réellement changé.
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
                                    # ⚠️ Préserver le statut courant si la révision n'a pas changé.
                                    # Seul un changement de révision justifie un retour à PENDING.
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
                        new_discoveries += 1
                        logger.info(
                            f"[Upsert] '{name}' ({file_id}) — version={version} enregistré."
                        )
                    else:
                        logger.info(
                            f"Fichier '{name}' hors périmètre "
                            f"(parent: {parents[0]})."
                        )

                await self.db.commit()

                page_token = results.get("nextPageToken")
                if not page_token:
                    break

        if needs_initial_sync:
            uninitialized_folders = (
                await self.db.execute(
                    select(DriveFolder).filter(DriveFolder.is_initial_sync_done == False)
                )
            ).scalars().all()
            for f in uninitialized_folders:
                f.is_initial_sync_done = True
            await self.db.commit()

        logger.info(f"Delta Discovery terminé. {new_discoveries} fichiers en queue.")
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

            doc_url = f"https://docs.google.com/document/d/{state.google_file_id}"
            payloads_to_publish.append({
                "state": state,
                "message": {
                    "google_file_id": state.google_file_id,
                    "url": doc_url,
                    "source_tag": folder.tag,
                    "folder_name": state.parent_folder_name or folder.folder_name or "",
                    "google_access_token": google_access_token,
                    # Fix #4 : OIDC token (validité 1h, non expirable pendant le backoff Pub/Sub)
                    # En prod : oidc_token contient un token frais, jwt = ""
                    # En local : oidc_token = "", jwt = MOCK_M2M_JWT
                    "oidc_token": oidc_token,
                    "jwt": m2m_jwt,
                }
            })
            state.status = DriveSyncStatus.QUEUED
            state.last_processed_at = datetime.utcnow()
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
