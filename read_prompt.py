import httpx
import asyncio

async def test_prompt():
    async with httpx.AsyncClient() as client:
        # Assuming we need to bypass auth or just run the manage_env to see the db content
        pass

if __name__ == "__main__":
    pass
