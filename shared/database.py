import asyncio
import logging
import os
import re
from typing import AsyncGenerator

from google.cloud.alloydb.connector import AsyncConnector, IPTypes
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from tenacity import retry, stop_after_attempt, wait_exponential

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

    # P3.1 — hnsw.ef_search : parametre de qualite du graphe HNSW lors de la recherche.
    # Uniquement pour cv_api : configure via HNSW_EF_SEARCH=100 dans docker-compose / Cloud Run.
    # 0 = desactive (defaut) : aucune surcharge pour les autres services.
    hnsw_ef_search = int(os.getenv("HNSW_EF_SEARCH", "0"))
    _connect_args: dict = {}
    if hnsw_ef_search > 0:
        _connect_args["server_settings"] = {"hnsw.ef_search": str(hnsw_ef_search)}
        logger.info("[DB] hnsw.ef_search=%d configure via server_settings asyncpg.", hnsw_ef_search)

    pool_params = {
        "pool_pre_ping": True,
        # 5min au lieu de 30min : les connexions dégradées post-pic sont recyclées
        # plus agressivement. Évite la latence résiduelle constatée après les stress tests.
        "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", 300)),
        "pool_size": int(os.getenv("DB_POOL_SIZE", 10)),
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", 20)),
        # Fail-fast si pool sature : renvoie 500 apres 5s au lieu de bloquer 30s
        # (defaut SQLAlchemy = 30s → cascade de latences sur toutes les routes items_api)
        "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", 5)),
        # Rollback explicite à chaque retour de connexion au pool : garantit qu'une
        # transaction ouverte (BEGIN sans COMMIT, après exception) est annulée proprement
        # plutôt que de rester dans un état indéterminé jusqu'au prochain pool_recycle.
        "pool_reset_on_return": "rollback",
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
                # noqa: E501
                logger.error(f"[DB] IAM Authentication failed. Propagation delay detected. Wait. Details: {e}")
                raise

        engine = create_async_engine("postgresql+asyncpg://", async_creator=getconn, **pool_params)
    else:
        target_url = DATABASE_URL
        if target_url and target_url.startswith("postgresql://"):
            target_url = target_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        engine = create_async_engine(target_url, connect_args=_connect_args, **pool_params)

    SessionLocal = sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False,
        autocommit=False, autoflush=False
    )


async def close_db_connector():
    if engine:
        await engine.dispose()
    if connector:
        await connector.close()


async def check_db_connection() -> bool:
    """Vérifie la connectivité DB avec un timeout court (5s).

    Utilise asyncio.wait_for pour éviter de bloquer le /ready endpoint
    quand le pool de connexions est saturé (ex: pendant un bulk pipeline).
    En cas de TimeoutError (saturation temporaire), retourne True de façon
    optimiste — le 503 ne se déclenche que si la DB est réellement inaccessible.
    """
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
    # Pas de finally: await db.close() — async with SessionLocal() gere deja le cycle
    # de vie via __aexit__ + asyncio.shield(). Un double-close cause IllegalStateChangeError
    # sous charge concurrente avec SQLAlchemy 2.x + Python 3.13.
    # Pour resoudre le bug du cycle de vie sous pytest/asyncio, on intercepte les exceptions
    # et on close explicitement.
    async with SessionLocal() as db:
        try:
            yield db
        except Exception:
            await db.close()
            raise
