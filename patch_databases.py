import os
import re

dirs = ["users_api", "items_api", "competencies_api", "cv_api", "prompts_api", "drive_api"]

for d in dirs:
    path = os.path.join(d, "database.py")
    if not os.path.exists(path):
        continue
    
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Import tenacity if missing
    if "from tenacity import" not in content:
        content = "from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type\n" + content

    # Replace the async def getconn() block
    pattern = re.compile(r"(\s*)async def getconn\(\):.*?(?=\1\s*engine = create_async_engine)", re.DOTALL)
    
    replacement = r"""\1@retry(wait=wait_exponential(multiplier=1, min=4, max=10), stop=stop_after_attempt(5), reraise=True)
\1async def getconn():
\1    logger.info(f"[DB] Attempting IAM connection to {ALLOYDB_INSTANCE_URI} as user '{DB_USER}'")
\1    conn = await connector.connect(
\1        ALLOYDB_INSTANCE_URI,
\1        "asyncpg",
\1        user=DB_USER,
\1        db=DB_NAME,
\1        enable_iam_auth=True,
\1        ip_type=IPTypes.PRIVATE
\1    )
\1    return conn
"""
    new_content = pattern.sub(replacement, content)
    
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"Patched {path}")
