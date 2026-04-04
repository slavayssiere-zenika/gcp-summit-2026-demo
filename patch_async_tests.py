import os
import re

directories = ["users_api", "items_api", "competencies_api", "cv_api", "prompts_api", "drive_api"]

for dir_name in directories:
    # 1. DELETE test_database.py
    test_db_path = os.path.join(dir_name, "test_database.py")
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
    # also tests/test_database.py
    test_db_path2 = os.path.join(dir_name, "tests", "test_database.py")
    if os.path.exists(test_db_path2):
        os.remove(test_db_path2)

    # 2. PATCH database.py
    db_path = os.path.join(dir_name, "database.py")
    if os.path.exists(db_path):
        with open(db_path, "r") as f:
            db_content = f.read()

        if "if \"sqlite\" in DATABASE_URL:" not in db_content:
            # Replace the engine creation
            target = "engine = create_async_engine(DATABASE_URL, **pool_params)"
            replacement = """from sqlalchemy.pool import StaticPool
        if "sqlite" in DATABASE_URL:
            engine = create_async_engine(DATABASE_URL, poolclass=StaticPool)
        else:
            engine = create_async_engine(DATABASE_URL, **pool_params)"""
            db_content = db_content.replace(target, replacement)
            with open(db_path, "w") as f:
                f.write(db_content)

    # 3. PATCH conftest.py
    conf_path = os.path.join(dir_name, "conftest.py")
    if not os.path.exists(conf_path):
        conf_path = os.path.join(dir_name, "tests", "conftest.py")
        if not os.path.exists(conf_path):
            continue

    with open(conf_path, "r") as f:
        conf_content = f.read()

    # Skip if already asyncio
    if "create_async_engine" in conf_content and "aiosqlite" in conf_content:
        pass
    else:
        # Patch sqlite URL
        conf_content = conf_content.replace('os.environ["DATABASE_URL"] = "sqlite://"', 'os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"')
        
        # Patch engine dispose
        conf_content = conf_content.replace("engine.dispose() # Dispose the one created in database.py", "")
        conf_content = conf_content.replace("if engine:\n    engine.dispose()", "")

        # Patch imports
        conf_content = conf_content.replace("from sqlalchemy import create_engine", "from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession")
        conf_content = conf_content.replace("from sqlalchemy.orm import sessionmaker", "")

        # Patch Engine definition
        engine_regex = re.compile(r"engine = create_engine\([\s\S]*?poolclass=StaticPool,\n?\)")
        new_engine = """engine = create_async_engine(
    "sqlite+aiosqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)"""
        conf_content = engine_regex.sub(new_engine, conf_content)
        
        # Handle cases where engine = create_engine wasn't formatted precisely this way
        if new_engine not in conf_content:
            fallback = re.compile(r"engine = create_engine\(.*?\)", re.MULTILINE)
            conf_content = fallback.sub(new_engine, conf_content)

        # Patch SessionLocal
        sess_regex = re.compile(r"TestingSessionLocal = sessionmaker\(.*?\)")
        conf_content = sess_regex.sub("TestingSessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=AsyncSession)", conf_content)

        # Patch Base.metadata
        create_all_regex = re.compile(r"Base\.metadata\.create_all\(bind=engine\)")
        new_create_all = """import asyncio
async def init_test_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
try:
    asyncio.run(init_test_db())
except RuntimeError:
    pass # loop already in execution"""
        conf_content = create_all_regex.sub(new_create_all, conf_content, count=1)
        conf_content = create_all_regex.sub("asyncio.run(init_test_db())", conf_content) # Remaining hits

        # Patch override_get_db
        over_regex = re.compile(r"def override_get_db\(\):[\s\S]*?try:[\s\S]*?finally:\n?\s+?db\.close\(\)")
        new_over = """async def override_get_db():
    async with TestingSessionLocal() as db:
        yield db"""
        conf_content = over_regex.sub(new_over, conf_content)

        # Patch db fixture
        fix_db_regex = re.compile(r"session = TestingSessionLocal\(\)\n\s+yield session\n\s+session\.close\(\)\n\s+Base\.metadata\.drop_all\(bind=engine\)")
        new_fix_db = """async with TestingSessionLocal() as session:
        yield session"""
        conf_content = fix_db_regex.sub(new_fix_db, conf_content)

        # Ensure @pytest.mark.asyncio or async generator rules apply if we ever yielded directly.
        # Just writing it back
        with open(conf_path, "w") as f:
            f.write(conf_content)

print("Patch script applied across all APIs.")
