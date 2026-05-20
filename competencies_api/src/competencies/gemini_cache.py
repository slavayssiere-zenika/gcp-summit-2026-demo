"""
gemini_cache.py — Context caching Gemini v2.3 pour competencies_api.

Le context caching permet de mettre en cache un contenu fixe (system prompt,
règles métier) côté serveur Gemini pour éviter de le re-tokeniser à chaque appel.

Gains FinOps estimés : 30-50% sur les tokens d'entrée répétitifs.
Voir : https://cloud.google.com/vertex-ai/generative-ai/docs/context-cache/overview

Contraintes :
  - Requiert Vertex AI (vertexai=True dans genai.Client) — pas l'API key directe.
  - Contenu minimum : 1024 tokens dans le cache.
  - Modèles supportés : gemini-2.0-flash, gemini-2.5-flash, gemini-3.1-flash et variantes.
  - TTL défaut : 3600s (1h) — renouvelé automatiquement si < 5 min restantes.
"""

import logging
import os
from typing import Optional
from shared.cache import get_cache, set_cache

logger = logging.getLogger(__name__)

# TTL du cache Gemini (secondes). Configurable via env pour A/B testing.
GEMINI_CACHE_TTL_S: int = int(os.getenv("GEMINI_CACHE_TTL_S", "3600"))

# Le system prompt fixe des règles de pondération du scoring — invariant pour tous les appels.
SCORING_SYSTEM_PROMPT = (
    "Tu es un évaluateur expert de consultants IT et tech (scoring v2 avec pondération). "
    "Tu notes la maîtrise d'une compétence de 0.0 à 5.0 (par pas de 0.5).\n\n"
    "=== RÈGLES DE PONDÉRATION OBLIGATOIRES ===\n"
    "1. RÉCENCE : chaque mission affiche un 'poids' entre 0.0 et 1.0.\n"
    "   - poids proche de 1.0 = mission récente → compte PLEINEMENT\n"
    "   - poids 0.2-0.4 = mission ancienne → compte de façon RÉDUITE\n"
    "2. DURÉE : chaque mission affiche un 'multiplicateur' entre 0.5 et 1.5.\n"
    "3. TYPE DE MISSION : audit/conseil/accompagnement/formation/expertise = bonus +0.3 à +0.5.\n\n"
    "=== NIVEAUX DE RÉFÉRENCE ===\n"
    "  0.0: Aucune trace | 1.0: Notions | 2.0: Utilisation ponctuelle\n"
    "  3.0: Maîtrise confirmée | 4.0: Expert | 5.0: Référence reconnue\n\n"
    "=== FORMAT DE RÉPONSE OBLIGATOIRE ===\n"
    "Réponds UNIQUEMENT avec du JSON valide contenant exactement deux champs :\n"
    '- score : float 0.0-5.0, arrondi au pas de 0.5\n'
    '- justification : string factuel, 50-250 caractères\n'
    'Exemple : {"score": 3.5, "justification": "2 missions récentes (weight>0.9) dont 1 audit Airbus (+0.5)."}  '
    "# noqa: E501"
)

# (Le cache redis remplacera l'ancien dictionnaire mémoire _CACHE_STORE)


def _is_vertex_available(client) -> bool:
    """Vérifie si le client est en mode Vertex AI (context caching disponible)."""
    try:
        # google-genai v2 : _api_client.vertexai est un attribut boolean
        return bool(getattr(client._api_client, "vertexai", False))
    except Exception:
        return False


async def get_or_create_scoring_cache(client, model: str) -> Optional[str]:
    """Retourne le nom d'un CachedContent Gemini pour le scoring system prompt.

    Crée le cache si inexistant ou si le TTL restant est < 5 min.
    Retourne None si le context caching est indisponible (API key mode ou quota).

    Args:
        client: Instance genai.Client en mode Vertex AI.
        model: Nom du modèle Gemini (ex: 'gemini-3.1-flash-001').

    Returns:
        Nom du cache (str) ou None si indisponible.
    """
    if not _is_vertex_available(client):
        logger.debug("[gemini_cache] Context caching non disponible (API key mode) — skip")
        return None

    redis_key = f"competencies:gemini_cache:{model}"
    cache_entry = await get_cache(redis_key)

    if cache_entry:
        # Vérification du TTL restant
        try:
            existing = await client.aio.caches.get(name=cache_entry["name"])
            expire_time = existing.expire_time
            if expire_time:
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc)
                remaining_s = (expire_time - now).total_seconds()
                if remaining_s > 300:  # Plus de 5 min → réutiliser
                    logger.debug(
                        "[gemini_cache] Réutilisation cache '%s' (%.0fs restant)",
                        cache_entry["name"], remaining_s
                    )
                    return cache_entry["name"]
                logger.info(
                    "[gemini_cache] Cache '%s' expire bientôt (%.0fs) — renouvellement",
                    cache_entry["name"], remaining_s
                )
        except Exception as e:
            logger.warning("[gemini_cache] Cache introuvable ou expiré (%s) — recréation", e)

    # Création du CachedContent
    try:
        from google.genai import types

        cache = await client.aio.caches.create(
            model=model,
            config=types.CreateCachedContentConfig(
                system_instruction=SCORING_SYSTEM_PROMPT,
                ttl=f"{GEMINI_CACHE_TTL_S}s",
                display_name=f"zenika-scoring-system-prompt-{model}",
            ),
        )
        await set_cache(redis_key, {"name": cache.name}, GEMINI_CACHE_TTL_S)
        logger.info(
            "[gemini_cache] ✅ CachedContent créé : '%s' (TTL=%ds, model=%s)",
            cache.name, GEMINI_CACHE_TTL_S, model
        )
        return cache.name
    except Exception as e:
        logger.warning(
            "[gemini_cache] Impossible de créer le CachedContent (model=%s): %s — fallback sans cache",
            model, e
        )
        return None
