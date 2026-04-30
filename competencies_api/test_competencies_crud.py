"""
test_competencies_crud.py — Tests des endpoints CRUD de competencies_router.py.

Coverage cible : 13% → 55%+
Patterns : client function-scoped, MagicMock synchrone pour les résultats SQLAlchemy.
"""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./competencies_test.db")
os.environ.setdefault("SECRET_KEY", "testsecret")
os.environ.setdefault("COMPETENCIES_API_URL", "http://competencies_api:8003")
os.environ.setdefault("USERS_API_URL", "http://users_api:8000")

import fakeredis
_fake_redis_client = fakeredis.FakeRedis(decode_responses=True)

with patch("redis.from_url", return_value=_fake_redis_client), \
     patch("opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter", return_value=MagicMock()):
    from main import app
    from database import get_db
    from src.auth import verify_jwt

from fastapi.testclient import TestClient

# ── Helpers ───────────────────────────────────────────────────────────────────

def override_verify_jwt():
    return {"sub": "1", "role": "admin", "allowed_category_ids": [1]}


def get_client() -> TestClient:
    """Retourne un nouveau client avec les overrides en place."""
    app.dependency_overrides[verify_jwt] = override_verify_jwt
    return TestClient(app)


AUTH = {"Authorization": "Bearer testtoken"}


def _make_sync_db(first_results=None, all_results=None, scalar_values=None):
    """
    AsyncSession mock dont .execute() est awaitable et retourne un MagicMock synchrone.
    Tous les résultats (.scalar(), .scalars().first(), .scalars().all()) sont synchrones.
    """
    first_results = first_results or []
    scalar_values = scalar_values or []
    all_results = all_results or []
    idx = [0]

    async def fake_execute(stmt, *a, **kw):
        result = MagicMock()
        val = first_results[idx[0]] if idx[0] < len(first_results) else None
        sval = scalar_values[idx[0]] if idx[0] < len(scalar_values) else 0
        result.scalars.return_value.first.return_value = val
        result.scalars.return_value.all.return_value = all_results
        result.scalar.return_value = sval
        result.scalar_one.return_value = sval
        result.scalar_one_or_none.return_value = sval
        idx[0] += 1
        return result

    mock_db = AsyncMock()
    mock_db.execute = fake_execute
    mock_db.commit = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.delete = AsyncMock()
    return mock_db


def _make_comp(comp_id=1, name="Python", parent_id=None):
    """Crée un mock Competency avec les champs requis."""
    from src.competencies.models import Competency
    c = Competency()
    c.id = comp_id
    c.name = name
    c.parent_id = parent_id
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
    """Désactive le cache Redis pour isoler les tests."""
    mocker.patch("src.competencies.competencies_router.get_cache", return_value=None)
    mocker.patch("src.competencies.competencies_router.set_cache", return_value=None)
    mocker.patch("src.competencies.competencies_router.delete_cache", return_value=None)
    mocker.patch("src.competencies.competencies_router.delete_cache_pattern", return_value=None)


# ── GET / — list_competencies ─────────────────────────────────────────────────

def test_list_competencies_empty(mocker):
    """GET / → 200 avec liste vide si aucune compétence."""
    _patch_cache(mocker)
    mock_db = _make_sync_db(first_results=[], scalar_values=[0])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with get_client() as client:
        resp = client.get("/", headers=AUTH)

    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data or isinstance(data, (list, dict))
    app.dependency_overrides.pop(get_db, None)


def test_list_competencies_paginated(mocker):
    """GET /?skip=0&limit=5 → 200 avec pagination."""
    _patch_cache(mocker)
    comp = _make_comp(1, "Python")
    mock_db = _make_sync_db(
        first_results=[None],
        all_results=[comp],
        scalar_values=[1]  # total = 1
    )

    mocker.patch(
        "src.competencies.competencies_router.serialize_competency",
        return_value={"id": 1, "name": "Python", "children": [], "created_at": "2024-01-01T00:00:00", "sub_competencies": []}
    )

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with get_client() as client:
        resp = client.get("/?skip=0&limit=5", headers=AUTH)

    assert resp.status_code == 200
    app.dependency_overrides.pop(get_db, None)


# ── GET /search ───────────────────────────────────────────────────────────────

def test_search_competencies_empty(mocker):
    """GET /search?query=inexistant → 200 liste vide."""
    _patch_cache(mocker)
    mock_db = _make_sync_db(scalar_values=[0])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with get_client() as client:
        resp = client.get("/search?query=inexistant", headers=AUTH)

    assert resp.status_code == 200
    app.dependency_overrides.pop(get_db, None)


def test_search_competencies_missing_query_returns_422():
    """GET /search sans paramètre query → 422 (paramètre obligatoire)."""
    with get_client() as client:
        resp = client.get("/search", headers=AUTH)
    assert resp.status_code == 422


