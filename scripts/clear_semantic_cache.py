import os
import asyncio
import redis.asyncio as aioredis

async def clear_semantic_cache():
    # Semantic Cache is on DB 2
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/2")
    print(f"Connecting to Redis at {redis_url}...")
    r = aioredis.from_url(redis_url, decode_responses=True)
    
    cursor = 0
    pattern = "semcache:*"
    deleted_count = 0
    
    print(f"Scanning for keys matching '{pattern}'...")
    while True:
        cursor, keys = await r.scan(cursor=cursor, match=pattern, count=100)
        if keys:
            await r.delete(*keys)
            deleted_count += len(keys)
            print(f"Deleted {len(keys)} keys...")
        if cursor == 0:
            break
            
    print(f"Finished. Total deleted: {deleted_count}")
    await r.close()

if __name__ == "__main__":
    asyncio.run(clear_semantic_cache())
