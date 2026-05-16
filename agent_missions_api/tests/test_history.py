import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from main import app
import os
SECRET_KEY = os.environ.get("SECRET_KEY", "testsecret_must_be_32_characters_long_for_sha256")
import jwt  # noqa: E402

ALGORITHM = "HS256"


def make_jwt(sub: str = "test@zenika.com") -> str:
    return jwt.encode({"sub": sub, "exp": 9999999999}, SECRET_KEY, algorithm=ALGORITHM)


def auth_headers(sub: str = "test@zenika.com") -> dict:
    return {"Authorization": f"Bearer {make_jwt(sub)}"}


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


def test_get_history_empty(client):
    mock_session_service = AsyncMock()
    mock_session_service.get_session.return_value = None
    with patch("main.get_session_service", return_value=mock_session_service):
        resp = client.get("/history", headers=auth_headers())
    assert resp.status_code == 200
    assert resp.json() == {"history": []}


def test_get_history_with_events(client):
    mock_session_service = AsyncMock()

    mock_session = MagicMock()

    class FakePart:
        def __init__(self, text):
            self.text = text

    class FakeContent:
        def __init__(self, role, text):
            self.role = role
            self.parts = [FakePart(text)]

    class FakeEvent:
        def __init__(self, author, role, text):
            self.author = author
            self.content = FakeContent(role, text)

    mock_session.events = [
        FakeEvent("user", "user", "Hello"),
        FakeEvent("assistant", "model", '{"reply": "Hi", "display_type": "text_only", "data": {}}')
    ]

    mock_session_service.get_session.return_value = mock_session

    with patch("main.get_session_service", return_value=mock_session_service):
        with patch("main.extract_metadata_from_session", return_value={"data": None, "steps": []}):
            resp = client.get("/history", headers=auth_headers())

    assert resp.status_code == 200
    history = resp.json()["history"]
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "Hello"
    assert history[1]["role"] == "assistant"
    assert history[1]["content"] == "Hi"


def test_delete_history(client):
    mock_session_service = AsyncMock()
    mock_session = MagicMock()
    mock_session_service.get_session.return_value = mock_session
    mock_session_service._delete_session_impl = MagicMock()

    with patch("main.get_session_service", return_value=mock_session_service):
        resp = client.delete("/history", headers=auth_headers())

    assert resp.status_code == 200
    assert resp.json() == {"message": "Historique effacé"}
    mock_session_service._delete_session_impl.assert_called_once()


def test_delete_history_empty(client):
    mock_session_service = AsyncMock()
    mock_session_service.get_session.return_value = None

    with patch("main.get_session_service", return_value=mock_session_service):
        resp = client.delete("/history", headers=auth_headers())

    assert resp.status_code == 200
    assert resp.json() == {"message": "Pas d'historique"}


def test_a2a_query_success(client):
    mock_result = {
        "response": "ok",
        "data": {},
        "display_type": "text_only",
        "steps": [],
        "thoughts": "",
        "usage": {},
        "source": None,
        "session_id": "sess"
    }
    with patch("main.run_agent_query", new=AsyncMock(return_value=mock_result)):
        resp = client.post("/a2a/query", json={"query": "test"}, headers=auth_headers())
    assert resp.status_code == 200
    assert resp.json()["response"] == "ok"


def test_get_spec(client):
    resp = client.get("/spec")
    assert resp.status_code == 200
    assert "Agent Missions API" in resp.text
