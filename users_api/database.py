from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/mydb")

engine = create_engine(DATABASE_URL)
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
        except Exception as e:
            print(f"Migration notice (can be ignored if table new): {str(e)}")
            conn.rollback()
