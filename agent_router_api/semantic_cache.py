"""
SEC-F06 — Semantic Cache LLM (v2 — Redis HNSW)
Module de cache sémantique pour intercepter les requêtes sémantiquement
similaires avant l'appel Gemini, générant une économie FinOps significative.

Architecture :
  1. Génération de l'embedding de la requête via gemini-embedding-001
  2. Recherche par cosine similarity via HNSW index Redis (FT.SEARCH)
  3. Si score >= seuil : retour immédiat + log BQ avec action="semantic_cache_hit"
  4. Sinon : appel LLM normal + stockage en cache (fire-and-forget)

Upgrade v2 :
  - Migration O(N) scan → O(log N) HNSW via redis.commands.search (RediSearch module)
  - Redis 7.2 requis sur Memorystore (redis_version = "REDIS_7_2" dans redis.tf)
  - Embedding async via asyncio.get_event_loop().run_in_executor pour ne pas bloquer
  - redis.asyncio utilisé pour tous les appels Redis (compatibilité asyncio native)

Paramètres configurables (env vars) :
  SEMANTIC_CACHE_ENABLED    : "true"/"false" (défaut: true)
  SEMANTIC_CACHE_THRESHOLD  : float 0.0-1.0 (défaut: 0.95)
  SEMANTIC_CACHE_TTL        : int secondes  (défaut: 900 = 15 min)
  GEMINI_EMBEDDING_MODEL    : str           (défaut: gemini-embedding-001)
  REDIS_URL                 : str           (défaut: redis://redis:6379/2)
"""

import asyncio
import json
import logging
import math
import os
import time
import uuid
from typing import Optional

import redis.asyncio as aioredis

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
_HNSW_INDEX_NAME = "idx:semcache"
_EMBEDDING_DIM = 768  # gemini-embedding-001 dimension


