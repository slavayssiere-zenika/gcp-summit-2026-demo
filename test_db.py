import sys
import os
sys.path.insert(0, os.path.abspath("cv_api"))

import asyncio
from src.database import SessionLocal
from src.cvs.models import CVProfile
from sqlalchemy import select

async def main():
    async with SessionLocal() as db:
        profiles = (await db.execute(select(CVProfile).filter(CVProfile.user_id == 2))).scalars().all()
        for p in profiles:
            print(f"Profile {p.id}:")
            print("Missions:", p.missions)

asyncio.run(main())
