import asyncio
import os
import sys

# Ajouter le dossier de l'API au path pour importer la config DB
sys.path.append("/Users/sebastien.lavayssiere/Code/test-open-code/drive_api")
os.environ["DATABASE_URL"] = "postgresql+asyncpg://postgres:postgres@localhost:5432/drive" # fallback dev local url si nécessaire

from database import engine
from sqlalchemy import text

async def check():
    async with engine.begin() as conn:
        res = await conn.execute(text("SELECT status, count(*) FROM drive_sync_state GROUP BY status"))
        print("--- drive_sync_state stats ---")
        for row in res:
            print(f"{row[0]}: {row[1]}")

asyncio.run(check())
