import redis
import os

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/6")

redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

def get_redis():
    return redis_client
