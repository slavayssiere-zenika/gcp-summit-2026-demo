import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import DriveFolder
from src.services.google_api_client import DriveApiClient

logger = logging.getLogger(__name__)

REDIS_TTL_ROOTS = 300
REDIS_TTL_GRAPH = 2592000
REDIS_TTL_OUT_OF_SCOPE = 86400
REDIS_KEY_ROOTS = "drive:roots"

class TreeResolver:
    def __init__(self, db: AsyncSession, drive_api: DriveApiClient, redis):
        self.db = db
        self.drive_api = drive_api
        self.redis = redis

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

    def _cache_path(self, path: list, root_folder_id: int) -> None:
        for intermediate_id in path:
            self.redis.set(f"drive:graph:{intermediate_id}", str(root_folder_id), ex=REDIS_TTL_GRAPH)

    async def load_roots(self) -> list[dict]:
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

    async def resolve_root_and_parent(
        self, start_parent_id: str, roots: list[dict]
    ) -> tuple[dict | None, str | None, str | None]:
        current_id = start_parent_id
        path_traversed = []
        path_traversed_names = []

        raw = self.redis.get(f"drive:name:{start_parent_id}")
        parent_folder_name = raw.decode("utf-8") if isinstance(raw, bytes) else raw

        if not parent_folder_name:
            try:
                folder_meta = await self.drive_api.get_folder_meta(start_parent_id, fields="name")
                if folder_meta:
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
                folder_meta = await self.drive_api.get_folder_meta(current_id, fields="parents,name")
                if not folder_meta:
                    break

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
