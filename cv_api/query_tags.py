import asyncio
import sys
sys.path.append('/Users/sebastien.lavayssiere/Code/test-open-code/cv_api')
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from src.cvs.models import CVProfile

async def main():
    engine = create_async_engine('postgresql+asyncpg://admin:zenika2026@localhost:5432/cv_api')
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as ds:
        res = (await ds.execute(select(CVProfile.source_tag).distinct())).scalars().all()
        print('Tags in DB:', res)

asyncio.run(main())
