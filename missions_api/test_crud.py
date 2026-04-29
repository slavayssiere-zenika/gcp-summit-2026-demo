import os
os.environ['SECRET_KEY'] = 'testsecret'
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock
import json

from main import app
from database import get_db
from src.auth import verify_jwt

# 1. Provide dependency overrides for testing
async def override_get_db():
    db = AsyncMock()
    yield db

def override_verify_jwt():
    return {"sub": "test", "email": "test@zenika.com", "role": "admin"}

app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[verify_jwt] = override_verify_jwt

client = TestClient(app)

# 2. Basic Tests
def test_health(mocker):
    mocker.patch("database.check_db_connection", new=AsyncMock(return_value=True))
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

def test_get_spec_success(mocker):
    mocker.patch("builtins.open", mocker.mock_open(read_data="# Spec doc"))
    response = client.get("/spec")
    assert response.status_code == 200
    assert "# Spec doc" in response.text

def test_get_spec_fail(mocker):
    mocker.patch("builtins.open", side_effect=Exception("Not found"))
    response = client.get("/spec")
    assert response.status_code == 200
    assert "# Specification introuvable" in response.text

# 3. Router Tests with Mocks
@pytest.fixture
def mock_httpx(mocker):
    mock = mocker.patch("src.missions.analysis_service.httpx.AsyncClient")
    client_instance = AsyncMock()
    mock.return_value.__aenter__.return_value = client_instance
    return client_instance

@pytest.fixture
def mock_genai(mocker):
    return mocker.patch("src.missions.analysis_service.client")

def test_list_missions(mocker):
    mock_db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    
    mock_mission = MagicMock(id=1, title="Test Mission", description="Description", extracted_competencies=["Java"], proposed_team=[], fallback_full_scan=False, status="STAFFED", prefiltered_candidates=[])
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_mission]
    mock_db.execute.return_value = mock_result
    
    response = client.get("/missions", headers={"Authorization": "Bearer token"})
    assert response.status_code == 200
    assert response.json()[0]["title"] == "Test Mission"

# Tests STAFF-003 — Détection de conflits de staffing (get_active_missions_for_user)
# ---------------------------------------------------------------------------

def test_get_active_missions_for_user_staffed(mocker):
    """STAFF-003 : Un user staffé sur une mission doit apparaître dans active_missions."""
    mock_db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db

    mock_mission = MagicMock(
        id=5,
        title="Moteur de Rapprochement Factures (PR-2026-ZEN-FIN-04)",
        proposed_team=[
            {"user_id": 42, "full_name": "Ahmed KANOUN", "role": "Tech Lead", "estimated_days": 60, "justification": "Expert Java"},
            {"user_id": 7, "full_name": "Alice MARTIN", "role": "Consultant", "estimated_days": 30, "justification": "Backend Java"}
        ]
    )
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_mission]
    mock_db.execute.return_value = mock_result

    response = client.get("/missions/user/42/active", headers={"Authorization": "Bearer fake_token"})

    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == 42
    assert data["total"] == 1
    assert len(data["active_missions"]) == 1
    assert data["active_missions"][0]["mission_id"] == 5
    assert "Rapprochement" in data["active_missions"][0]["mission_title"]
    assert data["active_missions"][0]["role"] == "Tech Lead"


def test_get_active_missions_for_user_not_staffed(mocker):
    """STAFF-003 : Un user non staffé sur aucune mission doit retourner une liste vide."""
    mock_db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db

    mock_mission = MagicMock(
        id=5,
        title="Mission sans le user 99",
        proposed_team=[
            {"user_id": 42, "full_name": "Ahmed KANOUN", "role": "Tech Lead", "estimated_days": 60, "justification": "Expert Java"}
        ]
    )
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_mission]
    mock_db.execute.return_value = mock_result

    response = client.get("/missions/user/99/active", headers={"Authorization": "Bearer fake_token"})

    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == 99
    assert data["total"] == 0
    assert data["active_missions"] == []


def test_get_active_missions_ignores_sentinel_user_id_zero(mocker):
    """STAFF-003 : user_id=0 (sentinelle 'aucun profil') ne doit jamais apparaître dans active_missions."""
    mock_db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db

    mock_mission = MagicMock(
        id=3,
        title="Mission sans profils",
        proposed_team=[
            {"user_id": 0, "full_name": "Aucun profil disponible", "role": "Non staffé", "estimated_days": 0, "justification": "Aucun consultant qualifié"}
        ]
    )
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_mission]
    mock_db.execute.return_value = mock_result

    response = client.get("/missions/user/0/active", headers={"Authorization": "Bearer fake_token"})

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0


