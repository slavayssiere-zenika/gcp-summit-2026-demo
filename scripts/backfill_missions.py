
import asyncio
import os
import httpx
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select

# This script moves missions from CV Profiles (cv_api) to Items (items_api)
# Run with: python scripts/backfill_missions.py

CV_DB_URL = os.getenv("CV_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/cv_db")
ITEMS_API_URL = os.getenv("ITEMS_API_URL", "http://localhost:8000")
AUTH_TOKEN = os.getenv("ADMIN_TOKEN") # Needs a valid admin JWT if running locally

async def migrate():
    engine = create_async_engine(CV_DB_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"} if AUTH_TOKEN else {}
    
    async with async_session() as db:
        # 1. Fetch all profiles with missions
        from sqlalchemy import text
        result = await db.execute(text("SELECT id, user_id, missions FROM cv_profiles WHERE missions IS NOT NULL AND missions != '[]'"))
        rows = result.all()
        
        print(f"Found {len(rows)} profiles with missions to migrate.")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # 2. Get/Create Categories
            m_res = await client.post(f"{ITEMS_API_URL.rstrip('/')}/categories", json={"name": "Missions", "description": "Migrated from CVs"}, headers=headers)
            mission_cat_id = m_res.json().get("id") if m_res.status_code < 400 else None
            
            s_res = await client.post(f"{ITEMS_API_URL.rstrip('/')}/categories", json={"name": "Restricted", "description": "Confidential missions"}, headers=headers)
            sensitive_cat_id = s_res.json().get("id") if s_res.status_code < 400 else None
            
            for row in rows:
                profile_id, user_id, missions = row
                if not isinstance(missions, list): continue
                
                print(f"Processing Profile {profile_id} (User {user_id})...")
                for m in missions:
                    is_sensitive = m.get("is_sensitive", False)
                    cat_ids = [mission_cat_id] if mission_cat_id else []
                    if is_sensitive and sensitive_cat_id:
                        cat_ids.append(sensitive_cat_id)
                        
                    item_data = {
                        "name": m.get("title", "Untitled Mission"),
                        "description": m.get("description", ""),
                        "user_id": user_id,
                        "category_ids": cat_ids,
                        "metadata_json": {
                            "company": m.get("company"),
                            "competencies": m.get("competencies", []),
                            "is_sensitive": is_sensitive,
                            "source": "Migration"
                        }
                    }
                    res = await client.post(f"{ITEMS_API_URL.rstrip('/')}/", json=item_data, headers=headers)
                    if res.status_code >= 400:
                        print(f"  Error creating mission '{m.get('title')}': {res.text}")
                
                # 3. Clear missions in DB
                await db.execute(text("UPDATE cv_profiles SET missions = NULL WHERE id = :id"), {"id": profile_id})
        
        await db.commit()
    print("Migration complete.")

if __name__ == "__main__":
    asyncio.run(migrate())
