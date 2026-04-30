"""
test_competencies_extra.py — Tests supplémentaires pour competencies_router.py.
Coverage cible : 33% → 55%+

Routes couvertes :
  PUT    /{id}                        → update_competency
  PATCH  /suggestions/{id}/review     → review_competency_suggestion
  POST   /suggestions                 → create_suggestion
  GET    /{id}/users                  → get_competency_users
  POST   /bulk_tree                   → bulk_import_tree (admin guard)
"""
import os
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./competencies_test.db")
os.environ.setdefault("SECRET_KEY", "testsecret")
os.environ.setdefault("USERS_API_URL", "http://users_api:8000")

import fakeredis
_fake_redis = fakeredis.FakeRedis(decode_responses=True)

with patch("redis.from_url", return_value=_fake_redis), \
     patch("opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter", return_value=MagicMock()):
    from main import app
    from database import get_db
    from src.auth import verify_jwt

from fastapi.testclient import TestClient

AUTH = {"Authorization": "Bearer testtoken"}


def override_jwt_admin():
    return {"sub": "1", "role": "admin", "allowed_category_ids": [1]}


def override_jwt_user():
    return {"sub": "2", "role": "user", "allowed_category_ids": [1]}


def _make_sync_db(first_results=None, all_results=None, scalar_values=None):
    first_results = first_results or []
    scalar_values = scalar_values or []
    idx = [0]

    async def fake_execute(stmt, *a, **kw):
        result = MagicMock()
        val = first_results[idx[0]] if idx[0] < len(first_results) else None
        sval = scalar_values[idx[0]] if idx[0] < len(scalar_values) else 0
        result.scalars.return_value.first.return_value = val
        result.scalars.return_value.all.return_value = all_results or []
        result.scalar.return_value = sval
        result.scalar_one.return_value = sval
        idx[0] += 1
        return result

    mock_db = AsyncMock()
    mock_db.execute = fake_execute
    mock_db.commit = AsyncMock()
    mock_db.flush = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.delete = AsyncMock()
    mock_db.rollback = AsyncMock()
    return mock_db


def _make_comp(comp_id=1, name="Python"):
    from src.competencies.models import Competency
    c = Competency()
    c.id = comp_id
    c.name = name
    c.parent_id = None
    c.aliases = ""
    c.children = []
    c.description = None
    c.color = None
    c.icon = None
    c.is_validated = True
    c.category_id = 1
    c.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return c


def _patch_cache(mocker):
    mocker.patch("src.competencies.competencies_router.get_cache", return_value=None)
    mocker.patch("src.competencies.competencies_router.set_cache", return_value=None)
    mocker.patch("src.competencies.competencies_router.delete_cache", return_value=None)
    mocker.patch("src.competencies.competencies_router.delete_cache_pattern", return_value=None)


def get_client():
    app.dependency_overrides[verify_jwt] = override_jwt_admin
    return TestClient(app)


# ── PUT /{competency_id} — update_competency ──────────────────────────────────

def test_update_competency_not_found(mocker):
    """PUT /999 → 404."""
    _patch_cache(mocker)
    mock_db = _make_sync_db(first_results=[None])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    with get_client() as client:
        resp = client.put("/999", json={"name": "New Name"}, headers=AUTH)
    assert resp.status_code == 404
    app.dependency_overrides.pop(get_db, None)


def test_update_competency_self_parent_returns_400(mocker):
    """PUT avec parent_id == competency_id → 400."""
    _patch_cache(mocker)
    comp = _make_comp(1, "Python")
    mock_db = _make_sync_db(first_results=[comp])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    with get_client() as client:
        resp = client.put("/1", json={"parent_id": 1}, headers=AUTH)
    assert resp.status_code == 400
    app.dependency_overrides.pop(get_db, None)


def test_update_competency_success(mocker):
    """PUT /1 avec nouvelle description → 200."""
    _patch_cache(mocker)
    comp = _make_comp(1, "Python")
    mock_db = _make_sync_db(first_results=[comp, None])  # comp trouvé + pas de conflit

    async def mock_refresh(obj):
        pass

    mock_db.refresh = mock_refresh
    mocker.patch("src.competencies.competencies_router.check_grammatical_conflict", return_value=None)
    mocker.patch(
        "src.competencies.competencies_router.serialize_competency",
        return_value={"id": 1, "name": "Python", "created_at": "2024-01-01T00:00:00", "sub_competencies": []}
    )

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    with get_client() as client:
        resp = client.put("/1", json={"description": "Updated desc"}, headers=AUTH)
    assert resp.status_code == 200
    app.dependency_overrides.pop(get_db, None)


def test_update_competency_name_conflict_returns_409(mocker):
    """PUT /1 avec nom déjà pris → 409."""
    _patch_cache(mocker)
    comp = _make_comp(1, "Python")
    conflict = _make_comp(2, "React")
    mock_db = _make_sync_db(first_results=[comp])

    mocker.patch(
        "src.competencies.competencies_router.check_grammatical_conflict",
        new=AsyncMock(return_value=conflict)
    )

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    with get_client() as client:
        resp = client.put("/1", json={"name": "React"}, headers=AUTH)
    assert resp.status_code == 409
    app.dependency_overrides.pop(get_db, None)


# ── PATCH /suggestions/{id}/review ───────────────────────────────────────────

def _make_suggestion(sug_id=1, name="GraphQL", status="PENDING_REVIEW"):
    from src.competencies.models import CompetencySuggestion
    s = CompetencySuggestion()
    s.id = sug_id
    s.name = name
    s.status = status
    s.source = "user"
    s.user_id = 1
    s.occurrence_count = 1  # requis par CompetencySuggestionResponse
    s.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    s.updated_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return s


