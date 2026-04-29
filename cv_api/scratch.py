import sys
import asyncio
sys.path.append("/Users/sebastien.lavayssiere/Code/test-open-code/cv_api")

from database import init_db_connector, get_db
from src.cvs.models import CVProfile
from sqlalchemy.future import select

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
