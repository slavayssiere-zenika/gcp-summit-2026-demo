"""
test_folders.py — Tests des endpoints /folders de drive_api.

Coverage cible : 27% → 65%+
Endpoints testés :
  POST   /folders            → duplicate 400 + admin guard 403
  GET    /folders            → list empty + items
  DELETE /folders/{id}       → 404 + 200/204
  POST   /folders/invalidate-cache → purge Redis
  POST   /folders/reset-sync       → idempotent
"""
import os
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./drive_test.db")
os.environ.setdefault("SECRET_KEY", "testsecret")
os.environ.setdefault("USERS_API_URL", "http://users-api:8000")

with patch("opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter", return_value=MagicMock()):
    from main import app
    from database import get_db
    from src.auth import verify_jwt

from fastapi.testclient import TestClient

def override_verify_jwt_admin():
    return {"sub": "admin1", "email": "admin@zenika.com", "role": "admin"}

async def override_get_db():
    db = AsyncMock()
    # Retourne un objet dont .scalars().all() / .scalars().first() sont sync
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.scalars.return_value.first.return_value = None
    db.execute = AsyncMock(return_value=result)
    yield db

app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[verify_jwt] = override_verify_jwt_admin

client = TestClient(app)
AUTH = {"Authorization": "Bearer testtoken"}


def _make_sync_db(first_results=None, all_results=None, rowcount=0, scalar_values=None):
    """
    Construit un AsyncSession mock dont execute() est awaitable
    et retourne un résultat synchrone (MagicMock).
    scalar_values: liste de valeurs retournées par .scalar() dans l'ordre des appels.
    """
    first_results = first_results or []
    scalar_values = scalar_values or []
    idx = [0]
    scalar_idx = [0]

    async def fake_execute(stmt, *a, **kw):
        result = MagicMock()
        # .scalars().first()
        val = first_results[idx[0]] if idx[0] < len(first_results) else None
        result.scalars.return_value.first.return_value = val
        result.scalars.return_value.all.return_value = all_results or []
        result.rowcount = rowcount
        # .scalar() pour les count queries
        sval = scalar_values[scalar_idx[0]] if scalar_idx[0] < len(scalar_values) else 0
        result.scalar.return_value = sval
        result.scalar_one.return_value = sval
        result.scalar_one_or_none.return_value = sval
        idx[0] += 1
        scalar_idx[0] += 1
        return result

    mock_db = AsyncMock()
    mock_db.execute = fake_execute
    mock_db.commit = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.delete = AsyncMock()
    return mock_db


# ── POST /folders ─────────────────────────────────────────────────────────────

def test_add_folder_duplicate_google_id_returns_400(mocker):
    """Dossier déjà enregistré (même google_folder_id) → 400."""
    from src.models import DriveFolder
    existing = DriveFolder()
    existing.id = 1
    existing.google_folder_id = "abc123"
    existing.tag = "tag1"
    existing.folder_name = "Test"

    mock_db = _make_sync_db(first_results=[existing, None])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    mocker.patch("src.routers.folders_router.get_drive_service", side_effect=Exception("no drive"))

    resp = client.post("/folders", json={
        "google_folder_id": "abc123", "tag": "tag1"
    }, headers=AUTH)

    assert resp.status_code == 400
    app.dependency_overrides[get_db] = override_get_db


def test_add_folder_non_admin_returns_403():
    """Utilisateur non-admin → 403."""
    def override_user():
        return {"sub": "1", "email": "u@z.com", "role": "user"}

    app.dependency_overrides[verify_jwt] = override_user

    resp = client.post("/folders", json={
        "google_folder_id": "xyz", "tag": "t"
    }, headers=AUTH)

    assert resp.status_code == 403
    app.dependency_overrides[verify_jwt] = override_verify_jwt_admin


def test_add_folder_success(mocker):
    """Nouveau dossier (aucun existant) → 200/201."""
    from src.models import DriveFolder
    from datetime import datetime, timezone

    mock_db = _make_sync_db(first_results=[None, None])

    async def mock_refresh(obj):
        obj.id = 42
        obj.folder_name = "Test Folder"
        obj.excluded_folders = None
        obj.created_at = datetime.now(timezone.utc)

    mock_db.refresh = mock_refresh

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    mock_drive = MagicMock()
    mock_drive.files.return_value.get.return_value.execute.return_value = {"name": "Test Folder"}
    mocker.patch("src.routers.folders_router.get_drive_service", return_value=mock_drive)
    mocker.patch("src.routers.folders_router.get_redis", return_value=MagicMock())

    resp = client.post("/folders", json={
        "google_folder_id": "newid", "tag": "new-tag"
    }, headers=AUTH)

    assert resp.status_code in (200, 201)
    app.dependency_overrides[get_db] = override_get_db