def test_get_active_missions_multiple_missions(mocker):
    """STAFF-003 : Un user staffé sur plusieurs missions doit toutes les voir."""
    mock_db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db

    mission_a = MagicMock(
        id=10, title="Mission FinTech A",
        proposed_team=[{"user_id": 42, "role": "Tech Lead", "estimated_days": 20, "justification": "Expert"}]
    )
    mission_b = MagicMock(
        id=11, title="Mission Cloud B",
        proposed_team=[{"user_id": 42, "role": "Architecte", "estimated_days": 15, "justification": "Cloud"}]
    )
    mission_c = MagicMock(
        id=12, title="Mission sans Ahmed",
        proposed_team=[{"user_id": 7, "role": "Consultant", "estimated_days": 10, "justification": "Other"}]
    )
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mission_a, mission_b, mission_c]
    mock_db.execute.return_value = mock_result

    response = client.get("/missions/user/42/active", headers={"Authorization": "Bearer fake_token"})

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    mission_ids = [m["mission_id"] for m in data["active_missions"]]
    assert 10 in mission_ids
    assert 11 in mission_ids
    assert 12 not in mission_ids


# ---------------------------------------------------------------------------
# Tests Mission Status Lifecycle (RBAC + State Machine)
# ---------------------------------------------------------------------------

def override_verify_jwt_commercial():
    return {"sub": "commercial@zenika.com", "role": "commercial"}

def override_verify_jwt_user():
    return {"sub": "user@zenika.com", "role": "user"}


def test_update_mission_status_commercial_allowed(mocker):
    """Un commercial peut faire passer une mission STAFFED → NO_GO."""
    from src.missions.models import MissionStatus

    mock_db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[verify_jwt] = override_verify_jwt_commercial

    mock_mission = MagicMock(
        id=1,
        title="Mission Test",
        status=MissionStatus.STAFFED,
    )
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = mock_mission
    mock_db.execute.return_value = mock_result
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()

    payload = {"status": "NO_GO", "reason": "Client hors budget"}
    response = client.patch("/missions/1/status", json=payload, headers={"Authorization": "Bearer fake_token"})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "NO_GO"
    assert data["old_status"] == "STAFFED"

    # Cleanup
    app.dependency_overrides[verify_jwt] = override_verify_jwt


def test_update_mission_status_user_forbidden(mocker):
    """Un user standard ne peut pas modifier le statut (403)."""
    mock_db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[verify_jwt] = override_verify_jwt_user

    payload = {"status": "NO_GO", "reason": "Test"}
    response = client.patch("/missions/1/status", json=payload, headers={"Authorization": "Bearer fake_token"})

    assert response.status_code == 403

    # Cleanup
    app.dependency_overrides[verify_jwt] = override_verify_jwt


def test_update_mission_status_invalid_transition(mocker):
    """Une transition STAFFED → WON est invalide (422)."""
    from src.missions.models import MissionStatus

    mock_db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[verify_jwt] = override_verify_jwt_commercial

    mock_mission = MagicMock(id=1, title="Mission Test", status=MissionStatus.STAFFED)
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = mock_mission
    mock_db.execute.return_value = mock_result

    payload = {"status": "WON", "reason": "Tentative invalide"}
    response = client.patch("/missions/1/status", json=payload, headers={"Authorization": "Bearer fake_token"})

    assert response.status_code == 422

    # Cleanup
    app.dependency_overrides[verify_jwt] = override_verify_jwt


def test_list_missions_includes_status(mocker):
    """L'endpoint GET /missions doit inclure le champ 'status' dans chaque entrée."""
    from src.missions.models import MissionStatus

    mock_db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db

    mock_mission = MagicMock(
        id=1,
        title="Mission avec statut",
        description="Description",
        status=MissionStatus.STAFFED,
        extracted_competencies=["Java"],
        proposed_team=[],
        fallback_full_scan=False,
    )
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_mission]
    mock_db.execute.return_value = mock_result

    response = client.get("/missions", headers={"Authorization": "Bearer token"})
    assert response.status_code == 200
    missions = response.json()
    assert len(missions) > 0
    assert "status" in missions[0]
    assert missions[0]["status"] == "STAFFED"

