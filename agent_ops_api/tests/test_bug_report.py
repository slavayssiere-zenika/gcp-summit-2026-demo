import os
import sys
from unittest.mock import patch
import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

SECRET_KEY = os.environ.get("SECRET_KEY", "testsecret_must_be_32_characters_long_for_sha256")
ALGORITHM = "HS256"

sys.path.insert(0, os.path.dirname(__file__))


def make_jwt(sub: str = "alice@zenika.com") -> str:
    return pyjwt.encode({"sub": sub, "exp": 9999999999}, SECRET_KEY, algorithm=ALGORITHM)


def auth_headers(sub: str = "alice@zenika.com") -> dict:
    return {"Authorization": f"Bearer {make_jwt(sub)}"}


@pytest.fixture
def client():
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@patch("bug_report._send_chat_notification")
@patch("agent.run_agent_query")
def test_improvement_request_success(mock_run_query, mock_send_notification, client):
    # Mock agent response
    mock_run_query.return_value = {
        "response": "SRE Agent analysis result here.",
        "data": {},
        "display_type": "text_only",
        "steps": [],
        "thoughts": "",
    }
    mock_send_notification.return_value = None

    payload = {
        "session_id": "test-session-123",
        "user_comment": "We need a faster UI load.",
        "session_history": [
            {"role": "user", "content": "Hello agent"},
            {"role": "assistant", "content": "Hello user, how can I help?"}
        ]
    }

    response = client.post(
        "/sre/improvement",
        json=payload,
        headers=auth_headers("alice@zenika.com")
    )

    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    assert data["success"] is True
    assert "SRE Agent analysis result" in data["analysis"]

    mock_run_query.assert_called_once()
    mock_send_notification.assert_called_once_with(
        user_email="alice@zenika.com",
        session_id="test-session-123",
        user_comment="We need a faster UI load.",
        analysis_text="SRE Agent analysis result here."
    )
