import os
import json
import redis.asyncio as redis
import httpx
import logging

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
logger = logging.getLogger(__name__)
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

PROMPTS_API_URL = os.getenv("PROMPTS_API_URL", "http://prompts_api:8000")

async def get_cached_prompt(http_client: httpx.AsyncClient, prompt_key: str, headers: dict) -> str:
    """Récupère le prompt depuis le cache Redis (TTL 60s) ou directement depuis PROMPTS_API."""
    cache_key = f"mission_prompt_v1:{prompt_key}"
    
    # 1. Vérification du cache
    try:
        cached_val = await redis_client.get(cache_key)
        if cached_val:
            return cached_val
    except Exception as e:
        logger.warning(f"Erreur de lecture Redis pour le cache des prompts: {e}")

    # 2. Requete distante si absent du cache
    try:
        res = await http_client.get(f"{PROMPTS_API_URL.rstrip('/')}/{prompt_key}", headers=headers, timeout=5.0)
        res.raise_for_status()
        prompt_val = res.json()["value"]
    except Exception as e:
        is_404 = isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 404
        logger.warning(f"Prompt {prompt_key} indisponible (404 ou erreur connexion: {e}). Fallback sur le ficher local.")
        local_filename = None
        if prompt_key == "missions_api.extract_mission_info":
            local_filename = "extract_mission_info.txt"
        elif prompt_key == "missions_api.staffing_heuristics":
            local_filename = "staffing_heuristics.txt"
            
        if local_filename and os.path.exists(local_filename):
            try:
                with open(local_filename, "r", encoding="utf-8") as f:
                    prompt_val = f.read()
            except Exception as file_ex:
                logger.error(f"Echec de lecture du fallback {local_filename}: {file_ex}")
                raise e
        else:
            logger.error(f"Cannot fetch generic prompt {prompt_key}: No fallback.")
            raise e

    # 3. Sauvegarde avec TTL (60s pour la bufferisation des bursts, gérant implicitement l'invalidation partielle)
    try:
        await redis_client.setex(cache_key, 60, prompt_val)
    except Exception as e:
        logger.warning(f"Erreur d'écriture Redis pour le cache: {e}")
        
    return prompt_val

async def force_invalidate_prompt(prompt_key: str):
    """Invalide manuellement le cache (Webhook use-case)."""
    try:
        await redis_client.delete(f"mission_prompt_v1:{prompt_key}")
    except Exception as e:
        pass
