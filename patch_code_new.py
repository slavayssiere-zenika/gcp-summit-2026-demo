import os
import re

SERVICES = [
    "items_api",
    "competencies_api",
    "cv_api",
    "drive_api",
    "prompts_api"
]

CWD = "/Users/sebastien.lavayssiere/Code/test-open-code"

def patch_requirements(service):
    req_path = os.path.join(CWD, service, "requirements.txt")
    if not os.path.exists(req_path):
        return
    with open(req_path, "r") as f:
        content = f.read()
    
    content = content.replace("google-cloud-alloydb-connector[pg8000]", "google-cloud-alloydb-connector[asyncpg]")
    content = content.replace("pg8000>=1.31.2", "asyncpg>=0.29.0\n")
    content = content.replace("psycopg2-binary>=2.9.0\n", "")
    content = content.replace("psycopg2-binary>=2.9.0", "")
    
    with open(req_path, "w") as f:
        f.write(content)
        
def patch_database(service):
    src = os.path.join(CWD, "users_api", "database.py")
    dest = os.path.join(CWD, service, "database.py")
    if not os.path.exists(src) or not os.path.exists(dest):
        return
    with open(src, "r") as f:
        content = f.read()
    with open(dest, "w") as f:
         f.write(content)

def patch_main(service):
    main_path = os.path.join(CWD, service, "main.py")
    if not os.path.exists(main_path):
        return
    with open(main_path, "r") as f:
        content = f.read()

    # Apply lifespan imports
    if "from contextlib import asynccontextmanager" not in content:
        content = content.replace("from fastapi import FastAPI", "from fastapi import FastAPI\nfrom contextlib import asynccontextmanager\nimport database")

    # Add lifespan definition
    lifespan_def = """

@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.init_db_connector()
    SQLAlchemyInstrumentor().instrument(engine=database.engine)
    yield
    await database.close_db_connector()

"""
    if "def lifespan" not in content:
        content = content.replace("app = FastAPI(", lifespan_def + 'app = FastAPI(lifespan=lifespan, ')

    # Remove sync SQLAlchemy instrumentation if present
    content = content.replace("SQLAlchemyInstrumentor().instrument(engine=engine)", "")
    
    # In check_db_connection
    content = content.replace("if check_db_connection():", "if await check_db_connection():")
    
    # Remove from database import engine
    content = content.replace("from database import engine\n", "")

    with open(main_path, "w") as f:
        f.write(content)

for svc in SERVICES:
    patch_requirements(svc)
    patch_database(svc)
    patch_main(svc)
    print(f"Patched generic files for {svc}")
