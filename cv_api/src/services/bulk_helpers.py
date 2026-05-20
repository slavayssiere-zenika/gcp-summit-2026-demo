"""
bulk_helpers.py — Fonctions utilitaires partagées pour le pipeline bulk CV.

Extrait de bulk_service.py (God module) — 2026-05-14.

Fonctions exportées :
  - _acquire_service_token()
  - _get_cv_extraction_prompt()
  - _resolve_competency_ids()
  - _post_missions_bulk()
"""

import asyncio
import logging
import os

import httpx
from opentelemetry.propagate import inject
from shared.semaphore_utils import acquire_shielded
from shared.schemas.pagination import PaginationResponse
from src.services.config import (
    COMPETENCIES_API_URL, ITEMS_API_URL,
    PROMPTS_API_URL, USERS_API_URL,
)
from shared.cache import get_cache, set_cache
from shared.schemas.auth import TokenResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)


async def _acquire_service_token(auth_header: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=10.0) as hc:
            res = await hc.post(
                f"{USERS_API_URL.rstrip('/')}/internal/service-token",
                headers={"Authorization": auth_header},
            )
            if res.status_code == 200:
                data = TokenResponse.model_validate(res.json())
                return data.access_token
            logger.warning(f"[bulk_reanalyse] service-token HTTP {res.status_code} — fallback JWT court.")
    except Exception as e:
        logger.warning(f"[bulk_reanalyse] Impossible d'obtenir le service-token: {e} — fallback JWT court.")
    return auth_header.removeprefix("Bearer ").strip()


async def _get_cv_extraction_prompt() -> str:
    cached_prompt = await get_cache("cv_api:prompt")
    if cached_prompt:
        return cached_prompt
    try:
        async with httpx.AsyncClient(timeout=10.0) as hc:
            res = await hc.get(f"{PROMPTS_API_URL.rstrip('/')}/prompts/cv_api.extract_cv_info")
            if res.status_code == 200:

                class PromptResp(BaseModel):
                    value: str
                data = PromptResp.model_validate(res.json())
                prompt = data.value
                if prompt:
                    await set_cache("cv_api:prompt", prompt, 30 * 60)
                    return prompt
    except Exception as e:
        logger.warning(f"[bulk_reanalyse] prompts_api indisponible: {e}")
    for candidate in ["cv_api.extract_cv_info.txt", "/app/cv_api.extract_cv_info.txt"]:
        if os.path.exists(candidate):
            with open(candidate, "r", encoding="utf-8") as f:
                prompt = f.read()
            await set_cache("cv_api:prompt", prompt, 30 * 60)
            return prompt
    logger.error("[bulk_reanalyse] CRITIQUE : aucun prompt CV disponible")
    return ""


async def _resolve_competency_ids(
    comps_payload: list,
    hc: httpx.AsyncClient,
    req_headers: dict,
    sem: asyncio.Semaphore | None = None,
) -> list[int]:
    """Résout une liste de {name, aliases, practiced} en IDs entiers depuis competencies_api.

    Pour chaque compétence :
      1. Cherche par nom exact (ou alias) via GET /search?q={name}
      2. Si non trouvé → crée via POST / (get-or-create idempotent)
    Retourne les IDs résolus (les échecs sont logés et ignorés).
    """
    _sem = sem or asyncio.Semaphore(10)  # Local — créé dans le corps de la fonction, non persistant entre requêtes.

    def _normalize(s: str) -> str:
        return s.strip().lower().replace("-", " ").replace("_", " ")

    async def _resolve_one(comp: dict) -> int | None:
        name = (comp.get("name") or "").strip()
        if not name:
            return None
        if not comp.get("practiced", True):
            return None  # Compétence non pratiquée : on n'assigne pas
        n_norm = _normalize(name)
        async with acquire_shielded(_sem):  # Protection CancelledError — sémaphore potentiellement injecté module-level
            try:
                res = await hc.get(
                    f"{COMPETENCIES_API_URL.rstrip('/')}/search",
                    params={"q": name, "limit": 10},
                    headers=req_headers,
                    timeout=10.0,
                )
                if res.status_code == 200:
                    data = PaginationResponse[dict].model_validate(res.json())
                    for item in data.items:
                        if _normalize(item.get("name", "")) == n_norm:
                            return item["id"]
                        for alias in (item.get("aliases") or "").split(","):
                            if _normalize(alias.strip()) == n_norm:
                                return item["id"]
            except Exception as search_exc:
                logger.debug("[bulk_resolve] search '%s' failed: %s", name, search_exc)
            # Pas trouvé — création (idempotent)
            aliases_str = ", ".join(comp.get("aliases", []) or []) or None
            try:
                c_res = await hc.post(
                    f"{COMPETENCIES_API_URL.rstrip('/')}/",
                    json={"name": name, "description": "Candidate CV Skill",
                          **(({"aliases": aliases_str}) if aliases_str else {})},
                    headers=req_headers,
                    timeout=10.0,
                )
                if c_res.status_code < 400:
                    c_data = c_res.json()
                    if "id" not in c_data:
                        logger.error(
                            "[bulk_resolve] Rupture de contrat API competencies — champ 'id' absent "
                            "(keys=%s, status=%d). Skip.", list(c_data.keys()), c_res.status_code
                        )
                        return None
                    return c_data["id"]
            except Exception as create_exc:
                logger.warning("[bulk_resolve] create '%s' failed: %s", name, create_exc)
        return None

    tasks = [_resolve_one(c) for c in comps_payload]
    resolved = await asyncio.gather(*tasks, return_exceptions=True)
    return [r for r in resolved if isinstance(r, int)]


async def _post_missions_bulk(hc: httpx.AsyncClient, user_id: int, missions: list, headers: dict):
    if not missions:
        return
    items_payload = []
    for m in missions:
        title = m.get("title") or m.get("company") or "Mission sans titre"
        items_payload.append({
            "name": title[:255],
            "description": m.get("description", "")[:2000],
            "user_id": user_id,
            "category_ids": [],
            "metadata_json": {
                "start_date": m.get("start_date"),
                "end_date": m.get("end_date"),
                "company": m.get("company"),
                "skills": m.get("skills", []),
                "source": "bulk_reanalyse",
            },
        })
    try:
        inject(headers)
        await hc.post(
            f"{ITEMS_API_URL.rstrip('/')}/bulk",
            json={"items": items_payload},
            headers=headers,
            timeout=30.0,
        )
    except Exception as e:
        logger.warning(f"[bulk_reanalyse] items_api /bulk user={user_id}: {e}")