# ── GET /folders ──────────────────────────────────────────────────────────────

def test_list_folders_empty():
    """GET /folders → [] si aucun dossier."""
    mock_db = _make_sync_db(all_results=[])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    resp = client.get("/folders", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json() == []
    app.dependency_overrides[get_db] = override_get_db


def test_list_folders_returns_items():
    """GET /folders → liste des dossiers enregistrés."""
    from src.models import DriveFolder
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    f1 = DriveFolder()
    f1.id = 1
    f1.google_folder_id = "abc"
    f1.tag = "t1"
    f1.folder_name = "Alice"
    f1.excluded_folders = None
    f1.created_at = now

    f2 = DriveFolder()
    f2.id = 2
    f2.google_folder_id = "def"
    f2.tag = "t2"
    f2.folder_name = "Bob"
    f2.excluded_folders = None
    f2.created_at = now

    mock_db = _make_sync_db(all_results=[f1, f2])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    resp = client.get("/folders", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    app.dependency_overrides[get_db] = override_get_db


# ── DELETE /folders/{folder_id} ───────────────────────────────────────────────

def test_delete_folder_not_found():
    """DELETE /folders/999 → 404."""
    mock_db = _make_sync_db(first_results=[None])  # pas de dossier

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    resp = client.delete("/folders/999", headers=AUTH)
    assert resp.status_code == 404
    app.dependency_overrides[get_db] = override_get_db


def test_delete_folder_success(mocker):
    """DELETE /folders/1 → 200/204 si trouvé."""
    from src.models import DriveFolder
    folder = DriveFolder()
    folder.id = 1
    folder.google_folder_id = "abc123"
    folder.tag = "t1"

    # Premier execute → folder trouvé, Deuxième → files_count = 0
    mock_db = _make_sync_db(first_results=[folder, None], scalar_values=[None, 0])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    mocker.patch("src.routers.folders_router.get_redis", return_value=MagicMock())

    resp = client.delete("/folders/1", headers=AUTH)
    assert resp.status_code in (200, 204)
    app.dependency_overrides[get_db] = override_get_db


def test_delete_folder_non_admin_returns_403():
    """DELETE sans droit admin → 403."""
    def override_user():
        return {"sub": "1", "email": "u@z.com", "role": "user"}

    app.dependency_overrides[verify_jwt] = override_user
    resp = client.delete("/folders/1", headers=AUTH)
    assert resp.status_code == 403
    app.dependency_overrides[verify_jwt] = override_verify_jwt_admin


# ── POST /folders/invalidate-cache ────────────────────────────────────────────

def test_invalidate_cache_success(mocker):
    """POST /folders/invalidate-cache → 200 avec keys_deleted."""
    mock_redis = MagicMock()
    mock_redis.scan_iter.return_value = []  # pas de clés matchantes
    mock_redis.delete.return_value = True
    mocker.patch("src.routers.folders_router.get_redis", return_value=mock_redis)

    resp = client.post("/folders/invalidate-cache", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert "keys_deleted" in data or "status" in data


def test_invalidate_cache_deletes_rebuild_lock(mocker):
    """POST /folders/invalidate-cache → supprime drive:sync:rebuild_running."""
    mock_redis = MagicMock()
    mock_redis.scan_iter.return_value = []
    mocker.patch("src.routers.folders_router.get_redis", return_value=mock_redis)

    resp = client.post("/folders/invalidate-cache", headers=AUTH)
    assert resp.status_code == 200
    # Vérifie que delete a été appelé (pour le verrou rebuild)
    mock_redis.delete.assert_called()


def test_invalidate_cache_non_admin_returns_403():
    """Utilisateur non-admin → 403."""
    def override_user():
        return {"sub": "1", "email": "u@z.com", "role": "user"}

    app.dependency_overrides[verify_jwt] = override_user
    resp = client.post("/folders/invalidate-cache", headers=AUTH)
    assert resp.status_code == 403
    app.dependency_overrides[verify_jwt] = override_verify_jwt_admin


# ── POST /folders/reset-sync ──────────────────────────────────────────────────

def test_reset_sync_success():
    """POST /folders/reset-sync → 200 avec count réinitialisé."""
    mock_db = _make_sync_db(rowcount=5)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    resp = client.post("/folders/reset-sync", headers=AUTH)
    assert resp.status_code in (200, 202)
    app.dependency_overrides[get_db] = override_get_db


def test_reset_sync_non_admin_returns_403():
    """Non-admin → 403."""
    def override_user():
        return {"sub": "1", "email": "u@z.com", "role": "user"}

    app.dependency_overrides[verify_jwt] = override_user
    resp = client.post("/folders/reset-sync", headers=AUTH)
    assert resp.status_code == 403
    app.dependency_overrides[verify_jwt] = override_verify_jwt_admin
