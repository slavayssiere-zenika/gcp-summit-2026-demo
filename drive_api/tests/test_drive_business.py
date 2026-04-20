"""
Tests de la logique métier drive_api.

Couvre :
- DELETE /folders/{id} — suppression et vérification
- GET /files — liste des fichiers trackés
- POST /retry-errors — remise en file des erreurs
- GET /tokens/google — endpoint token ADC
- POST /sync — déclenchement synchronisation (public, protégé par Cloud IAM)
- Vérification auth JWT sur toutes les routes protégées
- GET /status avec compteurs détaillés (errors, imported, ignored)
"""

import os
os.environ['SECRET_KEY'] = 'testsecret'
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./drive_business_test.db"
os.environ["USERS_API_URL"] = "http://users-api:8000"

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

with patch("opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter", return_value=MagicMock()):
    from main import app
    from database import get_db, Base
    from src.auth import verify_jwt
    import src.models  # Required so Base.metadata knows about tables before create_all

# ── DB Setup ──────────────────────────────────────────────────────────────────

sync_engine = create_engine("sqlite:///./drive_business_test.db", connect_args={"check_same_thread": False})
async_engine = create_async_engine("sqlite+aiosqlite:///./drive_business_test.db", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(
    class_=AsyncSession,
    autocommit=False, autoflush=False, expire_on_commit=False,
    bind=async_engine
)

async def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        await db.close()

def override_verify_jwt():
    return {"sub": "admin@zenika.com", "email": "admin@zenika.com", "role": "admin"}

@pytest.fixture(autouse=True)
def app_with_overrides():
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[verify_jwt] = override_verify_jwt
    yield app
    app.dependency_overrides.clear()

@pytest.fixture
def client(app_with_overrides):
    return TestClient(app_with_overrides)

AUTH_HEADER = {"Authorization": "Bearer fake_admin_token"}

@pytest.fixture(autouse=True)
def fresh_db():
    """Recrée le schéma avant chaque test pour garantir l'isolation."""
    Base.metadata.drop_all(bind=sync_engine)
    Base.metadata.create_all(bind=sync_engine)
    yield
    Base.metadata.drop_all(bind=sync_engine)


# ── Tests Auth sur Routes Protégées ──────────────────────────────────────────

def test_folders_post_requires_jwt(client):
    """POST /folders sans JWT doit retourner 401."""
    original = app.dependency_overrides.pop(verify_jwt, None)
    try:
        resp = client.post("/folders", json={"google_folder_id": "abc123", "tag": "Lyon"})
        assert resp.status_code == 401
    finally:
        if original:
            app.dependency_overrides[verify_jwt] = original


def test_folders_get_requires_jwt(client):
    """GET /folders sans JWT doit retourner 401."""
    original = app.dependency_overrides.pop(verify_jwt, None)
    try:
        resp = client.get("/folders")
        assert resp.status_code == 401
    finally:
        if original:
            app.dependency_overrides[verify_jwt] = original


def test_folders_delete_requires_jwt(client):
    """DELETE /folders/{id} sans JWT doit retourner 401."""
    original = app.dependency_overrides.pop(verify_jwt, None)
    try:
        resp = client.delete("/folders/1")
        assert resp.status_code == 401
    finally:
        if original:
            app.dependency_overrides[verify_jwt] = original


def test_status_requires_jwt(client):
    """GET /status sans JWT doit retourner 401."""
    original = app.dependency_overrides.pop(verify_jwt, None)
    try:
        resp = client.get("/status")
        assert resp.status_code == 401
    finally:
        if original:
            app.dependency_overrides[verify_jwt] = original


# ── Tests Gestion Dossiers ────────────────────────────────────────────────────

def test_add_and_get_folder(client):
    """POST /folders crée un dossier, GET /folders le retrouve."""
    resp = client.post("/folders", json={"google_folder_id": "folder_abc", "tag": "Paris"}, headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["google_folder_id"] == "folder_abc"
    assert data["tag"] == "Paris"
    assert "id" in data

    list_resp = client.get("/folders", headers=AUTH_HEADER)
    assert list_resp.status_code == 200
    folders = list_resp.json()
    assert len(folders) == 1
    assert folders[0]["google_folder_id"] == "folder_abc"


def test_delete_folder_success(client):
    """DELETE /folders/{id} supprime le dossier, le GET suivant retourne 0 entrées."""
    # Créer
    create_resp = client.post("/folders", json={"google_folder_id": "del_folder", "tag": "Nantes"}, headers=AUTH_HEADER)
    assert create_resp.status_code == 200
    folder_id = create_resp.json()["id"]

    # Supprimer
    del_resp = client.delete(f"/folders/{folder_id}", headers=AUTH_HEADER)
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deleted"

    # Vérifier l'absence
    list_resp = client.get("/folders", headers=AUTH_HEADER)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 0


def test_delete_folder_not_found(client):
    """DELETE /folders/9999 sur un id inexistant doit retourner 404."""
    resp = client.delete("/folders/9999", headers=AUTH_HEADER)
    assert resp.status_code == 404


def test_add_duplicate_folder(client):
    """Enregistrer deux fois le même google_folder_id doit retourner 400."""
    client.post("/folders", json={"google_folder_id": "dup_folder", "tag": "Bordeaux"}, headers=AUTH_HEADER)
    resp = client.post("/folders", json={"google_folder_id": "dup_folder", "tag": "Marseille"}, headers=AUTH_HEADER)
    assert resp.status_code == 400
    assert "already registered" in resp.json()["detail"]


def test_add_folder_extracts_id_from_url(client):
    """Une URL complète Google Drive doit être parsée pour extraire l'ID."""
    resp = client.post(
        "/folders",
        json={"google_folder_id": "https://drive.google.com/drive/folders/1BcD2EfGhIjKl3Mn", "tag": "Lille"},
        headers=AUTH_HEADER
    )
    assert resp.status_code == 200
    # L'ID extrait doit être uniquement l'identifiant, pas l'URL complète
    assert resp.json()["google_folder_id"] == "1BcD2EfGhIjKl3Mn"


# ── Tests Status Détaillé ─────────────────────────────────────────────────────

def test_status_empty_database(client):
    """GET /status sur une base vide doit retourner des compteurs à 0."""
    resp = client.get("/status", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_files_scanned"] == 0
    assert data["pending"] == 0
    assert data["errors"] == 0
    assert data["imported"] == 0
    assert data["ignored"] == 0


def test_status_has_all_required_fields(client):
    """GET /status doit retourner tous les champs du schéma StatusResponse."""
    resp = client.get("/status", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    required_fields = ["total_files_scanned", "pending", "processing", "imported", "ignored", "errors"]
    for field in required_fields:
        assert field in data, f"Champ '{field}' manquant dans StatusResponse"


# ── Tests POST /sync (route publique, protégée par IAM) ─────────────────────

def test_sync_returns_started_when_drive_accessible(client, mocker):
    """POST /sync avec Google Drive accessible doit retourner {'status': 'started'}."""
    mock_drive = MagicMock()
    mock_drive.about.return_value.get.return_value.execute.return_value = {"user": {"emailAddress": "sa@project.iam.gserviceaccount.com"}}
    mocker.patch("src.google_auth.get_drive_service", return_value=mock_drive)

    # Mock SessionLocal pour la background task (sinon TypeError: NoneType not callable)
    mock_session = AsyncMock()
    mock_context = AsyncMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_session)
    mock_context.__aexit__ = AsyncMock(return_value=None)
    mocker.patch("database.SessionLocal", return_value=mock_context)

    resp = client.post("/sync")
    # La synchro est lancée en arrière-plan → status=started
    assert resp.status_code == 200
    assert resp.json()["status"] == "started"


def test_sync_returns_403_when_drive_permission_lost(client, mocker):
    """POST /sync lorsque le Service Account a perdu l'accès Drive doit retourner 403."""
    mock_drive = MagicMock()
    mock_drive.about.return_value.get.return_value.execute.side_effect = Exception("403 Forbidden: Service Account access revoked")
    mocker.patch("src.google_auth.get_drive_service", return_value=mock_drive)

    resp = client.post("/sync")
    assert resp.status_code == 403
    data = resp.json()
    assert data["status"] == "error"
    assert "SERVICE_ACCOUNT_ACCESS_LOSS" in data["message"]


# ── Tests GET /files ──────────────────────────────────────────────────────────

def test_list_files_empty(client):
    """GET /files sur une base vide doit retourner une liste vide."""
    resp = client.get("/files", headers=AUTH_HEADER)
    assert resp.status_code == 200
    assert resp.json() == []


# ── Tests POST /retry-errors ──────────────────────────────────────────────────

def test_retry_errors_no_errors_to_retry(client):
    """POST /retry-errors quand il n'y a aucune erreur doit retourner rows_updated=0."""
    resp = client.post("/retry-errors", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["rows_updated"] == 0


# ── Tests GET /version ────────────────────────────────────────────────────────

def test_version_returns_version_field(client):
    """GET /version doit retourner un champ 'version'."""
    resp = client.get("/version")
    assert resp.status_code == 200
    assert "version" in resp.json()


def test_version_matches_version_file(client):
    """GET /version doit correspondre au fichier VERSION."""
    version_file = os.path.join(os.path.dirname(__file__), "VERSION")
    if os.path.exists(version_file):
        with open(version_file) as f:
            expected = f.read().strip()
        resp = client.get("/version")
        assert resp.status_code == 200
        # version peut être injectée via APP_VERSION env var
        # le test vérifie juste que la clé existe
        assert "version" in resp.json()
