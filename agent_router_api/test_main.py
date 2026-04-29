import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock
import json
import base64

from main import app

client = TestClient(app)

# Helper for JWT payload Generation
def get_auth_token(sub="user_1"):
    from jose import jwt
    from router import SECRET_KEY
    from agent_commons.jwt_middleware import ALGORITHM
    payload = {"sub": sub, "role": "admin"}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert "Router Agent API" in response.json()["message"]

def test_get_spec_success(mocker):
    mocker.patch("builtins.open", mocker.mock_open(read_data="# Spec doc"))
    token = get_auth_token()
    response = client.get("/spec", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert "# Spec doc" in response.text

def test_get_spec_fail(mocker):
    mocker.patch("builtins.open", side_effect=Exception("Not found"))
    token = get_auth_token()
    response = client.get("/spec", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert "# Specification introuvable" in response.text

@pytest.fixture
def mock_httpx(mocker):
    mock = mocker.patch("main.httpx.AsyncClient")
    client_instance = AsyncMock()
    mock.return_value.__aenter__.return_value = client_instance
    return client_instance

def test_login_success(mock_httpx):
    mock_resp = MagicMock(status_code=200, cookies={"access_token": "abc"})
    mock_resp.json.return_value = {"message": "Success"}
    mock_httpx.post.return_value = mock_resp

    response = client.post("/login", json={"username": "bob", "password": "123"})
    assert response.status_code == 200
    assert response.cookies.get("access_token") == "abc"

def test_login_fail(mock_httpx):
    mock_resp = MagicMock(status_code=401)
    mock_resp.json.return_value = {"detail": "Invalid creds"}
    mock_httpx.post.return_value = mock_resp

    response = client.post("/login", json={"username": "bob", "password": "123"})
    assert response.status_code == 401
    assert "Invalid creds" in response.json()["detail"]

def test_logout():
    client.cookies.set("access_token", "abc")
    response = client.post("/logout")
    assert response.status_code == 200
    assert response.cookies.get("access_token") is None

def test_get_me_success(mock_httpx):
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"username": "bob"}
    mock_httpx.get.return_value = mock_resp
    
    response = client.get("/me")
    assert response.status_code == 200
    assert response.json()["username"] == "bob"

def test_get_me_fail(mock_httpx):
    mock_resp = MagicMock(status_code=401)
    mock_httpx.get.return_value = mock_resp
    
    response = client.get("/me")
    assert response.status_code == 401

def test_mcp_registry():
    token = get_auth_token()
    response = client.get("/mcp/registry", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    payload = response.json()
    assert "services" in payload
    assert len(payload["services"]) > 0

@patch('router.run_agent_query')
def test_query_success(mock_run_agent_query):
    mock_run_agent_query.return_value = {"response": "Answer", "source": "gemini"}
    token = get_auth_token()
    
    response = client.post("/query", json={"query": "Hello"}, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["response"] == "Answer"

@patch('router.run_agent_query')
def test_query_error(mock_run_agent_query):
    mock_run_agent_query.side_effect = Exception("Agent fail")
    token = get_auth_token()
    
    response = client.post("/query", json={"query": "Hello"}, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["source"] == "error"
    assert "Agent fail" in response.json()["response"]

def test_query_no_auth():
    response = client.post("/query", json={"query": "Hello"})
    assert response.status_code == 401

def test_get_history_success(mocker):
    # Mock get_session_service
    mock_svc = AsyncMock()
    mock_session = MagicMock()
    
    mock_event_1 = MagicMock(author="user")
    mock_event_1.usage_metadata = None
    mock_event_1.response = None
    mock_event_1.get_function_calls.return_value = []
    mock_event_1.get_function_responses.return_value = []
    mock_event_1.actions = []
    mock_event_1.content.parts = [MagicMock(text="User msg")]
    
    mock_event_2 = MagicMock(author="assistant")
    mock_event_2.usage_metadata = None
    mock_event_2.response = None
    mock_event_2.get_function_calls.return_value = []
    mock_event_2.get_function_responses.return_value = []
    mock_event_2.actions = []
    mock_event_2.content = "```json\n{\"reply\": \"Ans\", \"display_type\": \"text\"}\n```"
    
    mock_session.events = [mock_event_1, mock_event_2]
    mock_svc.get_session.return_value = mock_session
    
    mocker.patch("router.get_session_service", return_value=mock_svc)
    
    token = get_auth_token("test_user_hi")
    response = client.get("/history", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    history = response.json()["history"]
    assert len(history) == 2
    assert history[0]["content"] == "User msg"
    assert "Ans" in history[1]["content"]

def test_get_history_no_session(mocker):
    mock_svc = AsyncMock()
    mock_svc.get_session.return_value = None
    mocker.patch("router.get_session_service", return_value=mock_svc)
    
    token = get_auth_token()
    response = client.get("/history", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["history"] == []

def test_get_history_invalid_auth():
    response = client.get("/history", headers={"Authorization": "Bearer invalid"})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Tests OPS-002 — Interception des erreurs ADK "No function call event found"
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_agent_query_adk_session_corruption_returns_structured_response(mocker):
    """OPS-002 : L'erreur ADK liée à la corruption de session retourne une réponse
    structurée schema-complète (usage, steps, session_id) et ne lève pas d'exception."""
    from agent import run_agent_query

    # Simule un Runner ADK qui lève ValueError "No function call event found"
    mock_runner = MagicMock()

    async def corrupt_run_async(*args, **kwargs):
        raise ValueError("No function call event found for function responses ids: {'abc123'}")
        yield  # Make it an async generator

    mock_runner.run_async = corrupt_run_async

    mocker.patch("google.adk.runners.Runner", return_value=mock_runner)
    mocker.patch("agent.create_agent", new=AsyncMock(return_value=MagicMock(model="gemini-2.0-flash")))

    mock_session_svc = AsyncMock()
    mock_session_svc.get_session.return_value = MagicMock()
    mocker.patch("agent.get_session_service", return_value=mock_session_svc)

    result = await run_agent_query("Y a-t-il des erreurs 500 ?", session_id="corrupted-session-42")

    # La réponse doit être structurée (schema-complète), pas juste {"response": "Erreur: ...", "source": "error"}
    assert "response" in result
    assert "⚠️" in result["response"]  # Message utilisateur friendly
    assert "session" in result["response"].lower() or "corrompu" in result["response"].lower()

    # steps doit contenir le warning de corruption
    assert "steps" in result
    assert len(result["steps"]) > 0
    corruption_warnings = [s for s in result["steps"] if "SESSION_CORRUPTION" in s.get("tool", "")]
    assert len(corruption_warnings) == 1
    assert "technical_detail" in corruption_warnings[0]["args"]
    assert "No function call event found" in corruption_warnings[0]["args"]["technical_detail"]

    # usage doit être présent (schema-complet)
    assert "usage" in result
    assert "total_input_tokens" in result["usage"]
    assert "total_output_tokens" in result["usage"]
    assert "estimated_cost_usd" in result["usage"]

    # session_id doit être retourné
    assert "session_id" in result
    assert result["session_id"] == "corrupted-session-42"

    # source ne doit pas être "error" (qui casse l'UI)
    assert result.get("source") != "error"


@pytest.mark.asyncio
async def test_run_agent_query_other_value_error_is_logged(mocker):
    """OPS-002 : Une ValueError ADK non-reconnue (pas 'No function call event found')
    est loggée mais ne crash pas — retourne une réponse avec le message d'erreur."""
    from agent import run_agent_query

    mock_runner = MagicMock()

    async def other_error_run_async(*args, **kwargs):
        raise ValueError("Some other unexpected ADK error")
        yield

    mock_runner.run_async = other_error_run_async
    mocker.patch("google.adk.runners.Runner", return_value=mock_runner)
    mocker.patch("agent.create_agent", new=AsyncMock(return_value=MagicMock(model="gemini-2.0-flash")))

    mock_session_svc = AsyncMock()
    mock_session_svc.get_session.return_value = MagicMock()
    mocker.patch("agent.get_session_service", return_value=mock_session_svc)

    result = await run_agent_query("Test query", session_id="test-session-other")

    # La réponse doit contenir quelque chose (pas un crash)
    assert "response" in result
    assert "usage" in result
    assert "steps" in result
    # Pas de warning SESSION_CORRUPTION pour cette erreur
    corruption_warnings = [s for s in result["steps"] if "SESSION_CORRUPTION" in s.get("tool", "")]
    assert len(corruption_warnings) == 0


@pytest.mark.asyncio
async def test_run_agent_query_normal_execution_unaffected(mocker):
    """OPS-002 : Le refactoring try/except ne doit pas altérer le comportement normal
    d'une exécution sans erreur."""
    from agent import run_agent_query

    mock_runner = MagicMock()
    mock_event = MagicMock()
    mock_event.content = MagicMock()
    mock_event.content.role = "model"
    mock_event.content.parts = [MagicMock(text="Réponse normale", thought=None, tool_call=None, function_call=None, function_response=None)]
    mock_event.response = None

    async def normal_run_async(*args, **kwargs):
        yield mock_event

    mock_runner.run_async = normal_run_async
    mocker.patch("google.adk.runners.Runner", return_value=mock_runner)
    mocker.patch("agent.create_agent", new=AsyncMock(return_value=MagicMock(model="gemini-2.0-flash")))

    mock_session_svc = AsyncMock()
    mock_session_svc.get_session.return_value = MagicMock()
    mocker.patch("agent.get_session_service", return_value=mock_session_svc)

    result = await run_agent_query("Bonjour", session_id="normal-session")

    assert "response" in result
    assert "Réponse normale" in result["response"]
    assert "usage" in result
    assert "steps" in result
    # Aucun warning de corruption
    corruption_warnings = [s for s in result["steps"] if "SESSION_CORRUPTION" in s.get("tool", "")]
    assert len(corruption_warnings) == 0
