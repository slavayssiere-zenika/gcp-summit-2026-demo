"""
test_admin_router.py — Couverture de src/cvs/routers/admin_router.py.

Deux endpoints couverts (lignes 30-176) :
  POST /admin/remediate-legacy
    - Succès nominal (0 profils) → {status: success, fixed_count: 0}
    - Profil sans compétences extraites → ignoré (continue)
    - Profil avec suffisamment de compétences assignées → ignoré (continue)
    - Profil nécessitant remédiation :
        * URL Drive /d/<id> → PATCH Drive réussi
        * URL Drive ?id=<id> → PATCH Drive réussi
        * URL Drive non reconnue → warning + pas de PATCH
        * PATCH Drive HTTP 4xx → log erreur mais continue
        * PATCH Drive exception réseau → log erreur mais continue
        * Mise à jour DB (UPDATE processing_errors) + commit
        * Exception réseau sur compétences → continue
    - Exception globale → HTTP 500
    - Propagation Authorization header
  POST /admin/clear-processing-errors
    - Succès nominal → {status: success, cleared_count: N}
    - Exception DB → HTTP 500 + rollback
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app
from shared.database import get_db
from src.auth import verify_admin


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_auth_headers(role="admin"):
    import jwt
    import os
    secret = os.environ.get("SECRET_KEY", "testsecret")
    token = jwt.encode({"sub": "test_admin", "role": role}, secret, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def _make_http_resp(status=200, json_data=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_data or {}
    return r


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


@pytest.fixture(autouse=True)
def override_db(mock_db):
    async def _get_db():
        yield mock_db
    app.dependency_overrides[get_db] = _get_db
    yield
    app.dependency_overrides.pop(get_db, None)


# ── POST /admin/remediate-legacy ──────────────────────────────────────────────

def test_remediate_legacy_no_profiles(client, mock_db):
    """Aucun profil en base → fixed_count=0."""
    result_mock = MagicMock()
    result_mock.fetchall.return_value = []
    mock_db.execute = AsyncMock(return_value=result_mock)

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        resp = client.post("/admin/remediate-legacy", headers=get_auth_headers())

    assert resp.status_code == 200
    assert resp.json() == {"status": "success", "fixed_count": 0}


def test_remediate_legacy_profile_no_competencies_skipped(client, mock_db):
    """Profil avec 0 compétences extraites → ignoré (nb_extracted == 0)."""
    result_mock = MagicMock()
    # (p_id, user_id, source_url, extracted_competencies)
    result_mock.fetchall.return_value = [
        (1, 10, "https://drive.google.com/d/FILE1", [])
    ]
    mock_db.execute = AsyncMock(return_value=result_mock)

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        resp = client.post("/admin/remediate-legacy", headers=get_auth_headers())

    assert resp.status_code == 200
    data = resp.json()
    assert data["fixed_count"] == 0
    mock_http.get.assert_not_called()  # Aucun appel compétences


def test_remediate_legacy_profile_enough_competencies_skipped(client, mock_db):
    """Profil avec suffisamment de compétences assignées → ignoré (continue)."""
    result_mock = MagicMock()
    result_mock.fetchall.return_value = [
        (1, 10, "https://drive.google.com/d/FILE1",
         [{"name": "Python"}, {"name": "GCP"}])
    ]
    mock_db.execute = AsyncMock(return_value=result_mock)

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=_make_http_resp(200, {"total": 5, "items": []}))
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        resp = client.post("/admin/remediate-legacy", headers=get_auth_headers())

    assert resp.status_code == 200
    assert resp.json()["fixed_count"] == 0


def test_remediate_legacy_remediation_with_drive_slash_d(client, mock_db):
    """Remédiation complète : URL Drive /d/<id> → PATCH Drive + UPDATE DB."""
    result_mock = MagicMock()
    result_mock.fetchall.return_value = [
        (1, 10, "https://drive.google.com/d/ABCDEF123",
         [{"name": "Python"}, {"name": "GCP"}])
    ]
    update_result = MagicMock()
    mock_db.execute = AsyncMock(side_effect=[result_mock, update_result])

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        # competencies: 0 assigned (< 2 extracted) → remédiation
        mock_http.get = AsyncMock(return_value=_make_http_resp(200, {"total": 0, "items": []}))
        mock_http.patch = AsyncMock(return_value=_make_http_resp(200))
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        resp = client.post(
            "/admin/remediate-legacy",
            headers={**get_auth_headers(), "Authorization": "Bearer mytoken"}
        )

    assert resp.status_code == 200
    assert resp.json()["fixed_count"] == 1
    mock_http.patch.assert_called_once()
    patch_call = mock_http.patch.call_args
    assert "ABCDEF123" in patch_call.args[0]
    mock_db.commit.assert_called()


def test_remediate_legacy_remediation_with_id_param(client, mock_db):
    """Remédiation : URL Drive ?id=<id> → PATCH Drive réussi."""
    result_mock = MagicMock()
    result_mock.fetchall.return_value = [
        (2, 20, "https://drive.google.com/open?id=XYZ789",
         [{"name": "Cloud"}])
    ]
    update_result = MagicMock()
    mock_db.execute = AsyncMock(side_effect=[result_mock, update_result])

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=_make_http_resp(200, {"total": 0, "items": []}))
        mock_http.patch = AsyncMock(return_value=_make_http_resp(200))
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        resp = client.post("/admin/remediate-legacy", headers=get_auth_headers())

    assert resp.status_code == 200
    assert resp.json()["fixed_count"] == 1
    patch_url = mock_http.patch.call_args.args[0]
    assert "XYZ789" in patch_url


def test_remediate_legacy_no_drive_id_in_url(client, mock_db):
    """URL source sans ID Drive reconnu → warning log, pas de PATCH, mais DB mise à jour."""
    result_mock = MagicMock()
    result_mock.fetchall.return_value = [
        (3, 30, "https://not-a-drive-url.com/some/path", [{"name": "Python"}])
    ]
    update_result = MagicMock()
    mock_db.execute = AsyncMock(side_effect=[result_mock, update_result])

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=_make_http_resp(200, {"total": 0, "items": []}))
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        resp = client.post("/admin/remediate-legacy", headers=get_auth_headers())

    assert resp.status_code == 200
    # PATCH non appelé car pas d'ID Drive
    mock_http.patch.assert_not_called()
    # DB mise à jour quand même
    assert resp.json()["fixed_count"] == 1


def test_remediate_legacy_drive_patch_http_error(client, mock_db):
    """PATCH Drive retourne HTTP 4xx → log erreur, mais le traitement continue."""
    result_mock = MagicMock()
    result_mock.fetchall.return_value = [
        (4, 40, "https://drive.google.com/d/FAILFILE",
         [{"name": "Python"}])
    ]
    update_result = MagicMock()
    mock_db.execute = AsyncMock(side_effect=[result_mock, update_result])

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=_make_http_resp(200, {"total": 0, "items": []}))
        mock_http.patch = AsyncMock(return_value=_make_http_resp(403))  # Erreur Drive
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        resp = client.post("/admin/remediate-legacy", headers=get_auth_headers())

    assert resp.status_code == 200
    # Malgré l'erreur Drive, la DB est quand même mise à jour
    assert resp.json()["fixed_count"] == 1


def test_remediate_legacy_drive_patch_network_error(client, mock_db):
    """Exception réseau lors du PATCH Drive → log erreur mais continue."""
    result_mock = MagicMock()
    result_mock.fetchall.return_value = [
        (5, 50, "https://drive.google.com/d/NETFAIL", [{"name": "Python"}])
    ]
    update_result = MagicMock()
    mock_db.execute = AsyncMock(side_effect=[result_mock, update_result])

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=_make_http_resp(200, {"total": 0, "items": []}))
        mock_http.patch = AsyncMock(side_effect=ConnectionError("Drive down"))
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        resp = client.post("/admin/remediate-legacy", headers=get_auth_headers())

    assert resp.status_code == 200
    assert resp.json()["fixed_count"] == 1


def test_remediate_legacy_competencies_network_error(client, mock_db):
    """Erreur réseau sur GET compétences → continue (pas de remédiation)."""
    result_mock = MagicMock()
    result_mock.fetchall.return_value = [
        (6, 60, "https://drive.google.com/d/FILE6", [{"name": "Python"}])
    ]
    mock_db.execute = AsyncMock(return_value=result_mock)

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=ConnectionError("API unreachable"))
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        resp = client.post("/admin/remediate-legacy", headers=get_auth_headers())

    assert resp.status_code == 200
    assert resp.json()["fixed_count"] == 0


def test_remediate_legacy_list_response_from_competencies_api(client, mock_db):
    """competencies_api retourne une liste (non dict) → len(data) utilisé."""
    result_mock = MagicMock()
    result_mock.fetchall.return_value = [
        (7, 70, "https://drive.google.com/d/FILE7",
         [{"name": "Python"}, {"name": "GCP"}, {"name": "K8s"}])
    ]
    mock_db.execute = AsyncMock(return_value=result_mock)

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        # Retourne une liste au lieu d'un dict
        mock_http.get = AsyncMock(return_value=_make_http_resp(200, [{"id": 1}, {"id": 2}, {"id": 3}]))
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        resp = client.post("/admin/remediate-legacy", headers=get_auth_headers())

    assert resp.status_code == 200
    # 3 assignées >= 3 extraites → ignoré
    assert resp.json()["fixed_count"] == 0


def test_remediate_legacy_global_exception_returns_500(client, mock_db):
    """Exception au niveau de db.execute() → HTTP 500."""
    mock_db.execute = AsyncMock(side_effect=RuntimeError("DB crash"))

    resp = client.post("/admin/remediate-legacy", headers=get_auth_headers())

    assert resp.status_code == 500
    assert "DB crash" in resp.json()["detail"]


def test_remediate_legacy_requires_admin_role(client):
    """Un utilisateur non-admin reçoit HTTP 403.

    Le conftest override verify_jwt en admin. On doit temporairement restaurer
    verify_admin réel pour tester le chemin 403.
    """
    # Retire l'override verify_admin pour laisser la vraie logique tourner
    from shared.auth.jwt import verify_jwt

    def override_user_jwt():
        return {"sub": "non_admin", "role": "user"}

    app.dependency_overrides[verify_jwt] = override_user_jwt
    try:
        resp = client.post("/admin/remediate-legacy", headers=get_auth_headers(role="user"))
    finally:
        # Restaure l'override admin du conftest
        app.dependency_overrides[verify_jwt] = lambda: {"sub": "test", "email": "test@zenika.com", "role": "admin"}

    assert resp.status_code == 403


# ── POST /admin/clear-processing-errors ──────────────────────────────────────

def test_clear_processing_errors_success(client, mock_db):
    """Succès : retourne cleared_count = rowcount."""
    result_mock = MagicMock()
    result_mock.rowcount = 7
    mock_db.execute = AsyncMock(return_value=result_mock)

    resp = client.post("/admin/clear-processing-errors", headers=get_auth_headers())

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["cleared_count"] == 7
    mock_db.commit.assert_called_once()


def test_clear_processing_errors_zero_rows(client, mock_db):
    """Aucune ligne à nettoyer → cleared_count = 0."""
    result_mock = MagicMock()
    result_mock.rowcount = 0
    mock_db.execute = AsyncMock(return_value=result_mock)

    resp = client.post("/admin/clear-processing-errors", headers=get_auth_headers())

    assert resp.status_code == 200
    assert resp.json()["cleared_count"] == 0


def test_clear_processing_errors_rowcount_none(client, mock_db):
    """rowcount = None (driver sans support) → cleared_count = 0."""
    result_mock = MagicMock()
    result_mock.rowcount = None
    mock_db.execute = AsyncMock(return_value=result_mock)

    resp = client.post("/admin/clear-processing-errors", headers=get_auth_headers())

    assert resp.status_code == 200
    assert resp.json()["cleared_count"] == 0


def test_clear_processing_errors_db_exception(client, mock_db):
    """Exception DB → HTTP 500 + rollback."""
    mock_db.execute = AsyncMock(side_effect=RuntimeError("JSONB error"))

    resp = client.post("/admin/clear-processing-errors", headers=get_auth_headers())

    assert resp.status_code == 500
    assert "JSONB error" in resp.json()["detail"]
    mock_db.rollback.assert_called_once()


def test_clear_processing_errors_requires_admin(client):
    """Un utilisateur non-admin reçoit HTTP 403."""
    from shared.auth.jwt import verify_jwt

    def override_user_jwt():
        return {"sub": "non_admin", "role": "user"}

    app.dependency_overrides[verify_jwt] = override_user_jwt
    try:
        resp = client.post("/admin/clear-processing-errors", headers=get_auth_headers(role="user"))
    finally:
        app.dependency_overrides[verify_jwt] = lambda: {"sub": "test", "email": "test@zenika.com", "role": "admin"}

    assert resp.status_code == 403
