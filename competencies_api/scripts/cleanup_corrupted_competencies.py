import asyncio
import ast
import json
import os
import sys

# Add the parent directory to sys.path to import from database and src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database import init_db_connector, get_db, close_db_connector
from src.competencies.models import Competency
from sqlalchemy.future import select

async def cleanup():
    print("Starting database cleanup for corrupted competencies...")
    await init_db_connector()
    
    async for db in get_db():
        # Find competencies whose name looks like a dictionary or JSON
        stmt = select(Competency).filter(Competency.name.like("%{%name%}%"))
        result = await db.execute(stmt)
        competencies = result.scalars().all()
        
        print(f"Found {len(competencies)} potentially corrupted competencies.")
        
        updated_count = 0
        merged_count = 0
        
        from sqlalchemy import update, delete
        from src.competencies.models import user_competency
        
        for comp in competencies:
            data = None
            try:
                # Try to parse the name as a dictionary
                data = ast.literal_eval(comp.name) if '{' in comp.name else None
            except:
                try:
                    data = json.loads(comp.name)
                except:
                    pass
            
            if isinstance(data, dict):
                new_name = data.get("name")
                new_desc = data.get("description")
                
                if new_name:
                    new_name = str(new_name)
                    # Check if a competency with this name already exists
                    existing = (await db.execute(select(Competency).filter(Competency.name.ilike(new_name)))).scalars().first()
                    
                    if existing and existing.id != comp.id:
                        print(f"Merging duplicate competency ID {comp.id} into existing ID {existing.id} ('{new_name}')")
                        
                        # 1. Update user associations that won't clash
                        # We delete relations that exist in both to avoid primary key violations on update
                        await db.execute(
                            delete(user_competency)
                            .where(user_competency.c.competency_id == comp.id)
                            .where(user_competency.c.user_id.in_(
                                select(user_competency.c.user_id).where(user_competency.c.competency_id == existing.id)
                            ))
                        )
                        
                        # 2. Transfer remaining associations
                        await db.execute(
                            update(user_competency)
                            .where(user_competency.c.competency_id == comp.id)
                            .values(competency_id=existing.id)
                        )
                        
                        # 3. Delete the corrupted one
                        await db.delete(comp)
                        merged_count += 1
                    else:
                        print(f"Fixing competency ID {comp.id}: '{comp.name}' -> '{new_name}'")
                        comp.name = new_name
                        if new_desc:
                            comp.description = str(new_desc)
                        updated_count += 1
            else:
                print(f"Could not parse name for competency ID {comp.id}: {comp.name}")
                
        if updated_count > 0 or merged_count > 0:
            await db.commit()
            print(f"Cleanup summary: {updated_count} updated, {merged_count} merged/deleted.")
        else:
            print("No competencies were updated or merged.")
            
        break # Exit after one session

    await close_db_connector()
    print("Cleanup finished.")

if __name__ == "__main__":
    asyncio.run(cleanup())
