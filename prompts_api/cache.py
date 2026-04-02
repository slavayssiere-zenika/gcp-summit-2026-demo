import os
import redis
import logging

redis_url = os.getenv("REDIS_URL", "redis://redis:6379/5")
redis_client = redis.from_url(redis_url, decode_responses=True)
logger = logging.getLogger(__name__)

async def get_cache(key: str):
    try:
        return redis_client.get(key)
    except Exception as e:
        logger.error(f"Redis cache GET error: {e}")
        return None

async def set_cache(key: str, value: str, ttl: int = 3600):
    try:
        redis_client.set(key, value, ex=ttl)
    except Exception as e:
        logger.error(f"Redis cache SET error: {e}")

async def delete_cache(key: str):
    try:
        redis_client.delete(key)
    except Exception as e:
        logger.error(f"Redis cache DELETE error: {e}")
