import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
from main import app
from src.auth import verify_jwt
from database import get_db

AUTH = {"Authorization": "Bearer testtoken"}

def override_jwt_admin():
    return {"sub": "1", "email": "admin@z.com", "role": "admin"}

app.dependency_overrides[verify_jwt] = override_jwt_admin

class DummyProfile:
    def __init__(self, id, user_id, missions):
        self.id = id
        self.user_id = user_id
        self.missions = missions

def test_get_user_missions_handles_malformed_missions(mocker):
    # Mocking db.execute(...).scalars().all()
    mock_db = AsyncMock()
    
    mock_profiles = [
        DummyProfile(id=1, user_id=2, missions=[
            {"title": "Tech Lead", "company": "Zenika"},
            {"title": None, "company": "Inconnu"},
            {"title": "Dev", "company": None},
            "invalid mission string",
            None
        ]),
        DummyProfile(id=2, user_id=2, missions=[
            {"title": "Tech Lead", "company": "Zenika"}, # duplicate
            {"title": "Data Engineer", "company": "Google"}
        ]),
        DummyProfile(id=3, user_id=2, missions=None) # no missions
    ]

    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = mock_profiles
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_result

    app.dependency_overrides[get_db] = lambda: mock_db
    
    client = TestClient(app)
    response = client.get("/user/2/missions", headers=AUTH)
    
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    
    items = data["items"]
    titles = [m.get("title") for m in items]
    
    # Verify duplicates removed, None handled correctly (skipped)
    assert "tech lead" in [t.lower() if t else t for t in titles]
    assert "data engineer" in [t.lower() if t else t for t in titles]
    assert "dev" in [t.lower() if t else t for t in titles]
    assert None not in titles

def test_get_user_missions_no_profiles(mocker):
    mock_db = AsyncMock()
    
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_result

    app.dependency_overrides[get_db] = lambda: mock_db
    
    client = TestClient(app)
    response = client.get("/user/2/missions", headers=AUTH)
    
    assert response.status_code == 404
    assert response.json()["detail"] == "Aucun profil CV trouvé pour cet utilisateur."

