import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from shared.database import get_db
from fastapi.testclient import TestClient
from main import app
from shared.auth.jwt import security, verify_jwt

os.environ['SECRET_KEY'] = 'testsecret'


# 1. Provide dependency overrides for testing
async def override_get_db():
    db = AsyncMock()
    yield db


def override_verify_jwt():
    return {"sub": "test", "role": "admin"}


app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[verify_jwt] = override_verify_jwt

app.dependency_overrides[security] = lambda: MagicMock(credentials="testtoken")

client = TestClient(app)

# 2. Basic Tests


def test_health(mocker):
    mocker.patch("shared.database.check_db_connection", new=AsyncMock(return_value=True))
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
    mock = mocker.patch("httpx.AsyncClient")
    client_instance = AsyncMock()
    mock.return_value.__aenter__.return_value = client_instance
    return client_instance


@pytest.fixture
def mock_genai(mocker):
    # Les sous-routers utilisent _svc_config.client (accès attribut).
    # Patcher la source src.services.config.client suffit pour tous.
    return mocker.patch("src.services.config.client")


def test_get_user_cv(mocker):
    # Mocking db.query
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_profile = MagicMock(user_id=1, source_url="http://test.com/cv.pdf", source_tag=None, imported_by_id=None)
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [mock_profile]
    mock_result.scalars.return_value = mock_scalars
    # First execute() = count query, second = paginated query
    mock_result.scalar.return_value = 1
    mock_db.execute.return_value = mock_result

    app.dependency_overrides[get_db] = lambda: mock_db

    response = client.get("/user/1")
    assert response.status_code == 200
    data = response.json()
    assert data["items"][0]["user_id"] == 1
    assert data["items"][0]["source_url"] == "http://test.com/cv.pdf"

    # Not found case
    mock_scalars.all.return_value = []
    mock_result.scalar.return_value = 0
    response = client.get("/user/2")
    assert response.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# Tests — Nomenclature Zenika : folder_name dans /import
# ═══════════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════════
# Tests — /reanalyze : Pipeline Pub/Sub unifié (plus de SSE)
# UC6 : reset PENDING + /sync déclenché
# UC7 : URL sans google_file_id → skipped_manual
# UC8 : drive_api inaccessible → mode dégradé, retour JSON 200
# UC9 : aucun CV en base → message re-découverte Drive
# ═══════════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════════
# Tests — /extraction-scores : Analytics API
# ═══════════════════════════════════════════════════════════════════════════════
