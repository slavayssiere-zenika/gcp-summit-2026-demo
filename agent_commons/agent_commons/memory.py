import json
import logging
import time
from typing import Mapping, Optional, Sequence

from google.adk.memory import BaseMemoryService
from google.adk.memory.memory_entry import MemoryEntry
from google.adk.memory.base_memory_service import SearchMemoryResponse
from google.adk.sessions import Session
from google.adk.events import Event
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

# Longueur max du texte conservé par message pour éviter des clés Redis trop volumineuses
_MAX_TEXT_LEN = 500


def _extract_text_from_event(event: Event) -> str:
    """Extrait le texte lisible d'un Event ADK (content.parts[].text)."""
    if not event.content or not event.content.parts:
        return ""
    texts = []
    for part in event.content.parts:
        if hasattr(part, "text") and part.text:
            texts.append(part.text.strip())
    return " ".join(texts)[:_MAX_TEXT_LEN]


class RedisMemoryService(BaseMemoryService):
    """
    Service de mémoire ADK basé sur Redis.

    Stocke les interactions passées par utilisateur et application.
    Chaque entrée conserve la question de l'utilisateur et la réponse finale
    de l'agent, afin que le LLM puisse s'appuyer sur l'historique inter-sessions.

    Isolation : clé Redis = memory:{app_name}:{user_id}
    Aucune donnée inter-utilisateur n'est jamais exposée (SEC-F01).
    """

    def __init__(
        self,
        redis_url: str,
        default_ttl_seconds: int = 86400,
        max_entries_per_user: int = 20,
    ):
        """
        Args:
            redis_url: URL de connexion Redis.
            default_ttl_seconds: Durée de vie par défaut (24h).
            max_entries_per_user: Nombre max de tours conservés par utilisateur (LRU).
        """
        self.redis = Redis.from_url(redis_url, decode_responses=True)
        self.default_ttl = default_ttl_seconds
        self.max_entries = max_entries_per_user

    def _get_key(self, app_name: str, user_id: str) -> str:
        """SEC-F01 : Isolation stricte par user_id — jamais de clé partagée entre users."""
        return f"memory:{app_name}:{user_id}"

    async def add_session_to_memory(self, session: Session) -> None:
        """Hook ADK appelé en fin de session — non utilisé ici (on passe par add_events_to_memory)."""
        pass

    async def add_events_to_memory(
        self,
        *,
        app_name: str,
        user_id: str,
        events: Sequence[Event],
        session_id: Optional[str] = None,
        custom_metadata: Optional[Mapping[str, object]] = None,
    ) -> None:
        """
        Stocke le contenu réel d'un tour de conversation dans Redis.

        Extrait la question de l'utilisateur (author == "user") et la réponse
        finale de l'agent (is_final_response() == True) pour constituer une entrée
        mémorisable et exploitable par le LLM lors de la prochaine session.
        """
        user_text = ""
        agent_text = ""

        for event in events:
            if event.author == "user" and not user_text:
                user_text = _extract_text_from_event(event)
            elif event.author != "user" and event.is_final_response() and not agent_text:
                agent_text = _extract_text_from_event(event)

        # On ne stocke pas les tours vides (ex: events purement techniques)
        if not user_text and not agent_text:
            logger.debug("[Memory] Tour vide ignoré (aucun texte extractible).")
            return

        entry = {
            "timestamp": time.time(),
            "session_id": session_id,
            "user": user_text,
            "agent": agent_text,
        }

        key = self._get_key(app_name, user_id)
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.lpush(key, json.dumps(entry, ensure_ascii=False))
            pipe.ltrim(key, 0, self.max_entries - 1)  # LRU : garde les N plus récents
            pipe.expire(key, self.default_ttl)
            await pipe.execute()

        logger.debug(
            "[Memory] Saved turn to %s (user=%d chars, agent=%d chars, TTL=%ds)",
            key, len(user_text), len(agent_text), self.default_ttl,
        )

    async def search_memory(
        self,
        *,
        app_name: str,
        user_id: str,
        query: str,
    ) -> SearchMemoryResponse:
        """
        Retourne les N derniers tours mémorisés pour cet utilisateur.

        Le LLM reçoit le contenu réel (question + réponse) et peut l'utiliser
        pour répondre à des questions faisant référence à des échanges passés
        (ex: "et pour la mission dont on parlait hier ?").

        Note : tri chronologique inverse (le plus récent en premier).
        """
        key = self._get_key(app_name, user_id)
        raw_entries = await self.redis.lrange(key, 0, -1)

        memories: list[MemoryEntry] = []
        for raw in raw_entries:
            try:
                data = json.loads(raw)
                user_q = data.get("user", "")
                agent_a = data.get("agent", "")
                ts = data.get("timestamp", 0)

                # Format lisible par le LLM injecté dans le contexte
                content_lines = []
                if user_q:
                    content_lines.append(f"User: {user_q}")
                if agent_a:
                    content_lines.append(f"Agent: {agent_a}")
                if not content_lines:
                    continue

                memories.append(MemoryEntry(
                    content="\n".join(content_lines),
                    metadata={
                        "timestamp": ts,
                        "session_id": data.get("session_id"),
                        "app_name": app_name,
                        "user_id": user_id,
                    },
                ))
            except Exception as exc:
                logger.warning("[Memory] Entrée corrompue ignorée : %s", exc)
                continue

        return SearchMemoryResponse(memories=memories)

    async def clear_memory(self, app_name: str, user_id: str) -> None:
        """Supprime toute la mémoire d'un utilisateur (RGPD / droit à l'oubli)."""
        key = self._get_key(app_name, user_id)
        await self.redis.delete(key)
        logger.info("[Memory] Mémoire effacée pour user_id=%s app=%s", user_id, app_name)
