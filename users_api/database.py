from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
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


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from src.users.models import Base
    from sqlalchemy import text
    
    # Create all tables if not exist
    Base.metadata.create_all(bind=engine)
    
    # Manual migrations for Users
    with engine.connect() as conn:
        try:
            # Add hashed_password if missing
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS hashed_password VARCHAR"))
            conn.execute(text("UPDATE users SET hashed_password = 'PENDING_MIGRATION' WHERE hashed_password IS NULL"))
            
            # Add first_name and last_name if missing
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS first_name VARCHAR"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_name VARCHAR"))
            
            conn.commit()
            
            # --- Seeding de l'utilisateur Admin sécurisé ---
            admin_pwd = os.getenv("DEFAULT_ADMIN_PASSWORD")
            if admin_pwd:
                from src.auth import get_password_hash
                from datetime import datetime
                
                res = conn.execute(text("SELECT id FROM users WHERE username = 'admin'"))
                if not res.fetchone():
                    hashed = get_password_hash(admin_pwd)
                    conn.execute(
                        text("""
                            INSERT INTO users (username, email, first_name, last_name, full_name, hashed_password, role, is_active, created_at, allowed_category_ids)
                            VALUES ('admin', 'admin@zenika.com', 'Zenika', 'Admin', 'Zenika Root Admin', :hashed, 'admin', True, :now, '1,2,3,4,5')
                        """), 
                        {"hashed": hashed, "now": datetime.utcnow()}
                    )
                    conn.commit()
                    print("[*] Admin user successfully seeded from environment securely.")
                    
        except Exception as e:
            print(f"Migration notice (can be ignored if table new): {str(e)}")
            conn.rollback()
