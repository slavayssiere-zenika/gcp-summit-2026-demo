import os
os.environ['SECRET_KEY'] = 'testsecret'
import os
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test.db"

import pytest
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient
from main import app
from database import get_db
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from database import Base

# Sync engine for table creation
sync_engine = create_engine("sqlite:///./test.db", connect_args={"check_same_thread": False})

# Async engine for testing actual routes
async_engine = create_async_engine("sqlite+aiosqlite:///./test.db", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(class_=AsyncSession, autocommit=False, autoflush=False, expire_on_commit=False, bind=async_engine)

from src.auth import verify_jwt

def override_verify_jwt():
    return {"sub": "test", "role": "admin"}

async def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        await db.close()

app.dependency_overrides[get_db] = override_get_db

app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[verify_jwt] = override_verify_jwt

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=sync_engine)
    yield
    Base.metadata.drop_all(bind=sync_engine)

def test_health(mocker):
    mocker.patch("database.check_db_connection", new_callable=AsyncMock, return_value=True)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

def test_add_folder():
    response = client.post("/folders", json={"google_folder_id": "12345", "tag": "Paris"})
    assert response.status_code == 200
    assert response.json()["google_folder_id"] == "12345"
    assert response.json()["tag"] == "Paris"
    
def test_add_duplicate_folder():
    client.post("/folders", json={"google_folder_id": "12345", "tag": "Paris"})
    response = client.post("/folders", json={"google_folder_id": "12345", "tag": "Lille"})
    assert response.status_code == 400

def test_list_folders():
    client.post("/folders", json={"google_folder_id": "abc", "tag": "Nice"})
    response = client.get("/folders")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["tag"] == "Nice"

def test_status_empty():
    response = client.get("/status")
    assert response.status_code == 200
    data = response.json()
    assert data["total_files_scanned"] == 0
    assert data["pending"] == 0
