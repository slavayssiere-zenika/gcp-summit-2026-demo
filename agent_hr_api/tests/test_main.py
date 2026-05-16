from unittest.mock import patch

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

# Helper for JWT payload Generation


def get_auth_token(sub="user_1"):
    import jwt
    from main import ALGORITHM, SECRET_KEY
    payload = {"sub": sub, "role": "admin"}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert "HR Agent API" in response.json()["message"]


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

# NOTE: Les endpoints /login, /logout, /me ont été supprimés de agent_hr_api.
# Le frontend s'authentifie directement via /auth/ → users_api (LB prio 30).
# Ces tests ne sont donc plus pertinents.


def test_mcp_registry():
    token = get_auth_token()
    response = client.get("/mcp/registry", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.json()
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

# Les tests /history sont couverts dans test_history_routes.py (patch de history_routes.SECRET_KEY requis)
