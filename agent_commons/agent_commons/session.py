"""
session.py — Redis-backed ADK session service shared across all agents.

Extracted and generalised from agent_hr_api/session.py,
agent_ops_api/session.py, and agent_missions_api/session.py.

The key difference between the original files was the Redis key prefix
(``adk:sessions:`` vs ``adk:missions:sessions:``).
This is now configurable via the ``redis_key_prefix`` constructor argument.
"""

import logging
import os
import pickle

import redis
from google.adk.runners import InMemorySessionService

logger = logging.getLogger(__name__)

# Default Redis key prefixes per agent namespace
_PREFIX_DEFAULT = "adk:sessions"


class RedisSessionService(InMemorySessionService):
    """InMemorySessionService backed by Redis for cross-process persistence.

    Args:
        redis_url:        Redis connection string (defaults to REDIS_URL env var
                          or ``redis://redis:6379/1``).
        redis_key_prefix: Prefix used for Redis keys (e.g. ``adk:sessions`` or
                          ``adk:missions:sessions``).  Allows multiple agents to
                          share the same Redis instance without key collisions.
        ttl_seconds:      Key TTL in seconds (default: 30 days).
    """

    def __init__(
        self,
        redis_url: str | None = None,
        redis_key_prefix: str = _PREFIX_DEFAULT,
        ttl_seconds: int = 30 * 24 * 60 * 60,
    ) -> None:
        super().__init__()
        _redis_url = redis_url or os.getenv("REDIS_URL", "redis://redis:6379/1")
        self.r = redis.from_url(_redis_url)
        self._prefix = redis_key_prefix
        self.ttl = ttl_seconds

    def _key(self, session_id: str) -> str:
        return f"{self._prefix}:{session_id}"

    def _save_all(self, session_id: str) -> None:
        if not session_id:
            return
        try:
            dump = pickle.dumps({
                "s": self.sessions,
                "u": self.user_state,
                "a": self.app_state,
            })
            self.r.set(self._key(session_id), dump, ex=self.ttl)
        except Exception as e:
            logger.error("Redis session save fail [%s]: %s", session_id, e)

    def _load_all(self, session_id: str) -> None:
        if not session_id:
            return
        try:
            raw = self.r.get(self._key(session_id))
            if raw:
                d = pickle.loads(raw)
                self.sessions = d.get("s", {})
                self.user_state = d.get("u", {})
                self.app_state = d.get("a", {})
        except Exception as e:
            logger.error("Redis session load fail [%s]: %s", session_id, e)

    def _get_session_impl(self, **kwargs):
        self._load_all(kwargs.get("session_id"))
        return super()._get_session_impl(**kwargs)

    def _create_session_impl(self, **kwargs):
        self._load_all(kwargs.get("session_id"))
        session = super()._create_session_impl(**kwargs)
        self._save_all(kwargs.get("session_id"))
        return session

    async def append_event(self, session, event):
        self._load_all(session.id)
        res = await super().append_event(session, event)
        self._save_all(session.id)
        return res

    def _delete_session_impl(self, **kwargs):
        self._load_all(kwargs.get("session_id"))
        super()._delete_session_impl(**kwargs)
        self._save_all(kwargs.get("session_id"))


# ─────────────────────────────────────────────────────────────────────────────
# HR Candidates Pool — mémoire de session pour l'agent HR
# ─────────────────────────────────────────────────────────────────────────────
# Permet de mémoriser les candidats trouvés lors d'une recherche initiale pour
# que les questions de suivi ("parmi ceux-là, qui...") n'exigent pas un nouvel
# appel RAG. TTL 1h — stocké dans le namespace hr:candidates:{session_id}.

import json as _json

HR_CANDIDATES_POOL_TTL = int(os.getenv("HR_CANDIDATES_POOL_TTL", "3600"))  # 1h par défaut


def store_hr_candidates_pool(r: redis.Redis, session_id: str, candidates: list) -> None:
    """Persiste le pool de candidats identifiés durant la session HR courante.

    Args:
        r:          Client Redis (synchrone, identique à RedisSessionService.r).
        session_id: ID de session ADK courant.
        candidates: Liste de dicts {user_id, similarity_score, full_name, ...}.
    """
    try:
        key = f"hr:candidates:{session_id}"
        r.set(key, _json.dumps(candidates), ex=HR_CANDIDATES_POOL_TTL)
        logger.debug("HR candidates pool stored for session %s (%d entries)", session_id, len(candidates))
    except Exception as e:
        logger.error("HR candidates pool store fail [%s]: %s", session_id, e)


def get_hr_candidates_pool(r: redis.Redis, session_id: str) -> list:
    """Récupère le pool de candidats mémorisé pour la session HR courante.

    Returns:
        Liste de candidats (vide si rien en cache ou erreur Redis).
    """
    try:
        key = f"hr:candidates:{session_id}"
        raw = r.get(key)
        if raw:
            return _json.loads(raw)
        return []
    except Exception as e:
        logger.error("HR candidates pool load fail [%s]: %s", session_id, e)
        return []


def clear_hr_candidates_pool(r: redis.Redis, session_id: str) -> None:
    """Invalide explicitement le pool de candidats (ex: après une requête hors-contexte)."""
    try:
        r.delete(f"hr:candidates:{session_id}")
    except Exception as e:
        logger.error("HR candidates pool clear fail [%s]: %s", session_id, e)
