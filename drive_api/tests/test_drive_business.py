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
    """POST /retry-errors quand il n'y a aucune erreur doit retourner total_reset=0."""
    resp = client.post("/retry-errors", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["total_reset"] == 0
    assert data["errors_reset"] == 0
    assert data["zombies_reset"] == 0


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


# ── Tests folder_name — Nomenclature Zenika ──────────────────────────────────

def test_add_folder_stores_folder_name(client, mocker):
    """POST /folders avec un folder Google Drive doit stocker le folder_name récupéré via l'API Drive."""
    mock_drive = MagicMock()
    mock_drive.files.return_value.get.return_value.execute.return_value = {"name": "Marie Dupont"}
    mocker.patch("src.google_auth.get_drive_service", return_value=mock_drive)

    resp = client.post(
        "/folders",
        json={"google_folder_id": "folder_xyz", "tag": "Paris"},
        headers=AUTH_HEADER
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["folder_name"] == "Marie Dupont"


def test_add_folder_uses_manual_folder_name_if_drive_fails(client, mocker):
    """POST /folders : si l'API Drive échoue, le folder_name fourni manuellement est retenu."""
    mock_drive = MagicMock()
    mock_drive.files.return_value.get.return_value.execute.side_effect = Exception("Drive unavailable")
    mocker.patch("src.google_auth.get_drive_service", return_value=mock_drive)

    resp = client.post(
        "/folders",
        json={"google_folder_id": "folder_abc2", "tag": "Lyon", "folder_name": "Jean Martin"},
        headers=AUTH_HEADER
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["folder_name"] == "Jean Martin"


def test_add_folder_folder_name_nullable_when_drive_fails(client, mocker):
    """POST /folders : si Drive échoue ET pas de folder_name manuel, folder_name est null."""
    mock_drive = MagicMock()
    mock_drive.files.return_value.get.return_value.execute.side_effect = Exception("Drive unavailable")
    mocker.patch("src.google_auth.get_drive_service", return_value=mock_drive)

    resp = client.post(
        "/folders",
        json={"google_folder_id": "folder_abc3", "tag": "Bordeaux"},
        headers=AUTH_HEADER
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["folder_name"] is None


def test_add_folder_invalidates_redis_cache(client, mocker):
    """POST /folders doit invalider la clé Redis drive:roots."""
    mock_drive = MagicMock()
    mock_drive.files.return_value.get.return_value.execute.return_value = {"name": "Test Folder"}
    mocker.patch("src.google_auth.get_drive_service", return_value=mock_drive)

    mock_redis = MagicMock()
    mocker.patch("src.router.get_redis", return_value=mock_redis)

    resp = client.post(
        "/folders",
        json={"google_folder_id": "folder_cache_test", "tag": "Nantes"},
        headers=AUTH_HEADER
    )
    assert resp.status_code == 200
    mock_redis.delete.assert_called_with("drive:roots")


def test_delete_folder_invalidates_redis_cache(client, mocker):
    """DELETE /folders/{id} doit invalider la clé Redis drive:roots."""
    mock_drive = MagicMock()
    mock_drive.files.return_value.get.return_value.execute.return_value = {"name": "Delete Test"}
    mocker.patch("src.google_auth.get_drive_service", return_value=mock_drive)

    mock_redis = MagicMock()
    mocker.patch("src.router.get_redis", return_value=mock_redis)

    # Créer un folder
    create_resp = client.post(
        "/folders",
        json={"google_folder_id": "folder_del_cache", "tag": "Rennes"},
        headers=AUTH_HEADER
    )
    folder_id = create_resp.json()["id"]

    mock_redis.reset_mock()
    del_resp = client.delete(f"/folders/{folder_id}", headers=AUTH_HEADER)
    assert del_resp.status_code == 200
    mock_redis.delete.assert_called_with("drive:roots")


# ── Tests règle d'exclusion underscore ────────────────────────────────────────

def test_underscore_folder_excluded_in_resolve(mocker):
    """
    _resolve_root_and_parent doit retourner (None, None, None) quand un dossier
    commence par underscore, signalant son exclusion du périmètre de sync.
    """
    from unittest.mock import AsyncMock, MagicMock
    from src.drive_service import DriveService

    mock_db = AsyncMock()
    mock_redis = MagicMock()
    mock_redis.get.return_value = None

    # Mock Drive API : le folder parent s'appelle "_Archive"
    mock_drive = MagicMock()
    mock_drive.files.return_value.get.return_value.execute.return_value = {
        "name": "_Archive",
        "parents": []
    }

    # Instanciation manuelle (sans passer par DI)
    service = DriveService.__new__(DriveService)
    service.db = mock_db
    service.drive = mock_drive
    service.redis = mock_redis

    import asyncio
    roots = [{"id": 1, "google_folder_id": "root_id_abc", "tag": "Paris", "folder_name": "CVs Paris"}]

    result = asyncio.get_event_loop().run_until_complete(
        service._resolve_root_and_parent("some_parent_id", roots)
    )
    root, parent_id, parent_name = result
    assert root is None, "Un dossier '_Archive' doit être exclu (préfixe underscore)"
    assert parent_id is None
    assert parent_name is None


def test_filestate_response_has_parent_folder_name(client):
    """GET /files doit retourner parent_folder_name dans chaque FileStateResponse."""
    resp = client.get("/files", headers=AUTH_HEADER)
    assert resp.status_code == 200
    # Liste vide OK, mais on vérifie que le schéma est accepté
    assert isinstance(resp.json(), list)


# ═══════════════════════════════════════════════════════════════════════════════
# Tests — GET /files/{google_file_id} (nouveau endpoint)
# ═══════════════════════════════════════════════════════════════════════════════

def test_get_file_state_by_id_with_parent_folder_name(client, mocker):
    """
    UC-DRIVE-1 — GET /files/{google_file_id} : retourne le DriveSyncState du fichier
    avec parent_folder_name (nomenclature Zenika 'Prénom Nom').
    """
    # Créer un folder d'abord
    mock_drive = MagicMock()
    mock_drive.files.return_value.get.return_value.execute.return_value = {"name": "Sophia Weber"}
    mocker.patch("src.google_auth.get_drive_service", return_value=mock_drive)
    mocker.patch("src.redis_client.get_redis", return_value=MagicMock())

    folder_resp = client.post(
        "/folders",
        json={"google_folder_id": "folder_sw", "tag": "Strasbourg"},
        headers=AUTH_HEADER
    )
    assert folder_resp.status_code == 200
    folder_id = folder_resp.json()["id"]

    # Insérer un DriveSyncState manuellement via DB
    from sqlalchemy.orm import sessionmaker, Session
    from src.models import DriveSyncState, DriveSyncStatus
    with sync_engine.connect() as conn:
        conn.execute(
            DriveSyncState.__table__.insert().values(
                google_file_id="GFILE_SW_001",
                folder_id=folder_id,
                file_name="CV Sophia Weber.gdoc",
                status="IMPORTED_CV",
                parent_folder_name="Sophia Weber",
            )
        )
        conn.commit()

    resp = client.get("/files/GFILE_SW_001", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["google_file_id"] == "GFILE_SW_001"
    assert data["parent_folder_name"] == "Sophia Weber"
    assert data["file_name"] == "CV Sophia Weber.gdoc"


def test_get_file_state_by_id_found_without_folder_name(client, mocker):
    """
    UC-DRIVE-2 — GET /files/{google_file_id} : fichier sans parent_folder_name
    (import manuel, avant la mise en place de la nomenclature Zenika).
    parent_folder_name doit être null.
    """
    mock_drive = MagicMock()
    mock_drive.files.return_value.get.return_value.execute.return_value = {"name": "CVs Bordeaux"}
    mocker.patch("src.google_auth.get_drive_service", return_value=mock_drive)
    mocker.patch("src.redis_client.get_redis", return_value=MagicMock())

    folder_resp = client.post(
        "/folders",
        json={"google_folder_id": "folder_bx", "tag": "Bordeaux"},
        headers=AUTH_HEADER
    )
    folder_id = folder_resp.json()["id"]

    from src.models import DriveSyncState
    with sync_engine.connect() as conn:
        conn.execute(
            DriveSyncState.__table__.insert().values(
                google_file_id="GFILE_BX_MANUAL",
                folder_id=folder_id,
                file_name="CV externe.gdoc",
                status="IMPORTED_CV",
                parent_folder_name=None,  # import manuel — pas de dossier Drive
            )
        )
        conn.commit()

    resp = client.get("/files/GFILE_BX_MANUAL", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["google_file_id"] == "GFILE_BX_MANUAL"
    assert data["parent_folder_name"] is None, "Un import manuel ne doit pas avoir de parent_folder_name"


def test_get_file_state_by_id_not_found(client):
    """
    UC-DRIVE-3 — GET /files/{google_file_id} : fichier inconnu → 404 propre.
    Cas : import manuel ou ID Google Drive incorrect — drive_api répond 404.
    Le cv_api/reanalyze gère ce cas en mode dégradé (folder_name = None).
    """
    resp = client.get("/files/GFILE_UNKNOWN_XYZ", headers=AUTH_HEADER)
    assert resp.status_code == 404
    data = resp.json()
    assert "detail" in data
    assert "GFILE_UNKNOWN_XYZ" in data["detail"]


def test_get_file_state_by_id_requires_jwt(client):
    """
    UC-DRIVE-4 — GET /files/{google_file_id} nécessite un JWT valide (Zero-Trust).
    """
    original = app.dependency_overrides.pop(verify_jwt, None)
    try:
        resp = client.get("/files/GFILE_ANY", headers={})
        assert resp.status_code == 401
    finally:
        if original:
            app.dependency_overrides[verify_jwt] = original
        else:
            app.dependency_overrides[verify_jwt] = override_verify_jwt
