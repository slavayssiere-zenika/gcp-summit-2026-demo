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
    from main import SECRET_KEY, ALGORITHM
    payload = {"sub": sub, "role": "admin"}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert "Ops Agent API" in response.json()["message"]

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

@patch('main.run_agent_query')
def test_query_success(mock_run_agent_query):
    mock_run_agent_query.return_value = {"response": "Answer", "source": "gemini"}
    token = get_auth_token()
    
    response = client.post("/query", json={"query": "Hello"}, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["response"] == "Answer"

@patch('main.run_agent_query')
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
    
    mocker.patch("agent.get_session_service", return_value=mock_svc)
    mocker.patch("metadata.extract_metadata_from_session", return_value={"steps": [{"type": "call", "tool": "test"}], "thoughts": "thought"})
    
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
    mocker.patch("agent.get_session_service", return_value=mock_svc)
    
    token = get_auth_token()
    response = client.get("/history", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["history"] == []

def test_get_history_invalid_auth():
    response = client.get("/history", headers={"Authorization": "Bearer invalid"})
    assert response.status_code == 401
