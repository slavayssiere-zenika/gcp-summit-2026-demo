import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath('src'))
from database import get_db
from sqlalchemy.future import select
from models import DriveSyncState, DriveFolder

async def main():
    async for db in get_db():
        # Get a few sync states
        stmt = select(DriveSyncState).limit(10)
        res = await db.execute(stmt)
        states = res.scalars().all()
        for s in states:
            print(f"File: {s.file_name}, Parent: {s.parent_folder_name}, Status: {s.status}")
            
        print("Folders:")
        stmt = select(DriveFolder)
        res = await db.execute(stmt)
        folders = res.scalars().all()
        for f in folders:
            print(f"Folder: {f.folder_name}, Tag: {f.tag}, ID: {f.id}, Google ID: {f.google_folder_id}")
        break

asyncio.run(main())
