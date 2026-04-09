import os
import re

directories = ['users_api', 'items_api', 'competencies_api', 'cv_api', 'prompts_api', 'drive_api']
for d in directories:
    file_path = os.path.join(d, 'database.py')
    if not os.path.exists(file_path):
        continue
    
    with open(file_path, 'r') as f:
        content = f.read()

    # The current code has:
    # DB_USER = os.getenv("DB_USER", "postgres")
    # DB_NAME = os.getenv("DB_NAME", "mydb")
    
    # We want to replace it with parsing from DATABASE_URL prioritizing it.
    
    new_vars = """import re

DB_USER = os.getenv("DB_USER", "postgres")
DB_NAME = os.getenv("DB_NAME", "mydb")

if DATABASE_URL and DATABASE_URL.startswith("postgresql"):
    m = re.match(r"postgresql(?:\\+asyncpg)?://([^:]+)(?::[^@]*)?@[^/]+/([^/?]+)", DATABASE_URL)
    if m:
        DB_USER = m.group(1)
        DB_NAME = m.group(2)
"""
    content = content.replace('DB_USER = os.getenv("DB_USER", "postgres")\nDB_NAME = os.getenv("DB_NAME", "mydb")', new_vars)
    
    with open(file_path, 'w') as f:
        f.write(content)
    print(f"Patched {file_path}")
