from agent_router_api.tests.test_semantic_cache import *
import asyncio

async def run():
    cache = make_cache()
    sample_response = {"response": "Answer"}
    cache._redis.execute_command = AsyncMock(return_value=[
        1, "semcache:bbb", ["score", "0.0", "response", json.dumps(sample_response)]
    ])
    
    with patch.object(cache, "_compute_embedding_async", new=AsyncMock(return_value=[0]*768)):
        result = await cache.get("Quelles sont les missions disponibles ?")
    
    print("RESULT:", result)

asyncio.run(run())
