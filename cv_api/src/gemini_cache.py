"""
gemini_cache.py — Context caching Gemini v2.3 pour cv_api.

Cache les system prompts des étapes du pipeline de taxonomie
(Map, Deduplicate, Reduce, Sweep) pour réduire les coûts FinOps.

Contraintes :
  - Requiert Vertex AI (vertex_batch_client) — pas l'API key directe.
  - Contenu minimum : 1024 tokens dans le cache.
  - TTL défaut : 3600s — renouvelé si < 5 min restantes.
  - Supporté sur : gemini-2.0-flash, gemini-2.5-flash, gemini-3.1-flash et variantes.

Usage pattern :
    from src.gemini_cache import get_or_create_prompt_cache, generate_with_cache

    cache_name = await get_or_create_prompt_cache(client, model, system_prompt, cache_key)
    response = await generate_with_cache(client, model, user_content, cache_name)
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

GEMINI_CACHE_TTL_S: int = int(os.getenv("GEMINI_CACHE_TTL_S", "3600"))

# Dictionnaire en mémoire : cache_key → {"name": str, "model": str}
_CACHE_STORE: dict = {}


def _is_vertex_available(client) -> bool:
    """Vérifie si le client genai est en mode Vertex AI."""
    try:
        return bool(getattr(client._api_client, "vertexai", False))
    except Exception:
        return False


async def get_or_create_prompt_cache(
    client,
    model: str,
    system_prompt: str,
    cache_key: str,
) -> Optional[str]:
    """Retourne le nom d'un CachedContent Gemini pour un system prompt donné.

    Crée le cache si inexistant ou expiré. Retourne None si le context
    caching est indisponible (API key mode, quota, ou modèle non supporté).

    Args:
        client: Instance genai.Client en mode Vertex AI.
        model: Nom du modèle (ex: 'gemini-3.1-flash-001').
        system_prompt: Contenu à cacher (doit faire >= 1024 tokens).
        cache_key: Clé unique pour ce prompt (ex: 'taxonomy_map_v1').

    Returns:
        Nom du cache (str) ou None.
    """
    if not _is_vertex_available(client):
        logger.debug("[gemini_cache] Context caching non disponible (API key mode) — skip")
        return None

    full_key = f"{model}:{cache_key}"
    cache_entry = _CACHE_STORE.get(full_key)

    if cache_entry:
        try:
            existing = await client.aio.caches.get(name=cache_entry["name"])
            expire_time = existing.expire_time
            if expire_time:
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc)
                remaining_s = (expire_time - now).total_seconds()
                if remaining_s > 300:
                    logger.debug(
                        "[gemini_cache] Réutilisation '%s' (%.0fs restant)", cache_entry["name"], remaining_s
                    )
                    return cache_entry["name"]
                logger.info(
                    "[gemini_cache] Cache '%s' expire bientôt (%.0fs) — renouvellement",
                    cache_entry["name"], remaining_s
                )
        except Exception as e:
            logger.warning("[gemini_cache] Cache introuvable (%s) — recréation", e)
            _CACHE_STORE.pop(full_key, None)

    try:
        from google.genai import types

        cache = await client.aio.caches.create(
            model=model,
            config=types.CreateCachedContentConfig(
                system_instruction=system_prompt,
                ttl=f"{GEMINI_CACHE_TTL_S}s",
                display_name=f"zenika-{cache_key}-{model}",
            ),
        )
        _CACHE_STORE[full_key] = {"name": cache.name}
        logger.info(
            "[gemini_cache] ✅ CachedContent créé : '%s' (key=%s, TTL=%ds)",
            cache.name, cache_key, GEMINI_CACHE_TTL_S
        )
        return cache.name
    except Exception as e:
        logger.warning(
            "[gemini_cache] Impossible de créer le CachedContent (key=%s, model=%s): %s — fallback",
            cache_key, model, e
        )
        return None