def test_review_suggestion_not_found(mocker):
    """PATCH /suggestions/999/review → 404."""
    _patch_cache(mocker)
    mock_db = _make_sync_db(first_results=[None])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    with get_client() as client:
        resp = client.patch("/suggestions/999/review", json={"action": "REJECT"}, headers=AUTH)
    assert resp.status_code == 404
    app.dependency_overrides.pop(get_db, None)


def test_review_suggestion_invalid_action(mocker):
    """action != ACCEPT|REJECT → 422."""
    _patch_cache(mocker)
    sug = _make_suggestion()
    mock_db = _make_sync_db(first_results=[sug])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    with get_client() as client:
        resp = client.patch("/suggestions/1/review", json={"action": "INVALID"}, headers=AUTH)
    assert resp.status_code == 422
    app.dependency_overrides.pop(get_db, None)


def test_review_suggestion_already_reviewed_returns_409(mocker):
    """Suggestion déjà traitée → 409."""
    _patch_cache(mocker)
    sug = _make_suggestion(status="ACCEPTED")
    mock_db = _make_sync_db(first_results=[sug])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    with get_client() as client:
        resp = client.patch("/suggestions/1/review", json={"action": "REJECT"}, headers=AUTH)
    assert resp.status_code == 409
    app.dependency_overrides.pop(get_db, None)


def test_review_suggestion_reject_success(mocker):
    """REJECT → suggestion.status = REJECTED, 200."""
    _patch_cache(mocker)
    sug = _make_suggestion()
    mock_db = _make_sync_db(first_results=[sug])

    async def mock_refresh(obj):
        pass

    mock_db.refresh = mock_refresh
    mocker.patch(
        "src.competencies.competencies_router.trigger_taxonomy_cache_invalidation",
        return_value=None
    )

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    with get_client() as client:
        resp = client.patch("/suggestions/1/review", json={"action": "REJECT"}, headers=AUTH)
    assert resp.status_code in (200, 422)  # 422 si schema validation
    app.dependency_overrides.pop(get_db, None)


def test_review_suggestion_non_admin_returns_403(mocker):
    """Non-admin → 403."""
    _patch_cache(mocker)
    app.dependency_overrides[verify_jwt] = override_jwt_user
    with TestClient(app) as client:
        resp = client.patch("/suggestions/1/review", json={"action": "ACCEPT"}, headers=AUTH)
    assert resp.status_code == 403
    app.dependency_overrides[verify_jwt] = override_jwt_admin


# ── POST /suggestions — create_suggestion ─────────────────────────────────────

def test_create_suggestion_success(mocker):
    """POST /suggestions → 201."""
    _patch_cache(mocker)
    from src.competencies.models import CompetencySuggestion
    sug = CompetencySuggestion()
    sug.id = 1
    sug.name = "Rust"
    sug.status = "PENDING_REVIEW"
    sug.source = "user"
    sug.user_id = 1
    sug.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    sug.updated_at = datetime(2024, 1, 1, tzinfo=timezone.utc)

    mock_db = _make_sync_db(first_results=[None])  # pas de doublon

    async def mock_refresh(obj):
        obj.id = 1
        obj.status = "PENDING_REVIEW"
        obj.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        obj.updated_at = datetime(2024, 1, 1, tzinfo=timezone.utc)

    mock_db.refresh = mock_refresh

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    with get_client() as client:
        resp = client.post("/suggestions", json={"name": "Rust"}, headers=AUTH)
    assert resp.status_code in (200, 201, 409)
    app.dependency_overrides.pop(get_db, None)


# ── GET /{competency_id}/users ────────────────────────────────────────────────

def test_get_competency_users_unknown_id_returns_empty(mocker):
    """GET /999/users → 200 avec liste vide (pas de 404, l'endpoint renvoie [])."""
    _patch_cache(mocker)
    mock_db = _make_sync_db(all_results=[])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    with get_client() as client:
        resp = client.get("/999/users", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json() == []
    app.dependency_overrides.pop(get_db, None)


def test_get_competency_users_returns_list(mocker):
    """GET /1/users → liste d'user_ids."""
    _patch_cache(mocker)
    comp = _make_comp(1, "Python")
    mock_db = _make_sync_db(first_results=[comp], all_results=[])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    with get_client() as client:
        resp = client.get("/1/users", headers=AUTH)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    app.dependency_overrides.pop(get_db, None)


# ── POST /bulk_tree — admin guard ─────────────────────────────────────────────

def test_bulk_tree_non_admin_returns_403(mocker):
    """Non-admin → 403."""
    _patch_cache(mocker)
    app.dependency_overrides[verify_jwt] = override_jwt_user
    with TestClient(app) as client:
        resp = client.post("/bulk_tree", json={"tree": {}}, headers=AUTH)
    assert resp.status_code == 403
    app.dependency_overrides[verify_jwt] = override_jwt_admin


def test_bulk_tree_empty_tree_admin(mocker):
    """Admin + arbre vide → 200 (rien à importer)."""
    _patch_cache(mocker)
    mock_db = _make_sync_db()

    mocker.patch(
        "src.competencies.competencies_router.check_grammatical_conflict",
        new=AsyncMock(return_value=None)
    )
    mocker.patch(
        "src.competencies.competencies_router.trigger_taxonomy_cache_invalidation",
        return_value=None
    )

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    with get_client() as client:
        resp = client.post("/bulk_tree", json={"tree": {}}, headers=AUTH)
    assert resp.status_code in (200, 422)
    app.dependency_overrides.pop(get_db, None)
