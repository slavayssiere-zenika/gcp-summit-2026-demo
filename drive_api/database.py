from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from typing import Generator
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/mydb")
USE_IAM_AUTH = os.getenv("USE_IAM_AUTH", "false").lower() == "true"

def get_engine():
    pool_params = {
        "pool_pre_ping": True,
        "pool_recycle": 1800,
    }
    
    if USE_IAM_AUTH:
        import logging
        import google.auth
        from google.auth.transport.requests import Request
        from sqlalchemy import event
        
        logger = logging.getLogger(__name__)
        credentials, _ = google.auth.default(scopes=[
            "https://www.googleapis.com/auth/cloud-platform",
            "https://www.googleapis.com/auth/alloydb.login"
        ])
        
        engine = create_engine(DATABASE_URL, **pool_params)
        logger.info("[DB] Initialized IAM-enabled Engine with pre_ping and recycle bounds")
        
        @event.listens_for(engine, "do_connect")
        def receive_do_connect(dialect, conn_rec, cargs, cparams):
            if not credentials.valid:
                logger.warning("[DB] IAM Token expired or empty, requesting refresh from GCP metadata...")
                try:
                    credentials.refresh(Request())
                    logger.info("[DB] Successfully refreshed IAM Token.")
                except Exception as e:
                    logger.error(f"[DB] Failed to refresh IAM token: {e}")
                    raise
            cparams["password"] = credentials.token
            
        return engine
        
    return create_engine(DATABASE_URL, **pool_params)

engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()