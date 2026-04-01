import os
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# CRITICAL: Set environment variables BEFORE any imports that use them at module level
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["ITEMS_API_URL"] = "http://items-api:8001"
os.environ["USERS_API_URL"] = "http://users-api:8000"
os.environ["JWT_SECRET_KEY"] = "testsecret"

# Mock OpenTelemetry before importing the app
with patch("opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter", return_value=MagicMock()):
    from main import app
    from database import get_db, engine
    from src.users.models import Base
    from src.auth import verify_jwt

# Re-configure engine for in-memory SQLite compatibility with FastAPI
# (Must use StaticPool to keep the connection alive across threads)
engine.dispose() # Dispose the one created in database.py
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create tables once for the test session
Base.metadata.create_all(bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

def override_verify_jwt():
    return {"sub": "1", "role": "admin"}

app.dependency_overrides[verify_jwt] = override_verify_jwt

@pytest.fixture(scope="function")
def db():
    # Create the database and the tables
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c
