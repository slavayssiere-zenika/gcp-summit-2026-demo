import json
import os
from typing import Any, Optional

import redis
from opentelemetry import trace

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/3")

_client: Optional[redis.Redis] = None
tracer = trace.get_tracer(__name__)


def get_client() -> redis.Redis:
    """Retourne le client Redis (lazy init pour permettre l'injection par les tests)."""
    global _client
    if _client is None:
        _client = redis.from_url(os.getenv("REDIS_URL", REDIS_URL), decode_responses=True)
    return _client


def reset_client():
    """Réinitialise le client Redis (utilisé par les fixtures Testcontainers)."""
    global _client
    _client = None


def get_cache(key: str) -> Optional[Any]:
    with tracer.start_as_current_span("cache.get", attributes={"cache.key": key}) as span:
        data = get_client().get(key)
        if data:
            try:
                span.set_attribute("cache.hit", True)
                return json.loads(data)
            except Exception:
                return data
        span.set_attribute("cache.hit", False)
        return None


def set_cache(key: str, value: Any, expire: int = 60):
    with tracer.start_as_current_span("cache.set", attributes={"cache.key": key, "cache.ttl": expire}) as span:
        get_client().setex(key, expire, json.dumps(value, default=str))
        span.set_attribute("cache.operation", "setex")


def delete_cache(key: str):
    with tracer.start_as_current_span("cache.delete", attributes={"cache.key": key}):
        get_client().delete(key)


def delete_cache_pattern(pattern: str):
    with tracer.start_as_current_span("cache.delete_pattern", attributes={"cache.pattern": pattern}) as span:
        c = get_client()
        deleted = 0
        for key in c.scan_iter(match=pattern):
            c.delete(key)
            deleted += 1
        span.set_attribute("cache.deleted_count", deleted)
