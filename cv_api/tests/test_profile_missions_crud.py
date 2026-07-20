from unittest.mock import AsyncMock, MagicMock
import pytest
from fastapi.testclient import TestClient
from main import app
from shared.auth.jwt import verify_jwt
from shared.database import get_db
from src.cvs.models import CVProfile

AUTH_ADMIN = {"Authorization": "Bearer admintoken"}


def override_jwt_admin():
    return {"sub": "1", "email": "admin@z.com", "role": "admin", "user_id": 1}


def override_jwt_other_user():
    return {"sub": "999", "email": "other@z.com", "role": "consultant", "user_id": 999}


@pytest.fixture(autouse=True)
def run_around_tests():
    # Before test: set default test admin
    app.dependency_overrides[verify_jwt] = override_jwt_admin
    yield
    # After test: reset to default test admin to prevent leakage to other test suites
    app.dependency_overrides[verify_jwt] = override_jwt_admin


def create_mock_profile(id, user_id, missions):
    m = MagicMock(spec=CVProfile)
    m.id = id
    m.user_id = user_id
    m.missions = missions
    m.created_at = "2026-07-17 12:00:00"
    return m


def test_add_mission_success(mocker):
    mock_db = AsyncMock()
    mock_profile = create_mock_profile(id=1, user_id=2, missions=[])

    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.first.return_value = mock_profile
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_result

    app.dependency_overrides[get_db] = lambda: mock_db

    client = TestClient(app)
    response = client.post("/user/2/missions", json={
        "title": "Ingénieur DevOps Cloud",
        "company": "Zenika",
        "description": "Mise en place de Terraform",
        "start_date": "2024-01",
        "end_date": "2025-06",
        "duration": "1 an",
        "mission_type": "build",
        "competencies": ["Terraform", "GCP"],
        "is_sensitive": False
    }, headers=AUTH_ADMIN)

    assert response.status_code == 201
    assert response.json()["title"] == "Ingénieur DevOps Cloud"
    assert response.json()["company"] == "Zenika"
    assert "Terraform" in response.json()["competencies"]


def test_update_mission_success(mocker):
    mock_db = AsyncMock()
    existing_mission = {
        "title": "Développeur",
        "company": "Ancien Client",
        "description": "Ancien Job"
    }
    mock_profile = create_mock_profile(id=1, user_id=2, missions=[existing_mission])

    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.first.return_value = mock_profile
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_result

    app.dependency_overrides[get_db] = lambda: mock_db

    client = TestClient(app)
    response = client.put("/user/2/missions/0", json={
        "title": "Développeur Senior Nuxt.js",
        "company": "Zenika"
    }, headers=AUTH_ADMIN)

    assert response.status_code == 200
    assert response.json()["title"] == "Développeur Senior Nuxt.js"
    assert response.json()["company"] == "Zenika"
    assert response.json()["description"] == "Ancien Job"


def test_delete_mission_success(mocker):
    mock_db = AsyncMock()
    existing_mission = {
        "title": "A Supprimer",
        "company": "Client"
    }
    mock_profile = create_mock_profile(id=1, user_id=2, missions=[existing_mission])

    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.first.return_value = mock_profile
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_result

    app.dependency_overrides[get_db] = lambda: mock_db

    client = TestClient(app)
    response = client.delete("/user/2/missions/0", headers=AUTH_ADMIN)

    assert response.status_code == 200
    assert response.json()["success"] is True


def test_crud_missions_security_denied(mocker):
    app.dependency_overrides[verify_jwt] = override_jwt_other_user

    mock_db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db

    client = TestClient(app)

    # Test Create denied
    res_post = client.post("/user/2/missions", json={"title": "Dev"}, headers=AUTH_ADMIN)
    assert res_post.status_code == 403

    # Test Update denied
    res_put = client.put("/user/2/missions/0", json={"title": "Dev"}, headers=AUTH_ADMIN)
    assert res_put.status_code == 403

    # Test Delete denied
    res_del = client.delete("/user/2/missions/0", headers=AUTH_ADMIN)
    assert res_del.status_code == 403
