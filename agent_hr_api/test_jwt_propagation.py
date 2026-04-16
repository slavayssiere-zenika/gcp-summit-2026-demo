"""
Tests de non-régression : propagation du JWT sub comme user_id dans agent_hr_api.

Régression ciblée : avant le correctif, user_id était hardcodé à "user_1"
dans /query -> run_agent_query, et dans get_session / delete_session des endpoints
history. Ces tests garantissent que le sub JWT est toujours utilisé.

ADR : BUG-FINOPS-002
"""

import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(__file__))

import jwt as pyjwt

SECRET_KEY = os.environ.get("SECRET_KEY", "testsecret")
ALGORITHM = "HS256"


def make_jwt(sub: str = "alice@zenika.com") -> str:
    return pyjwt.encode({"sub": sub, "exp": 9999999999}, SECRET_KEY, algorithm=ALGORITHM)


def auth_headers(sub: str = "alice@zenika.com") -> dict:
    return {"Authorization": f"Bearer {make_jwt(sub)}"}


@pytest.fixture
def client():
    from main import app
    from fastapi.testclient import TestClient
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# 1. /query — le sub JWT doit être passé à run_agent_query comme user_id
# ---------------------------------------------------------------------------

def test_query_direct_uses_jwt_sub_as_user_id(client):
    """
    REGRESSION BUG-FINOPS-002 : /query direct doit passer le sub JWT (et non
    'user_1') comme user_id à run_agent_query. Critical pour le tracking FinOps.
    """
    captured = {}

    async def capture(query, session_id, user_id="user_1", **kwargs):
        captured["user_id"] = user_id
        return {
            "response": "Test OK",
            "steps": [],
            "thoughts": "",
            "usage": {},
            "source": "hr_agent",
        }

    with patch("main.run_agent_query", new=capture):
        resp = client.post(
            "/query",
            json={"query": "Recherche les consultants Java"},
            headers=auth_headers("alice@zenika.com"),
        )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    assert captured.get("user_id") == "alice@zenika.com", (
        f"REGRESSION: user_id doit être le sub JWT 'alice@zenika.com', "
        f"got: {captured.get('user_id')!r} — 'user_1' hardcodé ?"
    )
    assert captured.get("user_id") != "user_1", \
        "REGRESSION: user_id ne doit JAMAIS être 'user_1' hardcodé"


def test_query_different_users_different_user_ids(client):
    """Deux utilisateurs distinctes doivent produire deux user_ids distincts."""
    captured_ids = []

    async def capture(query, session_id, user_id="user_1", **kwargs):
        captured_ids.append(user_id)
        return {"response": "OK", "steps": [], "thoughts": "", "usage": {}, "source": "hr_agent"}

    with patch("main.run_agent_query", new=capture):
        client.post("/query", json={"query": "test"}, headers=auth_headers("alice@zenika.com"))
        client.post("/query", json={"query": "test"}, headers=auth_headers("bob@zenika.com"))

    assert len(captured_ids) == 2
    assert captured_ids[0] == "alice@zenika.com"
    assert captured_ids[1] == "bob@zenika.com"
    assert captured_ids[0] != captured_ids[1]


# ---------------------------------------------------------------------------
# 2. GET /history — session ADK doit utiliser sub JWT comme user_id
# ---------------------------------------------------------------------------

def test_history_uses_jwt_sub_as_user_id(client):
    """
    REGRESSION BUG-FINOPS-002 : GET /history doit récupérer la session ADK
    avec user_id=sub_JWT, pas 'user_1'. Sinon, chaque utilisateur voit
    toujours l'historique de 'user_1'.
    """
    captured_get_args = {}

    async def mock_get_session(app_name, user_id, session_id):
        captured_get_args["user_id"] = user_id
        captured_get_args["session_id"] = session_id
        return None  # Pas de session → retourne []

    mock_svc = MagicMock()
    mock_svc.get_session = mock_get_session

    with patch("main.get_session_service", return_value=mock_svc):
        resp = client.get("/history", headers=auth_headers("charlie@zenika.com"))
    assert resp.status_code == 200

    assert captured_get_args.get("user_id") == "charlie@zenika.com", (
        f"REGRESSION: history doit utiliser sub JWT comme user_id, "
        f"got: {captured_get_args.get('user_id')!r}"
    )
    assert captured_get_args.get("user_id") != "user_1", \
        "REGRESSION: user_id 'user_1' hardcodé détecté dans /history"


# ---------------------------------------------------------------------------
# 3. DELETE /history — session ADK doit utiliser sub JWT comme user_id
# ---------------------------------------------------------------------------

def test_delete_history_uses_jwt_sub_as_user_id(client):
    """
    REGRESSION BUG-FINOPS-002 : DELETE /history doit appeler _delete_session_impl
    avec user_id=sub_JWT. Sinon, la suppression ne touche pas la vraie session.
    """
    captured_delete_args = {}

    mock_session = MagicMock()
    mock_session.events = []

    async def mock_get_session(app_name, user_id, session_id):
        return mock_session  # Session existe → déclenchera la suppression

    def mock_delete(app_name, user_id, session_id):
        captured_delete_args["user_id"] = user_id

    mock_svc = MagicMock()
    mock_svc.get_session = mock_get_session
    mock_svc._delete_session_impl = mock_delete

    with patch("main.get_session_service", return_value=mock_svc):
        resp = client.delete("/history", headers=auth_headers("dana@zenika.com"))
    assert resp.status_code == 200

    assert captured_delete_args.get("user_id") == "dana@zenika.com", (
        f"REGRESSION: delete_history doit utiliser sub JWT comme user_id, "
        f"got: {captured_delete_args.get('user_id')!r}"
    )
    assert captured_delete_args.get("user_id") != "user_1", \
        "REGRESSION: user_id 'user_1' hardcodé détecté dans DELETE /history"
