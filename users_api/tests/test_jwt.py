import asyncio
import os
from httpx import AsyncClient
from jose import jwt

SECRET_KEY = os.getenv("SECRET_KEY", "test_secret")
token = jwt.encode({"sub": "testuser"}, SECRET_KEY, algorithm="HS256")
print(f"Token: {token}")

async def run():
    async with AsyncClient() as client:
        res = await client.get("http://localhost:8000/search", params={"query": "test"}, headers={"Authorization": f"Bearer {token}"})
        print(f"Direct to API: {res.status_code} {res.text}")

        res = await client.post("http://localhost:8000/mcp/call", json={"name": "search_users", "arguments": {"query": "test"}}, headers={"Authorization": f"Bearer {token}"})
        print(f"Via MCP Proxy: {res.status_code} {res.text}")

asyncio.run(run())
