import os
import sys

# Set DATABASE_URL before importing database module
if "DATABASE_URL" not in os.environ:
    # Assuming user is running postgres on localhost:5432 (mapped port)
    os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5432/competencies"

# Add project root to sys.path
sys.path.append("/Users/sebastien.lavayssiere/Code/test-open-code/competencies_api")

import asyncio
from database import init_db_connector, close_db_connector, engine
from src.competencies.models import Competency, user_competency
from sqlalchemy.future import select
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

async def run():
    try:
        await init_db_connector()
        
        async with AsyncSession(engine) as db:
            stmt = (
                select(
                    Competency.name,
                    func.count(user_competency.c.user_id).label("count")
                )
                .join(user_competency, Competency.id == user_competency.c.competency_id)
                .group_by(Competency.id, Competency.name)
                .order_by(func.count(user_competency.c.user_id).asc())
                .limit(10)
            )
            
            results = (await db.execute(stmt)).all()
            
            if not results:
                print("Aucune compétence n'est pour l'instant assignée à des utilisateurs.")
            else:
                print("--- COMPÉTENCES LES PLUS RARE ---")
                for name, count in results:
                    print(f"- {name}: {count} utilisateur(s)")

    finally:
        await close_db_connector()

if __name__ == "__main__":
    try:
        asyncio.run(run())
    except Exception as e:
        print(f"Erreur : {e}")
