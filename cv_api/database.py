import asyncio
import logging
import os
import re

from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import text
from google.cloud.alloydb.connector import AsyncConnector, IPTypes
from typing import AsyncGenerator

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")
ALLOYDB_INSTANCE_URI = os.getenv("ALLOYDB_INSTANCE_URI")
USE_IAM_AUTH = os.getenv("USE_IAM_AUTH", "false").lower() == "true"

DB_USER = os.getenv("DB_USER", "postgres")
DB_NAME = os.getenv("DB_NAME", "mydb")

if DATABASE_URL and DATABASE_URL.startswith("postgresql"):
    m = re.match(r"postgresql(?:\+asyncpg)?://([^:]+)(?::[^@]*)?@[^/]+/([^/?]+)", DATABASE_URL)
    if m:
        DB_USER = m.group(1)
        DB_NAME = m.group(2)

Base = declarative_base()
connector = None
engine = None
SessionLocal = None

async def init_db_connector():
    global connector, engine, SessionLocal
    
    pool_size = int(os.getenv("DB_POOL_SIZE", "50"))
    max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "100"))

    pool_params = {
        "pool_pre_ping": True,
        "pool_recycle": 1800,
        "pool_size": pool_size,
        "max_overflow": max_overflow,
    }

    if USE_IAM_AUTH and ALLOYDB_INSTANCE_URI:
        logger.info(f"[DB] Initializing Python AlloyDB Connector via asyncpg for {ALLOYDB_INSTANCE_URI}")
        connector = AsyncConnector()
        
        import asyncpg
        @retry(wait=wait_exponential(multiplier=1, min=4, max=10), stop=stop_after_attempt(5), reraise=True)
        async def getconn():
            logger.debug(f"[DB] Attempting IAM connection to {ALLOYDB_INSTANCE_URI} as user '{DB_USER}'")
            try:
                conn = await connector.connect(
                    ALLOYDB_INSTANCE_URI,
                    "asyncpg",
                    user=DB_USER,
                    db=DB_NAME,
                    enable_iam_auth=True,
                    ip_type=IPTypes.PRIVATE
                )
                return conn
            except asyncpg.exceptions.InvalidAuthorizationSpecificationError as e:
                logger.error(f"[DB] IAM Authentication failed. Propagation delay detected. Ensure the service account has 'roles/alloydb.client' and wait. Details: {e}")
                raise
        
        engine = create_async_engine("postgresql+asyncpg://", async_creator=getconn, **pool_params)
    else:
        target_url = DATABASE_URL
        if target_url and target_url.startswith("postgresql://"):
            target_url = target_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        engine = create_async_engine(target_url, **pool_params)

    SessionLocal = sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False,
        autocommit=False, autoflush=False
    )

async def close_db_connector():
    global connector, engine
    if engine:
        await engine.dispose()
    if connector:
        await connector.close()
        
async def check_db_connection() -> bool:
    """Vérifie la connectivité DB avec un timeout court (5s).

    Utilise asyncio.wait_for pour éviter de bloquer le /ready endpoint
    quand le pool de connexions est saturé (ex: pendant un batch Vertex AI).
    En cas de TimeoutError (saturation temporaire), retourne True de façon
    optimiste — le 503 ne se déclenche que si la DB est réellement inaccessible.
    """
    global engine
    if not engine:
        return False
    try:
        async def _ping():
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))

        await asyncio.wait_for(_ping(), timeout=5.0)
        return True
    except asyncio.TimeoutError:
        logger.warning("[DB] check_db_connection timeout (5s) — pool probablement saturé. Retour optimiste: True.")
        return True
    except Exception as e:
        logger.error(f"[DB] Database connection test failed: {e}")
        return False

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as db:
        try:
            yield db
        finally:
            await db.close()

# For imports requiring Base or other items directly
