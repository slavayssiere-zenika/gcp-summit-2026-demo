import asyncio
import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.cache import delete_cache, get_cache, set_cache
from src.models import DriveFolder
from src.services.google_api_client import DriveApiClient

logger = logging.getLogger(__name__)

REDIS_TTL_ROOTS = 300
REDIS_TTL_GRAPH = 2592000
REDIS_TTL_OUT_OF_SCOPE = 86400
REDIS_KEY_ROOTS = "drive:roots"


class TreeResolver:
    def __init__(self, db: AsyncSession, drive_api: DriveApiClient):
        """TreeResolver utilise shared.cache pour toutes les opérations Redis (async)."""
        self.db = db
        self.drive_api = drive_api

    async def _get_cached_roots(self) -> list[dict] | None:
        raw = await get_cache(REDIS_KEY_ROOTS)
        if raw is not None:
            if isinstance(raw, str):
                try:
                    return json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    logger.warning("[Cache] drive:roots — données corrompues, invalidation.")
                    await delete_cache(REDIS_KEY_ROOTS)
            elif isinstance(raw, list):
                return raw
        return None

    async def _set_cached_roots(self, roots: list[dict]) -> None:
        try:
            await set_cache(REDIS_KEY_ROOTS, json.dumps(roots), REDIS_TTL_ROOTS)
        except Exception as e:
            logger.warning(f"[Cache] Impossible d'écrire drive:roots: {e}")

    async def invalidate_roots_cache(self) -> None:
        await delete_cache(REDIS_KEY_ROOTS)
        logger.info("[Cache] drive:roots invalidé suite à une mutation de folder.")

    async def _cache_path(self, path: list, root_folder_id: int) -> None:
        await asyncio.gather(*[
            set_cache(f"drive:graph:{intermediate_id}", str(root_folder_id), REDIS_TTL_GRAPH)
            for intermediate_id in path
        ])

    async def load_roots(self) -> list[dict]:
        cached = await self._get_cached_roots()
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
        await self._set_cached_roots(roots)
        logger.info(f"[Cache] drive:roots — MISS → {len(roots)} folders chargés depuis DB.")
        return roots

    def _find_root_in_cache(self, folder_id: str, roots: list[dict]) -> dict | None:
        for r in roots:
            if folder_id in r["google_folder_id"] or r["google_folder_id"] in folder_id:
                return r
        return None

    async def _check_excluded(
        self, path_traversed_names: list, path_traversed: list, root: dict
    ) -> bool:
        excluded_list = [e.lower() for e in root.get("excluded_folders", [])]
        for node_name in path_traversed_names:
            if node_name.lower() in excluded_list:
                logger.info(
                    f"[_resolve_root_and_parent] Dossier '{node_name}' exclu "
                    f"(présent dans excluded_folders). Arrêt."
                )
                if path_traversed:
                    await asyncio.gather(*[
                        set_cache(f"drive:oos:{oos_id}", "1", REDIS_TTL_OUT_OF_SCOPE)
                        for oos_id in path_traversed
                    ])
                return True
        return False

    async def resolve_root_and_parent(
        self, start_parent_id: str, roots: list[dict]
    ) -> tuple[dict | None, str | None, str | None]:
        current_id = start_parent_id
        path_traversed = []
        path_traversed_names = []

        raw = await get_cache(f"drive:name:{start_parent_id}")
        parent_folder_name = raw if isinstance(raw, str) else (raw.decode("utf-8") if raw else None)

        if not parent_folder_name:
            try:
                folder_meta = await self.drive_api.get_folder_meta(start_parent_id, fields="name")
                if folder_meta:
                    parent_folder_name = folder_meta.get("name", "")
                    await set_cache(
                        f"drive:name:{start_parent_id}", parent_folder_name, REDIS_TTL_GRAPH
                    )
            except Exception as e:
                logger.error(f"Erreur Drive API pour folder name {start_parent_id}: {e}")

        while current_id:
            logger.info(f"[_resolve_root_and_parent] Évaluation du nœud: {current_id}")

            root = self._find_root_in_cache(current_id, roots)
            if root:
                logger.info(
                    f"[_resolve_root_and_parent] Trouvé racine: {current_id} → tag={root['tag']}"
                )
                if await self._check_excluded(path_traversed_names, path_traversed, root):
                    return None, None, None
                await self._cache_path(path_traversed, root["id"])
                return root, start_parent_id, parent_folder_name

            if await get_cache(f"drive:oos:{current_id}"):
                logger.debug(
                    f"[_resolve_root_and_parent] Nœud {current_id} blacklisté (hors périmètre) — skip."
                )
                return None, None, None

            cached_root_id = await get_cache(f"drive:graph:{current_id}")
            if cached_root_id:
                logger.info(
                    f"[_resolve_root_and_parent] Cache graphe HIT: {current_id} → root_id={cached_root_id}"
                )
                root = next((r for r in roots if r["id"] == int(cached_root_id)), None)
                if root:
                    if await self._check_excluded(path_traversed_names, path_traversed, root):
                        return None, None, None
                    await self._cache_path(path_traversed, root["id"])
                    return root, start_parent_id, parent_folder_name
                else:
                    await delete_cache(f"drive:graph:{current_id}")
                    logger.warning(
                        f"[_resolve_root_and_parent] Root {cached_root_id} en cache mais absent en DB. "
                        f"Cache purgé."
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
                    await set_cache(
                        f"drive:name:{start_parent_id}", folder_name_raw, REDIS_TTL_GRAPH
                    )

                if not parents:
                    logger.info(
                        f"[_resolve_root_and_parent] Racine absolue Drive atteinte pour {current_id} "
                        f"('{folder_name_raw}') — hors périmètre, mise en blacklist (24h)."
                    )
                    oos_ids = path_traversed + [current_id]
                    await asyncio.gather(*[
                        set_cache(f"drive:oos:{oos_id}", "1", REDIS_TTL_OUT_OF_SCOPE)
                        for oos_id in oos_ids
                    ])
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