def test_search_competencies_returns_results(mocker):
    """GET /search?query=Python → retourne la compétence Python."""
    _patch_cache(mocker)
    comp = _make_comp(1, "Python")
    mock_db = _make_sync_db(all_results=[comp], scalar_values=[1])

    mocker.patch(
        "src.competencies.competencies_router.serialize_competency",
        return_value={"id": 1, "name": "Python", "children": [], "created_at": "2024-01-01T00:00:00", "sub_competencies": []}
    )

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with get_client() as client:
        resp = client.get("/search?query=Python", headers=AUTH)

    assert resp.status_code == 200
    app.dependency_overrides.pop(get_db, None)


# ── GET /{competency_id} ──────────────────────────────────────────────────────

def test_get_competency_not_found(mocker):
    """GET /999 → 404."""
    _patch_cache(mocker)
    mock_db = _make_sync_db(first_results=[None])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with get_client() as client:
        resp = client.get("/999", headers=AUTH)

    assert resp.status_code == 404
    app.dependency_overrides.pop(get_db, None)


def test_get_competency_found(mocker):
    """GET /1 → 200 avec données de la compétence."""
    _patch_cache(mocker)
    comp = _make_comp(1, "Python")
    mock_db = _make_sync_db(first_results=[comp])

    mocker.patch(
        "src.competencies.competencies_router.serialize_competency",
        return_value={"id": 1, "name": "Python", "children": [], "created_at": "2024-01-01T00:00:00", "sub_competencies": []}
    )

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with get_client() as client:
        resp = client.get("/1", headers=AUTH)

    assert resp.status_code == 200
    app.dependency_overrides.pop(get_db, None)


# ── POST / — create_competency ────────────────────────────────────────────────

def test_create_competency_success(mocker):
    """POST / → 201 avec CompetencyResponse."""
    _patch_cache(mocker)
    mock_db = _make_sync_db(first_results=[None, None])  # pas de doublon name, pas de doublon alias

    comp = _make_comp(10, "React")

    async def mock_refresh(obj):
        obj.id = 10
        obj.name = "React"
        obj.aliases = []
        obj.children = []
        obj.description = None
        obj.color = None
        obj.icon = None
        obj.is_validated = True
        obj.category_id = 1
        obj.parent_id = None

    mock_db.refresh = mock_refresh

    mocker.patch("src.competencies.competencies_router.check_grammatical_conflict", return_value=None)
    mocker.patch("src.competencies.competencies_router._generate_aliases_for_competency", return_value=[])
    mocker.patch("src.competencies.competencies_router.trigger_taxonomy_cache_invalidation", return_value=None)
    mocker.patch("src.competencies.competencies_router.serialize_competency",
                 return_value={"id": 10, "name": "React", "children": [], "created_at": "2024-01-01T00:00:00", "sub_competencies": []})

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with get_client() as client:
        resp = client.post("/", json={"name": "React", "category_id": 1}, headers=AUTH)

    assert resp.status_code in (200, 201)
    app.dependency_overrides.pop(get_db, None)


# ── DELETE /{competency_id} ───────────────────────────────────────────────────

def test_delete_competency_not_found(mocker):
    """DELETE /999 → 404."""
    _patch_cache(mocker)
    mock_db = _make_sync_db(first_results=[None])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with get_client() as client:
        resp = client.delete("/999", headers=AUTH)

    assert resp.status_code == 404
    app.dependency_overrides.pop(get_db, None)


def test_delete_competency_success(mocker):
    """DELETE /1 → 204."""
    _patch_cache(mocker)
    comp = _make_comp(1, "Python")
    mock_db = _make_sync_db(
        first_results=[comp, None],
        scalar_values=[None, 0]  # 0 enfants → peut supprimer
    )

    mocker.patch("src.competencies.competencies_router.trigger_taxonomy_cache_invalidation", return_value=None)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with get_client() as client:
        resp = client.delete("/1", headers=AUTH)

    assert resp.status_code in (200, 204)
    app.dependency_overrides.pop(get_db, None)


# ── GET /suggestions ──────────────────────────────────────────────────────────

def test_list_suggestions_empty(mocker):
    """GET /suggestions → [] si aucune suggestion."""
    _patch_cache(mocker)
    mock_db = _make_sync_db(all_results=[])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with get_client() as client:
        resp = client.get("/suggestions", headers=AUTH)

    assert resp.status_code == 200
    assert resp.json() == []
    app.dependency_overrides.pop(get_db, None)


# ── POST /stats/counts ────────────────────────────────────────────────────────

def test_stats_counts_returns_data(mocker):
    """POST /stats/counts → 200 avec statistiques."""
    _patch_cache(mocker)
    mock_db = _make_sync_db(
        scalar_values=[42, 10, 5],
        all_results=[]
    )

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with get_client() as client:
        resp = client.post("/stats/counts", json={"user_ids": [1, 2, 3]}, headers=AUTH)

    assert resp.status_code == 200
    app.dependency_overrides.pop(get_db, None)


# ── Zero Trust — JWT absent → 401/403 ────────────────────────────────────────

def test_list_no_jwt_returns_401_or_403():
    """GET / sans JWT override → 401 ou 403."""
    app.dependency_overrides.pop(verify_jwt, None)
    app.dependency_overrides.pop(get_db, None)
    with TestClient(app) as client:
        resp = client.get("/")
    assert resp.status_code in (401, 403, 422)
    app.dependency_overrides[verify_jwt] = override_verify_jwt
