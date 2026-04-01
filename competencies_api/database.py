import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/mydb")
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
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    from src.competencies.models import Base as ModelsBase
    ModelsBase.metadata.create_all(bind=engine)
