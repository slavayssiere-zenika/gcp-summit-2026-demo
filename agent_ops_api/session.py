import os
import pickle
import redis
import logging
from google.adk.runners import InMemorySessionService

logger = logging.getLogger(__name__)

class RedisSessionService(InMemorySessionService):
    def __init__(self):
        super().__init__()
        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/1")
        self.r = redis.from_url(redis_url)
        # 1 Month TTL requested by user
        self.ttl = 30 * 24 * 60 * 60

    def _save_all(self, session_id: str):
        if not session_id:
            return
        try:
            dump = pickle.dumps({
                "s": self.sessions,
                "u": self.user_state,
                "a": self.app_state
            })
            self.r.set(f"adk:sessions:{session_id}", dump, ex=self.ttl)
        except Exception as e:
            logger.error(f"Redis memory save fail: {e}")

    def _load_all(self, session_id: str):
        if not session_id:
            return
        try:
            raw = self.r.get(f"adk:sessions:{session_id}")
            if raw:
                d = pickle.loads(raw)
                self.sessions = d.get("s", {})
                self.user_state = d.get("u", {})
                self.app_state = d.get("a", {})
        except Exception as e:
            logger.error(f"Redis memory load fail: {e}")

    def _get_session_impl(self, **kwargs):
        session_id = kwargs.get("session_id")
        self._load_all(session_id)
        return super()._get_session_impl(**kwargs)

    def _create_session_impl(self, **kwargs):
        session_id = kwargs.get("session_id")
        self._load_all(session_id)
        session = super()._create_session_impl(**kwargs)
        self._save_all(session_id)
        return session
        
    async def append_event(self, session, event):
        self._load_all(session.id)
        res = await super().append_event(session, event)
        self._save_all(session.id)
        return res
        
    def _delete_session_impl(self, **kwargs):
        session_id = kwargs.get("session_id")
        self._load_all(session_id)
        super()._delete_session_impl(**kwargs)
        self._save_all(session_id)
