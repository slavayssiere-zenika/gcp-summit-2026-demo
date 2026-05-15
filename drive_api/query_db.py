import asyncio
import os
import sys

from shared.database import get_db
from models import DriveFolder, DriveSyncState
from sqlalchemy.future import select

sys.path.insert(0, os.path.abspath('src'))


async def main():
    async for db in get_db():
        print("Sync States:")
        skip = 0
        limit = 100
        while True:
            stmt = select(DriveSyncState).offset(skip).limit(limit)
            res = await db.execute(stmt)
            states = res.scalars().all()
            if not states:
                break
            for s in states:
                print(f"File: {s.file_name}, Parent: {s.parent_folder_name}, Status: {s.status}")
            skip += limit
            
        print("Folders:")
        stmt = select(DriveFolder)
        res = await db.execute(stmt)
        folders = res.scalars().all()
        for f in folders:
            print(f"Folder: {f.folder_name}, Tag: {f.tag}, ID: {f.id}, Google ID: {f.google_folder_id}")
        break

asyncio.run(main())
