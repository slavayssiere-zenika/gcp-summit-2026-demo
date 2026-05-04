import asyncio
import sys

from database import get_db, init_db_connector
from sqlalchemy.future import select
from src.cvs.models import CVProfile

sys.path.append("/Users/sebastien.lavayssiere/Code/test-open-code/cv_api")



async def main():
    await init_db_connector()
    try:
        async for db_session in get_db():
            profiles = (await db_session.execute(select(CVProfile))).scalars().all()
            print(f"Profiles: {len(profiles)}")
            for p in profiles:
                print(f"Keywords: {p.competencies_keywords}")
                break
            break
    except Exception as e:
        print(f"ERROR: {e}")

asyncio.run(main())
