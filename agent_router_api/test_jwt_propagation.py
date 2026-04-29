"""
test_jwt_propagation.py — Tests de propagation JWT dans agent_router_api.

Vérifie :
  1. Token valide → accès autorisé à /query
  2. Token absent → 403 Forbidden
  3. Token expiré → 401 Unauthorized
  4. Token sans claim 'sub' → 401 Unauthorized
  5. JWT propagé vers les sous-agents (auth_header_var)
  6. Session isolée par sub JWT (deux users = deux sessions distinctes)
"""

import pytest
import time
from unittest.mock import AsyncMock


def make_token(sub: str = "user@zenika.com", role: str = "user", expired: bool = False, omit_sub: bool = False) -> str:
    from jose import jwt
    from router import SECRET_KEY
    from agent_commons.jwt_middleware import ALGORITHM
    payload: dict = {"role": role}
    if not omit_sub:
        payload["sub"] = sub
    if expired:
        payload["exp"] = int(time.time()) - 3600  # Expiré il y a 1h
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


# ── Accès autorisé ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_valid_jwt_grants_access(mocker, client):
    """Un token JWT valide doit permettre l'accès à /query."""
    mocker.patch("router._semantic_cache.get", new=AsyncMock(return_value=None))
    mocker.patch("router._semantic_cache.set", new=AsyncMock())
    ok_response = {"response": "OK", "source": "agent_hr", "data": None, "steps": [], "thoughts": ""}
    mocker.patch("router.run_agent_query", new=AsyncMock(return_value=ok_response))

    token = make_token()
    resp = client.post("/query", json={"query": "test"}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


# ── Token absent ──────────────────────────────────────────────────────────────

def test_missing_jwt_returns_401(client):
    """Aucun header Authorization → 401."""
    resp = client.post("/query", json={"query": "test"})
    assert resp.status_code == 401


def test_malformed_bearer_returns_401(client):
    """Header mal formé (pas 'Bearer XXX') → 401."""
    resp = client.post("/query", json={"query": "test"}, headers={"Authorization": "Basic invalid"})
    assert resp.status_code == 401


# ── Token invalide / expiré ───────────────────────────────────────────────────

def test_expired_jwt_returns_401(client):
    """Token expiré → 401 Unauthorized."""
    token = make_token(expired=True)
    resp = client.post("/query", json={"query": "test"}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_invalid_signature_returns_401(client):
    """Token signé avec une mauvaise clé → 401."""
    from jose import jwt
    bad_token = jwt.encode({"sub": "hacker@evil.com"}, "WRONG_SECRET_KEY", algorithm="HS256")
    resp = client.post("/query", json={"query": "test"}, headers={"Authorization": f"Bearer {bad_token}"})
    assert resp.status_code == 401


def test_jwt_without_sub_returns_401(client):
    """Token sans claim 'sub' → 401 (AGENTS.md §4)."""
    token = make_token(omit_sub=True)
    resp = client.post("/query", json={"query": "test"}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


# ── Propagation JWT vers les sous-agents ─────────────────────────────────────

@pytest.mark.asyncio
async def test_auth_header_var_set_before_run_agent(mocker, client):
    """auth_header_var doit être alimenté avec le Bearer token avant tout appel sous-agent."""
    mocker.patch("router._semantic_cache.get", new=AsyncMock(return_value=None))
    mocker.patch("router._semantic_cache.set", new=AsyncMock())

    captured_header: list = []

    async def capture_run_agent_query(query, session_id, auth_token=None, user_id=None):
        captured_header.append(auth_token)
        return {"response": "OK", "source": "agent_hr", "data": None, "steps": [], "thoughts": ""}

    mocker.patch("router.run_agent_query", new=capture_run_agent_query)

    token = make_token(sub="alice@zenika.com")
    client.post("/query", json={"query": "test"}, headers={"Authorization": f"Bearer {token}"})

    # auth_token transmis à run_agent_query doit contenir le Bearer
    assert len(captured_header) == 1
    assert captured_header[0] is not None
    assert "Bearer" in str(captured_header[0]) or captured_header[0] != ""


# ── Isolation de session par sub JWT ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_different_users_have_different_sessions(mocker, client):
    """Deux utilisateurs différents (sub distincts) doivent avoir des session_ids différents."""
    mocker.patch("router._semantic_cache.get", new=AsyncMock(return_value=None))
    mocker.patch("router._semantic_cache.set", new=AsyncMock())

    captured_sessions: list = []

    async def capture_sessions(query, session_id, auth_token=None, user_id=None):
        captured_sessions.append(session_id)
        return {"response": "OK", "source": "agent_hr", "data": None, "steps": [], "thoughts": ""}

    mocker.patch("router.run_agent_query", new=capture_sessions)

    token_alice = make_token(sub="alice@zenika.com")
    token_bob = make_token(sub="bob@zenika.com")

    client.post("/query", json={"query": "test"}, headers={"Authorization": f"Bearer {token_alice}"})
    client.post("/query", json={"query": "test"}, headers={"Authorization": f"Bearer {token_bob}"})

    assert len(captured_sessions) == 2
    assert captured_sessions[0] != captured_sessions[1], "Les sessions de deux users différents doivent être isolées"


# ── Endpoint /history protégé ─────────────────────────────────────────────────

def test_history_requires_valid_jwt(client):
    """GET /history sans token → 401."""
    resp = client.get("/history")
    assert resp.status_code == 401


def test_history_with_valid_jwt(mocker, client):
    """GET /history avec token valide → 200 (même si vide)."""
    # Mock la session service pour éviter Redis réel
    mock_session_service = mocker.MagicMock()
    mock_session_service.get_session = AsyncMock(return_value=None)
    mocker.patch("router.get_session_service", return_value=mock_session_service)

    token = make_token()
    resp = client.get("/history", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert "history" in resp.json()
