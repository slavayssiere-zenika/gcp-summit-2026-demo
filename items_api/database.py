from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/mydb")
USE_IAM_AUTH = os.getenv("USE_IAM_AUTH", "false").lower() == "true"

def get_engine():
    if USE_IAM_AUTH:
        import google.auth
        from google.auth.transport.requests import Request
        from sqlalchemy.engine.url import make_url
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        credentials.refresh(Request())
        url = make_url(DATABASE_URL)
        url = url.set(password=credentials.token)
        return create_engine(url)
    return create_engine(DATABASE_URL)

engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from src.items.models import Base
    Base.metadata.create_all(bind=engine)
