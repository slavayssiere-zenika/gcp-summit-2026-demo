"""
prompt_loader.py — Chargement et cache des system prompts depuis prompts_api.

Expose :
  _fetch_prompt_cached()  : récupère un prompt avec cache Redis TTL
  build_instruction_text(): construit le prompt système complet pour un agent

Séparé de agent.py pour respecter le seuil de 400 lignes (Golden Rule §14).
"""
import logging
import os

import httpx
from opentelemetry.propagate import inject
from pydantic import BaseModel, ValidationError
from shared.cache import get_cache, set_cache

logger = logging.getLogger(__name__)

_PROMPT_CACHE_TTL_S: int = int(os.getenv("PROMPT_CACHE_TTL_S", "60"))

_ROUTER_INSTRUCTION_DEFAULT = (
    "Tu es l'Orchestrateur Principal de la plateforme Zenika, le 'Front-Desk'. "
    "Ton rôle est de diriger la demande vers le hub approprié en utilisant tes outils "
    "de délégation (A2A). Ne dis pas 'je vais interroger mon collègue', sois direct."
)

LANGUAGE_DIRECTIVES: dict[str, str] = {
    "fr": "Réponds TOUJOURS en français, quelle que soit la langue de la demande.",
    "en": "Always respond in English, regardless of the language of the request.",
}


class _PromptValue(BaseModel):
    value: str = ""


async def _fetch_prompt_cached(cache_key: str, url: str, headers: dict) -> str | None:
    """Récupère un prompt depuis prompts_api avec cache TTL Redis.

    Retourne le texte du prompt si disponible (cache chaud ou API réussie),
    ou None si le cache est froid et l'API échoue.

    Args:
        cache_key: Clé de cache unique (ex: "router" ou "user:abc123").
        url:       URL complète de l'endpoint prompts_api.
        headers:   Headers HTTP à propager (Authorization + OTel).
    """
    cached = await get_cache(f"prompt:{cache_key}")
    if cached is not None:
        logger.debug("[PromptCache] HIT key=%s", cache_key)
        return cached

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            inject(headers)
            res = await client.get(url, headers=headers, timeout=10.0)
            if res.status_code == 200:
                try:
                    data = _PromptValue.model_validate(res.json())
                    prompt_text = data.value
                except ValidationError as ve:
                    logger.warning(
                        "[PromptCache] Rupture contrat prompts_api key=%s: %s",
                        cache_key, ve,
                    )
                    return None
                if prompt_text:
                    await set_cache(f"prompt:{cache_key}", prompt_text, _PROMPT_CACHE_TTL_S)
                    logger.debug(
                        "[PromptCache] STORED key=%s TTL=%ds",
                        cache_key, _PROMPT_CACHE_TTL_S,
                    )
                    return prompt_text
            else:
                logger.warning(
                    "[PromptCache] prompts_api returned HTTP %s for key=%s — using default",
                    res.status_code, cache_key,
                )
    except Exception as e:
        logger.warning("[PromptCache] Fetch failed for key=%s: %s — using default", cache_key, e)

    return None


async def build_instruction_text(
    session_id: str | None,
    auth_header: str | None,
    preferred_language: str = "fr",
) -> str:
    """Construit le system prompt final pour le Router Agent.

    1. Charge le prompt global depuis prompts_api (caché 60s).
    2. Charge le prompt utilisateur si session_id est défini (caché 60s par session).
    3. Injecte la directive de langue en tête.

    Args:
        session_id: ID de session ADK (None ou "anon" → skip prompt user).
        auth_header: Token Bearer à propager (Authorization).
        preferred_language: Code langue ISO-2 ("fr" | "en").

    Returns:
        Texte du system prompt complet.
    """
    prompts_api_url = os.getenv("PROMPTS_API_URL", "http://prompts_api:8000")
    instruction_text = _ROUTER_INSTRUCTION_DEFAULT
    headers = {"Authorization": auth_header} if auth_header else {}

    # ── Appel 1 : system prompt router (caché TTL 60s) ───────────────────────
    router_prompt_url = f"{prompts_api_url.rstrip('/')}/agent_router_api.system_instruction/compiled"
    fetched = await _fetch_prompt_cached("router", router_prompt_url, headers)
    if fetched:
        instruction_text = fetched

    # ── Appel 2 : prompt utilisateur (caché par session_id, TTL 60s) ─────────
    if session_id and session_id != "anon":
        user_prompt_url = f"{prompts_api_url.rstrip('/')}/user_{session_id}"
        user_prompt = await _fetch_prompt_cached(f"user:{session_id}", user_prompt_url, headers)
        if user_prompt:
            instruction_text += (
                f"\n\n--- INSTRUCTIONS UTILISATEUR ({session_id}) ---\n"
                f"{user_prompt}\n"
                "------------------------------------------------------------"
            )

    # ── Directive de langue ───────────────────────────────────────────────────
    lang_directive = LANGUAGE_DIRECTIVES.get(
        preferred_language[:2].lower(),
        LANGUAGE_DIRECTIVES["fr"],
    )
    return f"{lang_directive}\n\n{instruction_text}"
