import asyncio
import redis.asyncio as aioredis
import os

async def check():
    redis_url = "redis://172.31.48.3:6379"
    for db in range(16):
        r = aioredis.from_url(f"{redis_url}/{db}")
        try:
            res = await r.execute_command("FT.INFO", "idx:semcache")
            print(f"Found in DB {db}")
        except Exception as e:
            pass
        finally:
            await r.close()

asyncio.run(check())
