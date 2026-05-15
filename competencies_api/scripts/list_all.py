import asyncio
import os
import sys

from shared.database import get_db, init_db_connector
from sqlalchemy.future import select
from src.competencies.models import Competency

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


async def l():
    await init_db_connector()
    async for db in get_db():
        from sqlalchemy import func
        count = await db.execute(select(func.count(Competency.id)))
        print(f"TOTAL COUNT: {count.scalar()}")
        
        r = await db.execute(select(Competency.id, Competency.name, Competency.description))
        for x in r.fetchall():
            print(f"ID={x[0]} NAME={x[1]} DESC={x[2]}")
        break

if __name__ == "__main__":
    asyncio.run(l())