class SemanticCache:
    """
    Cache sémantique basé sur les embeddings Gemini et Redis HNSW.

    Utilise RediSearch (disponible sur Memorystore Redis 7.2+) avec un index
    HNSW pour une recherche en O(log N) au lieu du scan O(N) de la v1.
    Compatible redis.asyncio pour ne pas bloquer la boucle d'événements FastAPI.
    """

    def __init__(self) -> None:
        self._enabled = os.getenv("SEMANTIC_CACHE_ENABLED", "true").lower() == "true"
        self._threshold = float(os.getenv("SEMANTIC_CACHE_THRESHOLD", "0.95"))
        self._ttl = int(os.getenv("SEMANTIC_CACHE_TTL", "900"))
        self._embedding_model = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/2")

        self._redis: Optional[aioredis.Redis] = None
        self._redis_url = redis_url
        self._hnsw_ready = False

    # ------------------------------------------------------------------
    # Lazy init : connexion Redis async + création de l'index HNSW
    # ------------------------------------------------------------------

    async def _ensure_connected(self) -> bool:
        """Crée la connexion Redis async et l'index HNSW si nécessaire."""
        if self._redis is not None and self._hnsw_ready:
            return True

        try:
            if self._redis is None:
                self._redis = await aioredis.from_url(
                    self._redis_url, decode_responses=False
                )
            await self._ensure_hnsw_index()
            return True
        except Exception as e:
            logger.error(f"[SemanticCache] Connexion Redis échouée: {e}")
            self._redis = None
            return False

    async def _ensure_hnsw_index(self) -> None:
        """Crée l'index HNSW via FT.CREATE si absent. Idempotent."""
        if self._hnsw_ready:
            return
        try:
            # Vérifie si l'index existe déjà
            await self._redis.execute_command("FT.INFO", _HNSW_INDEX_NAME)
            self._hnsw_ready = True
            logger.info(f"[SemanticCache] Index HNSW '{_HNSW_INDEX_NAME}' trouvé.")
        except Exception:
            # Index absent → création
            # GCP Memorystore ne supporte pas TEXT (nécessite le module RediSearch complet).
            # On essaie d'abord avec TEXT (Redis Stack), puis fallback sur TAG (Memorystore).
            try:
                await self._redis.execute_command(
                    "FT.CREATE", _HNSW_INDEX_NAME,
                    "ON", "HASH",
                    "PREFIX", "1", _CACHE_KEY_PREFIX,
                    "SCHEMA",
                    "embedding", "VECTOR", "HNSW", "6",
                    "TYPE", "FLOAT32",
                    "DIM", str(_EMBEDDING_DIM),
                    "DISTANCE_METRIC", "COSINE",
                    "response", "TAG",
                    "query_text", "TAG",
                )
                self._hnsw_ready = True
                logger.info(f"[SemanticCache] Index HNSW '{_HNSW_INDEX_NAME}' créé (TAG — compatible Memorystore).")
            except Exception as e:
                logger.error(f"[SemanticCache] Impossible de créer l'index HNSW: {e}")
                # Fallback : on désactive le cache pour cette instance
                self._hnsw_ready = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get(self, query: str) -> Optional[dict]:
        """
        Cherche une réponse mise en cache sémantiquement similaire à la requête.

        Returns:
            dict avec `semantic_cache_hit: True` ou None si cache miss / désactivé.
        """
        if not self._enabled:
            return None

        if self._is_realtime_query(query):
            logger.debug(f"[SemanticCache] Requête temps-réel détectée, bypass: {query[:60]}")
            return None

        if not await self._ensure_connected():
            return None

        try:
            query_embedding = await self._compute_embedding_async(query)
            if query_embedding is None:
                return None

            # Recherche HNSW via FT.SEARCH — O(log N) vs O(N) pour le scan
            import struct
            embedding_bytes = struct.pack(f"{_EMBEDDING_DIM}f", *query_embedding[:_EMBEDDING_DIM])

            results = await self._redis.execute_command(
                "FT.SEARCH", _HNSW_INDEX_NAME,
                f"*=>[KNN 1 @embedding $vec AS score]",
                "PARAMS", "2", "vec", embedding_bytes,
                "RETURN", "3", "score", "response", "query_text",
                "SORTBY", "score", "ASC",
                "LIMIT", "0", "1",
                "DIALECT", "2",
            )

            if not results or results[0] == 0:
                try:
                    from metrics import SEMANTIC_CACHE_MISSES_TOTAL
                    SEMANTIC_CACHE_MISSES_TOTAL.inc()
                except Exception:
                    raise
                return None

            # Résultats : [count, key, [field, value, ...]]
            raw_fields = results[2] if len(results) > 2 else []
            field_map = {}
            for i in range(0, len(raw_fields) - 1, 2):
                k = raw_fields[i].decode() if isinstance(raw_fields[i], bytes) else raw_fields[i]
                v = raw_fields[i + 1].decode() if isinstance(raw_fields[i + 1], bytes) else raw_fields[i + 1]
                field_map[k] = v

            raw_score = field_map.get("score", "1.0")
            # HNSW cosine distance : 0 = identique, 2 = opposé → similarity = 1 - distance
            distance = float(raw_score)
            score = max(0.0, 1.0 - distance)

            # Import des métriques ici pour éviter les circular imports
            try:
                from metrics import SEMANTIC_CACHE_SIMILARITY_HISTOGRAM
                SEMANTIC_CACHE_SIMILARITY_HISTOGRAM.observe(score)
            except Exception:
                raise

            if score >= self._threshold and "response" in field_map:
                logger.info(
                    f"[SemanticCache] HIT — score={score:.4f} "
                    f"query='{query[:60]}'"
                )
                try:
                    from metrics import SEMANTIC_CACHE_HITS_TOTAL
                    SEMANTIC_CACHE_HITS_TOTAL.inc()
                except Exception:
                    raise
                return self._make_cache_hit_response(field_map["response"], score)
            else:
                logger.debug(
                    f"[SemanticCache] MISS — score={score:.4f} "
                    f"threshold={self._threshold} query='{query[:60]}'"
                )
                try:
                    from metrics import SEMANTIC_CACHE_MISSES_TOTAL
                    SEMANTIC_CACHE_MISSES_TOTAL.inc()
                except Exception:
                    raise
                return None

        except Exception as e:
            logger.error(f"[SemanticCache] Erreur lors de la recherche HNSW: {e}", exc_info=True)
            return None

    async def set(self, query: str, response: dict) -> None:
        """
        Stocke l'embedding de la requête et la réponse dans Redis.
        Appelé en fire-and-forget après un cache miss.
        """
        if not self._enabled:
            return

        if self._is_realtime_query(query):
            return

        # SEC-F06 Anti-poisoning : ne jamais stocker une réponse à une injection
        if self._is_injection_query(query):
            logger.warning(
                f"[SemanticCache] Injection détectée, stockage refusé: '{query[:60]}'"
            )
            return

        if not await self._ensure_connected():
            return

        try:
            embedding = await self._compute_embedding_async(query)
            if embedding is None:
                return

            import struct
            embedding_bytes = struct.pack(f"{_EMBEDDING_DIM}f", *embedding[:_EMBEDDING_DIM])

            key = f"{_CACHE_KEY_PREFIX}{uuid.uuid4().hex}"
            # HSET avec les champs requis par l'index HNSW
            await self._redis.hset(key, mapping={
                "embedding": embedding_bytes,
                "query_text": query[:500],
                "response": json.dumps(response),
                "created_at": str(int(time.time())),
            })
            await self._redis.expire(key, self._ttl)
            logger.info(f"[SemanticCache] STORE HNSW — key={key} query='{query[:60]}' ttl={self._ttl}s")

        except Exception as e:
            logger.error(f"[SemanticCache] Erreur lors du stockage HNSW: {e}", exc_info=True)

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

    async def _compute_embedding_async(self, text: str) -> Optional[list]:
        """Génère l'embedding d'un texte via l'API Gemini de façon async.
        Utilise run_in_executor pour ne pas bloquer la boucle d'événements FastAPI."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._compute_embedding_sync, text)

    def _compute_embedding_sync(self, text: str) -> Optional[list]:
        """Appel synchrone à l'API Gemini Embedding — exécuté dans un thread pool."""
        try:
            from google import genai
            client = genai.Client()
            result = client.models.embed_content(
                model=self._embedding_model,
                contents=text,
            )
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

    def _make_cache_hit_response(self, response_json: str, score: float) -> Optional[dict]:
        """Reconstruit la réponse depuis l'entrée cache et l'enrichit avec les métadonnées de hit."""
        try:
            response = json.loads(response_json)
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
                    f"✅ Réponse servie depuis le cache sémantique HNSW "
                    f"(similarité: {score:.1%}) — aucun appel LLM facturé."
                ),
            },
        })

        response["semantic_cache_hit"] = True
        response["source"] = "semantic_cache"

        return response
