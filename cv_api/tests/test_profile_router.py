from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
from main import app
from src.auth import verify_jwt
from database import get_db

AUTH = {"Authorization": "Bearer testtoken"}


def override_jwt_admin():
    return {"sub": "1", "email": "admin@z.com", "role": "admin"}


app.dependency_overrides[verify_jwt] = override_jwt_admin

from src.cvs.models import CVProfile  # noqa: E402


def create_mock_profile(id, user_id, missions):
    m = MagicMock(spec=CVProfile)
    m.id = id
    m.user_id = user_id
    m.missions = missions
    return m


def test_get_user_missions_handles_malformed_missions(mocker):
    # Mocking db.execute(...).scalars().all()
    mock_db = AsyncMock()

    mock_profiles = [
        create_mock_profile(id=1, user_id=2, missions=[
            {"title": "Tech Lead", "company": "Zenika"},
            {"title": None, "company": "Inconnu"},
            {"title": "Dev", "company": None},
            "invalid mission string",
            None
        ]),
        create_mock_profile(id=2, user_id=2, missions=[
            {"title": "Tech Lead", "company": "Zenika"},  # duplicate
            {"title": "Data Engineer", "company": "Google"}
        ]),
        create_mock_profile(id=3, user_id=2, missions=None)  # no missions
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


def test_import_cv_success(mocker):
    # Mocking profile import
    mock_db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db

    mock_extract = AsyncMock()
    from src.cvs.schemas import CVResponse
    mock_extract.return_value = CVResponse(
        message="Import et analyse terminés avec succès",
        user_id=1,
        competencies_assigned=0,
        extracted_info={
            "first_name": "Test",
            "last_name": "User",
            "email": "test@z.com",
            "is_anonymous": False,
            "current_role": "Dev",
            "years_of_experience": 5,
            "summary": "Test"
        },
        warnings=[],
        steps=[]
    )
    mocker.patch("src.cvs.routers.profile_router.process_cv_core", mock_extract)

    client = TestClient(app)
    response = client.post("/import", json={"url": "http://cv.pdf", "folder_name": "folder"}, headers=AUTH)

    assert response.status_code == 200
    assert response.json()["user_id"] == 1
    assert response.json()["message"] == "Import et analyse terminés avec succès"


def test_get_user_details(mocker):
    mock_db = AsyncMock()

    mock_profile = create_mock_profile(id=1, user_id=2, missions=[])
    mock_profile.first_name = "User"
    mock_profile.last_name = "Test"
    mock_profile.email = "test@z.com"
    mock_profile.extracted_competencies = []
    mock_profile.educations = []
    mock_profile.source_url = "http"
    mock_profile.years_of_experience = 5
    mock_profile.current_role = "Dev"
    mock_profile.summary = "Test"
    mock_profile.id = 1

    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [mock_profile]
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_result

    app.dependency_overrides[get_db] = lambda: mock_db

    client = TestClient(app)
    response = client.get("/user/2/details", headers=AUTH)

    assert response.status_code == 200
    assert response.json()["user_id"] == 2
