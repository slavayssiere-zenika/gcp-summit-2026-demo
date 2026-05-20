import asyncio

from src.cvs.routers.taxonomy_router import tree_task_manager
import json


async def main():
    state = await tree_task_manager.get_latest_status()
    print(json.dumps(state, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(main())
