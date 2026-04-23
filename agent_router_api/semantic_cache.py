"""
SEC-F06 — Semantic Cache LLM
Module de cache sémantique pour intercepter les requêtes sémantiquement
similaires avant l'appel Gemini, générant une économie FinOps significative.

Architecture :
  1. Génération de l'embedding de la requête via gemini-embedding-001
  2. Recherche par cosine similarity dans Redis (clés semcache:*)
  3. Si score >= seuil : retour immédiat + log BQ avec action="semantic_cache_hit"
  4. Sinon : appel LLM normal + stockage en cache (fire-and-forget)

Paramètres configurables (env vars) :
  SEMANTIC_CACHE_ENABLED    : "true"/"false" (défaut: true)
  SEMANTIC_CACHE_THRESHOLD  : float 0.0-1.0 (défaut: 0.95)
  SEMANTIC_CACHE_TTL        : int secondes  (défaut: 900 = 15 min)
  GEMINI_EMBEDDING_MODEL    : str           (défaut: gemini-embedding-001)
  REDIS_URL                 : str           (défaut: redis://redis:6379/1)
"""

import json
import logging
import math
import os
import time
import uuid
from typing import Optional

import redis

logger = logging.getLogger(__name__)

# Mots-clés indiquant une requête temps-réel — JAMAIS mis en cache
# ATTENTION : utiliser des mots-clés suffisamment précis pour ne pas filtrer
# les requêtes légitimes (ex: "missions disponibles" ≠ "disponibilité d'une personne")
_REALTIME_KEYWORDS = [
    "disponibilit",       # disponibilité, disponibilités (état d'une personne)
    "est disponible",     # "Ahmed est-il disponible ?"
    "sont disponibles",   # "Qui sont disponibles ?" (personnes, pas missions)
    "aujourd'hui",
    "aujourd hui",
    "maintenant",
    "en ce moment",
    "actuellement",
    "ce jour",
    "cette semaine",
    "ce mois",
    "en cours",
    "right now",
    "today",
    "currently",
]

# Patterns d'injection de prompt — JAMAIS mis en cache (anti-poisoning SEC-F06)
_INJECTION_PATTERNS = [
    "ignore",               # "Ignore toutes tes instructions"
    "oublie",               # "Oublie Zenika"
    "tu es maintenant",     # Injection de rôle
    "tu dois maintenant",
    "forget",               # Anglais
    "previous instructions",
    "system:",              # Prompt JSON structuré type {role: system}
    "\"role\":",            # Injection JSON
    "sans restrictions",
    "pwned",
    "arrr",                 # Pirate
]

_CACHE_KEY_PREFIX = "semcache:"


