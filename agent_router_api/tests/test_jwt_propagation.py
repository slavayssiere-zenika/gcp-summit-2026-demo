"""
Tests de non-régression : propagation du JWT sub comme user_id dans agent_router_api.

Régression ciblée :
- run_agent_query recevait user_id="user_1" hardcodé (sessions ADK et runner)
- log_ai_consumption BigQuery utilisait session_id (email) au lieu du vrai sub JWT
- /history et DELETE /history utilisaient jwt_user_id = payload.get("sub", "user_1")
  qui est correct si sub est non-null (pas de régression ici, test de confirmation)

ADR : BUG-FINOPS-002
"""

import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from jose import jwt as jose_jwt

SECRET_KEY = os.environ.get("SECRET_KEY", "testsecret")
ALGORITHM = "HS256"


def make_jwt(sub: str = "router@zenika.com") -> str:
    """Génère un JWT signé avec python-jose, cohérent avec le décodeur de main.py."""
    return jose_jwt.encode({"sub": sub, "exp": 9999999999}, SECRET_KEY, algorithm=ALGORITHM)


# ---------------------------------------------------------------------------
# 1. run_agent_query — doit accepter et utiliser user_id (pas "user_1")
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_agent_query_uses_provided_user_id(mocker):
    """
    REGRESSION BUG-FINOPS-002 : run_agent_query doit utiliser le user_id fourni
    depuis le JWT sub plutôt que 'user_1' hardcodé pour les sessions ADK.
    """
    import agent as agent_module

    captured_session_args = []

    mock_session_svc = MagicMock()

    async def mock_get_session(app_name, user_id, session_id):
        captured_session_args.append({"op": "get", "user_id": user_id})
        raise KeyError("not found")

    async def mock_create_session(app_name, user_id, session_id):
        captured_session_args.append({"op": "create", "user_id": user_id})

    mock_session_svc.get_session = mock_get_session
    mock_session_svc.create_session = mock_create_session

    mock_runner = MagicMock()

    async def mock_run_async(user_id, session_id, new_message):
        captured_session_args.append({"op": "run_async", "user_id": user_id})
        return
        yield  # Make it an async generator

    mock_runner.run_async = mock_run_async

    mocker.patch("agent.get_session_service", return_value=mock_session_svc)
    mocker.patch("agent.create_agent", new=AsyncMock(return_value=MagicMock(model="gemini-3-flash")))
    mocker.patch("google.adk.runners.Runner", return_value=mock_runner)

    await agent_module.run_agent_query(
        "Test query",
        session_id="test-session-router",
        user_id="router-user@zenika.com",
    )

    # Vérifier que AUCUN appel n'a utilisé "user_1"
    for call in captured_session_args:
        assert call["user_id"] != "user_1", (
            f"REGRESSION: {call['op']} a utilisé 'user_1' hardcodé. "
            f"Toutes les opérations doivent utiliser le sub JWT."
        )

    # Vérifier que le bon user_id a été propagé
    create_calls = [c for c in captured_session_args if c["op"] == "create"]
    if create_calls:
        assert create_calls[0]["user_id"] == "router-user@zenika.com", \
            f"create_session doit utiliser le sub JWT, got: {create_calls[0]['user_id']}"


@pytest.mark.asyncio
async def test_run_agent_query_bq_log_uses_user_id_not_session_id(mocker):
    """
    REGRESSION BUG-FINOPS-002 : log_ai_consumption BigQuery doit utiliser le
    user_id (sub JWT) pour user_email, pas session_id (qui peut être un UUID).
    """
    import agent as agent_module

    bq_log_calls = []

    mock_session_svc = MagicMock()
    mock_session_svc.get_session = AsyncMock(side_effect=KeyError("not found"))
    mock_session_svc.create_session = AsyncMock()

    mock_runner = MagicMock()

    # Simuler un event avec usage_metadata pour déclencher le log BQ
    class MockEvent:
        pass
    
    mock_event = MockEvent()
    mock_event.content = None
    mock_event.actions = []
    mock_event.usage_metadata = {"prompt_token_count": 100, "candidates_token_count": 50}

    async def mock_run_async(user_id, session_id, new_message):
        yield mock_event

    mock_runner.run_async = mock_run_async

    mocker.patch("agent.get_session_service", return_value=mock_session_svc)
    mocker.patch("agent.create_agent", new=AsyncMock(return_value=MagicMock(model="gemini-3-flash")))
    mocker.patch("google.adk.runners.Runner", return_value=mock_runner)

    # Mock httpx pour capturer l'appel BQ
    mock_response = MagicMock()
    mock_response.status_code = 200

    async def capture_bq_call(url, json=None, **kwargs):
        if "log_ai_consumption" in str(json):
            bq_log_calls.append(json)
        return mock_response

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = capture_bq_call

    mocker.patch("httpx.AsyncClient", return_value=mock_client)

    await agent_module.run_agent_query(
        "Test FinOps query",
        session_id="test-session-uuid-12345",
        user_id="finops-user@zenika.com",
    )

    # Si un log BQ a été émis, il doit utiliser le user_id, pas le session_id
    for call in bq_log_calls:
        args = call.get("arguments", {})
        user_email = args.get("user_email", "")
        assert user_email != "test-session-uuid-12345", (
            "REGRESSION: BQ log_ai_consumption utilise session_id comme user_email "
            "au lieu du sub JWT — les coûts sont mal imputés."
        )
        if user_email:
            assert "@" in user_email, (
                f"REGRESSION: user_email BQ doit contenir '@' (être un email), "
                f"got: {user_email!r}"
            )


# ---------------------------------------------------------------------------
# 2. /query HTTP — user_id JWT sub transmis à run_agent_query
# ---------------------------------------------------------------------------

def test_router_query_passes_jwt_sub_to_run_agent_query():
    """
    REGRESSION BUG-FINOPS-002 : Le handler /query du Router doit extraire le sub JWT
    et le passer à run_agent_query comme user_id.
    """
    from main import app
    from fastapi.testclient import TestClient

    client = TestClient(app, raise_server_exceptions=False)
    captured = {}

    async def capture(query, session_id, auth_token=None, user_id="user_1"):
        captured["user_id"] = user_id
        return {
            "response": "Router OK",
            "steps": [],
            "thoughts": "",
            "usage": {},
            "source": "router",
        }

    with patch("main.run_agent_query", new=capture):
        resp = client.post(
            "/query",
            json={"query": "Recherche consultants"},
            headers={"Authorization": f"Bearer {make_jwt('router-sub@zenika.com')}"},
        )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    assert captured.get("user_id") == "router-sub@zenika.com", (
        f"REGRESSION: run_agent_query doit recevoir sub JWT comme user_id, "
        f"got: {captured.get('user_id')!r}"
    )
    assert captured.get("user_id") != "user_1", \
        "REGRESSION: user_id 'user_1' hardcodé détecté dans le Router /query"

