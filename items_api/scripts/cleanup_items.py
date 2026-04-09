import asyncio
import sys
import os
import ast
import json

# Add current directory to path to import database
sys.path.append(os.path.abspath('.'))

from database import init_db_connector, get_db
from sqlalchemy import text

async def cleanup():
    print("Checking items database for corrupted entries...")
    await init_db_connector()
    
    async for db in get_db():
        for table in ['categories', 'items']:
            stmt = text(f"SELECT id, name, description FROM {table} WHERE name LIKE '%{{%' OR description LIKE '%{{%'")
            result = await db.execute(stmt)
            rows = result.fetchall()
            
            print(f"Found {len(rows)} potentially corrupted rows in {table}.")
            
            for r in rows:
                data = None
                try:
                    data = ast.literal_eval(r[1])
                except:
                    try:
                        data = json.loads(r[1])
                    except:
                        pass
                
                if isinstance(data, dict):
                    new_name = data.get("name")
                    new_desc = data.get("description")
                    if new_name:
                        print(f"Fixing {table} ID {r[0]}: {r[1]} -> {new_name}")
                        await db.execute(text(f"UPDATE {table} SET name = :n, description = :d WHERE id = :i"), 
                                         {'n': str(new_name), 'd': str(new_desc) if new_desc else r[2], 'i': r[0]})
            
        await db.commit()
        break
    print("Cleanup finished.")

if __name__ == "__main__":
    asyncio.run(cleanup())
