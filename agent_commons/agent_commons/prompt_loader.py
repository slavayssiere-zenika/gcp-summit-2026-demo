"""
prompt_loader.py — Chargement et cache des system prompts depuis prompts_api.

Module partagé pour tous les agents (HR, Ops, Missions).
Le Router dispose de son propre prompt_loader.py avec des fonctionnalités
supplémentaires (prompt utilisateur par session, directive de langue).

Expose :
  fetch_agent_prompt()  : récupère un prompt avec cache Redis TTL
  PromptValue           : modèle Pydantic pour valider le contrat prompts_api

Usage :
    from agent_commons.prompt_loader import fetch_agent_prompt

    instruction_text = await fetch_agent_prompt(
        prompt_key="agent_hr_api.system_instruction",
        default_text="Tu es l'Agent RH de Zenika.",
        auth_header=auth_header_var.get(),
        agent_prefix="[HR]",
    )
"""
import logging
import os

import httpx
from opentelemetry.propagate import inject
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

_PROMPT_CACHE_TTL_S: int = int(os.getenv("PROMPT_CACHE_TTL_S", "60"))


class PromptValue(BaseModel):
    """Contrat de réponse de l'endpoint GET /{key}/compiled de prompts_api.

    Champs :
        value : Texte du prompt compilé (non vide si succès).
    """

    value: str = ""


async def fetch_agent_prompt(
    prompt_key: str,
    default_text: str,
    auth_header: str | None,
    agent_prefix: str = "[AGENT]",
) -> str:
    """Charge le system prompt d'un agent depuis prompts_api avec cache Redis.

    Suit le pattern validé de prompt_loader.py du Router :
    - Cache Redis TTL (PROMPT_CACHE_TTL_S, défaut 60s) pour éviter 1 HTTP/requête.
    - Validation Pydantic (ADR-0015) pour détecter les ruptures de contrat.
    - Fallback sur default_text si prompts_api est indisponible.

    Args:
        prompt_key:   Clé du prompt en DB (ex: "agent_hr_api.system_instruction").
        default_text: Texte de fallback si prompts_api est inaccessible.
        auth_header:  Token Bearer à propager (Authorization). None si non auth.
        agent_prefix: Préfixe de log (ex: "[HR]", "[OPS]", "[MISSIONS]").

    Returns:
        Texte du system prompt (depuis prompts_api ou default_text).
    """
    # Import ici pour éviter une dépendance circulaire si shared n'est pas disponible
    # en environnement de test unitaire sans Redis.
    try:
        from shared.cache import get_cache, set_cache
        _cache_available = True
    except ImportError:
        _cache_available = False
        logger.warning(
            "%s shared.cache not available — prompt cache disabled", agent_prefix
        )

    prompts_api_url = os.getenv("PROMPTS_API_URL", "http://prompts_api:8000")
    cache_key = f"prompt:{prompt_key}"

    # ── 1. Cache Redis (si disponible) ───────────────────────────────────────
    if _cache_available:
        try:
            cached = await get_cache(cache_key)
            if cached is not None:
                logger.debug("%s [PromptCache] HIT key=%s", agent_prefix, prompt_key)
                return cached
        except Exception as e:
            logger.warning(
                "%s [PromptCache] Redis unavailable: %s — skipping cache", agent_prefix, e
            )

    # ── 2. Appel HTTP à prompts_api ──────────────────────────────────────────
    headers: dict[str, str] = {"Authorization": auth_header} if auth_header else {}
    inject(headers)

    url = f"{prompts_api_url.rstrip('/')}/{prompt_key}/compiled"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(url, headers=headers)

        if res.status_code == 200:
            try:
                data = PromptValue.model_validate(res.json())
                prompt_text = data.value
            except ValidationError as ve:
                logger.warning(
                    "%s [PromptCache] Rupture contrat prompts_api key=%s: %s",
                    agent_prefix, prompt_key, ve,
                )
                return default_text

            if prompt_text:
                # ── 3. Mise en cache Redis ──────────────────────────────────
                if _cache_available:
                    try:
                        await set_cache(cache_key, prompt_text, _PROMPT_CACHE_TTL_S)
                        logger.debug(
                            "%s [PromptCache] STORED key=%s TTL=%ds",
                            agent_prefix, prompt_key, _PROMPT_CACHE_TTL_S,
                        )
                    except Exception as e:
                        logger.warning(
                            "%s [PromptCache] Redis write failed: %s", agent_prefix, e
                        )
                return prompt_text
        else:
            logger.warning(
                "%s [PromptCache] prompts_api HTTP %s for key=%s — using default",
                agent_prefix, res.status_code, prompt_key,
            )

    except Exception as e:
        logger.warning(
            "%s [PromptCache] Fetch failed for key=%s: %s — using default",
            agent_prefix, prompt_key, e,
        )

    return default_text
