import redis
import json
from typing import Optional, Any
import os
from opentelemetry import trace

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/3")

client = redis.from_url(REDIS_URL, decode_responses=True)
tracer = trace.get_tracer(__name__)


def get_cache(key: str) -> Optional[Any]:
    with tracer.start_as_current_span(f"cache.get", attributes={"cache.key": key}) as span:
        data = client.get(key)
        if data:
            try:
                span.set_attribute("cache.hit", True)
                return json.loads(data)
            except:
                return data
        span.set_attribute("cache.hit", False)
        return None


def set_cache(key: str, value: Any, expire: int = 60):
    with tracer.start_as_current_span(f"cache.set", attributes={"cache.key": key, "cache.ttl": expire}) as span:
        client.setex(key, expire, json.dumps(value, default=str))
        span.set_attribute("cache.operation", "setex")


def delete_cache(key: str):
    with tracer.start_as_current_span(f"cache.delete", attributes={"cache.key": key}) as span:
        client.delete(key)


def delete_cache_pattern(pattern: str):
    with tracer.start_as_current_span(f"cache.delete_pattern", attributes={"cache.pattern": pattern}) as span:
        deleted = 0
        for key in client.scan_iter(pattern):
            client.delete(key)
            deleted += 1
        span.set_attribute("cache.deleted_count", deleted)