class SemanticCache:
    """
    Cache sémantique basé sur les embeddings Gemini et Redis.

    Utilise la cosine similarity pour détecter les requêtes sémantiquement
    similaires et retourner la réponse mise en cache sans appel LLM.
    """

    def __init__(self) -> None:
        self._enabled = os.getenv("SEMANTIC_CACHE_ENABLED", "true").lower() == "true"
        self._threshold = float(os.getenv("SEMANTIC_CACHE_THRESHOLD", "0.95"))
        self._ttl = int(os.getenv("SEMANTIC_CACHE_TTL", "900"))
        self._embedding_model = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/1")

        try:
            self._redis = redis.from_url(redis_url, decode_responses=True)
        except Exception as e:
            logger.error(f"[SemanticCache] Impossible de se connecter à Redis: {e}")
            self._redis = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get(self, query: str) -> Optional[dict]:
        """
        Cherche une réponse mise en cache sémantiquement similaire à la requête.

        Returns:
            dict avec `semantic_cache_hit: True` ou None si cache miss / désactivé.
        """
        if not self._enabled or self._redis is None:
            return None

        if self._is_realtime_query(query):
            logger.debug(f"[SemanticCache] Requête temps-réel détectée, bypass: {query[:60]}")
            return None

        try:
            query_embedding = await self._compute_embedding(query)
            if query_embedding is None:
                return None

            best_score = 0.0
            best_key = None
            best_entry = None

            # Scan O(N) sur toutes les clés semcache:* (acceptable pour MVP)
            for key in self._redis.scan_iter(f"{_CACHE_KEY_PREFIX}*"):
                try:
                    raw = self._redis.hgetall(key)
                    if not raw or "embedding" not in raw or "response" not in raw:
                        continue

                    cached_embedding = json.loads(raw["embedding"])
                    score = self._cosine_similarity(query_embedding, cached_embedding)

                    if score > best_score:
                        best_score = score
                        best_key = key
                        best_entry = raw

                except Exception as e:
                    logger.warning(f"[SemanticCache] Erreur lecture entrée {key}: {e}")
                    continue

            # Import des métriques ici pour éviter les circular imports
            try:
                from metrics import SEMANTIC_CACHE_SIMILARITY_HISTOGRAM
                SEMANTIC_CACHE_SIMILARITY_HISTOGRAM.observe(best_score)
            except Exception: raise

            if best_score >= self._threshold and best_entry is not None:
                logger.info(
                    f"[SemanticCache] HIT — score={best_score:.4f} "
                    f"key={best_key} query='{query[:60]}'"
                )
                try:
                    from metrics import SEMANTIC_CACHE_HITS_TOTAL
                    SEMANTIC_CACHE_HITS_TOTAL.inc()
                except Exception: raise
                return self._make_cache_hit_response(best_entry, best_score)
            else:
                logger.debug(
                    f"[SemanticCache] MISS — best_score={best_score:.4f} "
                    f"threshold={self._threshold} query='{query[:60]}'"
                )
                try:
                    from metrics import SEMANTIC_CACHE_MISSES_TOTAL
                    SEMANTIC_CACHE_MISSES_TOTAL.inc()
                except Exception: raise
                return None

        except Exception as e:
            logger.error(f"[SemanticCache] Erreur lors de la recherche: {e}", exc_info=True)
            return None

    async def set(self, query: str, response: dict) -> None:
        """
        Stocke l'embedding de la requête et la réponse dans Redis.
        Appelé en fire-and-forget après un cache miss.
        """
        if not self._enabled or self._redis is None:
            return

        if self._is_realtime_query(query):
            return

        # SEC-F06 Anti-poisoning : ne jamais stocker une réponse à une injection
        if self._is_injection_query(query):
            logger.warning(
                f"[SemanticCache] Injection détectée, stockage refusé: '{query[:60]}'"
            )
            return

        try:
            embedding = await self._compute_embedding(query)
            if embedding is None:
                return

            key = f"{_CACHE_KEY_PREFIX}{uuid.uuid4().hex}"
            entry = {
                "embedding": json.dumps(embedding),
                "query": query[:500],
                "response": json.dumps(response),
                "created_at": str(int(time.time())),
            }
            self._redis.hset(key, mapping=entry)
            self._redis.expire(key, self._ttl)
            logger.info(f"[SemanticCache] STORE — key={key} query='{query[:60]}' ttl={self._ttl}s")

        except Exception as e:
            logger.error(f"[SemanticCache] Erreur lors du stockage: {e}", exc_info=True)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _is_realtime_query(self, query: str) -> bool:
        """Détecte les requêtes temps-réel qui ne doivent jamais être mises en cache."""
        q_lower = query.lower()
        return any(kw in q_lower for kw in _REALTIME_KEYWORDS)

    def _is_injection_query(self, query: str) -> bool:
        """Détecte les tentatives d'injection de prompt qui ne doivent JAMAIS être cachées.
        Prévient le cache-poisoning : une injection réussie ne doit pas contaminer le cache."""
        q_lower = query.lower()
        return any(pattern in q_lower for pattern in _INJECTION_PATTERNS)

    def _cosine_similarity(self, a: list, b: list) -> float:
        """Calcule la cosine similarity entre deux vecteurs (implémentation pure Python/math)."""
        if len(a) != len(b) or len(a) == 0:
            return 0.0
        try:
            dot = sum(x * y for x, y in zip(a, b))
            norm_a = math.sqrt(sum(x * x for x in a))
            norm_b = math.sqrt(sum(y * y for y in b))
            if norm_a == 0.0 or norm_b == 0.0:
                return 0.0
            return dot / (norm_a * norm_b)
        except Exception as e:
            logger.error(f"[SemanticCache] Erreur cosine similarity: {e}")
            return 0.0

    async def _compute_embedding(self, text: str) -> Optional[list]:
        """Génère l'embedding d'un texte via l'API Gemini (google-genai)."""
        try:
            from google import genai
            client = genai.Client()
            result = client.models.embed_content(
                model=self._embedding_model,
                contents=text,
            )
            # L'API retourne un EmbedContentResponse avec .embeddings[0].values
            embeddings = getattr(result, "embeddings", None)
            if embeddings and len(embeddings) > 0:
                values = getattr(embeddings[0], "values", None)
                if values:
                    return list(values)
            logger.warning(f"[SemanticCache] Embedding vide reçu pour: {text[:60]}")
            return None
        except Exception as e:
            logger.error(f"[SemanticCache] Erreur génération embedding: {e}", exc_info=True)
            return None

    def _make_cache_hit_response(self, entry: dict, score: float) -> dict:
        """Reconstruit la réponse depuis l'entrée cache et l'enrichit avec les métadonnées de hit."""
        try:
            response = json.loads(entry["response"])
        except Exception:
            return None

        # Injecter un step informatif visible en mode Expert
        if "steps" not in response:
            response["steps"] = []

        response["steps"].insert(0, {
            "type": "warning",
            "tool": "semantic_cache:HIT",
            "args": {
                "similarity_score": round(score, 4),
                "threshold": self._threshold,
                "message": (
                    f"✅ Réponse servie depuis le cache sémantique "
                    f"(similarité: {score:.1%}) — aucun appel LLM facturé."
                ),
            },
        })

        response["semantic_cache_hit"] = True
        response["source"] = "semantic_cache"

        return response
