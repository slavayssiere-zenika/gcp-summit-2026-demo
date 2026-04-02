import pytest
from fastapi.testclient import TestClient
from main import app
from database import get_db
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
import os

# SQLite InMemory for tests
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

def test_add_folder():
    response = client.post("/drive-api/folders", json={"google_folder_id": "12345", "tag": "Paris"})
    assert response.status_code == 200
    assert response.json()["google_folder_id"] == "12345"
    assert response.json()["tag"] == "Paris"
    
def test_add_duplicate_folder():
    client.post("/drive-api/folders", json={"google_folder_id": "12345", "tag": "Paris"})
    response = client.post("/drive-api/folders", json={"google_folder_id": "12345", "tag": "Lille"})
    assert response.status_code == 400

def test_list_folders():
    client.post("/drive-api/folders", json={"google_folder_id": "abc", "tag": "Nice"})
    response = client.get("/drive-api/folders")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["tag"] == "Nice"

def test_status_empty():
    response = client.get("/drive-api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["total_files_scanned"] == 0
    assert data["pending"] == 0
