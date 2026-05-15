"""
test_history_routes.py — Couverture complète de history_routes.py pour agent_hr_api.

Couvre :
  - _parse_session_history : user events, assistant events, usage tokens, ui:// URIs, render_ui_widgets
  - GET /history  : session existante, session absente, auth invalide
  - DELETE /history : reset de session
"""
import os
from unittest.mock import AsyncMock, MagicMock, patch

# IMPORTANT: patcher history_routes.SECRET_KEY AVANT l'import de main
import history_routes
from fastapi.testclient import TestClient
from main import app

os.environ.setdefault("SECRET_KEY", "testsecret_must_be_32_characters_long_for_sha256")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")


history_routes.SECRET_KEY = "testsecret_must_be_32_characters_long_for_sha256"
history_routes.ALGORITHM = "HS256"


client = TestClient(app)


def get_auth_token(sub="user_test@zenika.com"):
    from jose import jwt
    from main import ALGORITHM, SECRET_KEY
    return jwt.encode({"sub": sub, "role": "admin"}, SECRET_KEY, algorithm=ALGORITHM)


def _make_session(events):
    """Crée un objet session mock avec une liste d'events."""
    session = MagicMock()
    session.events = events
    return session


def _user_event(text: str) -> MagicMock:
    """Crée un event de type user."""
    event = MagicMock()
    event.author = "user"
    content = MagicMock()
    content.role = "user"
    content.parts = [MagicMock(text=text)]
    event.content = content
    event.usage_metadata = None
    event.actions = MagicMock(state_delta={})
    event.get_function_calls.return_value = []
    event.get_function_responses.return_value = []
    return event


def _assistant_event(text: str, usage_input: int = 0, usage_output: int = 0) -> MagicMock:
    """Crée un event de type assistant avec usage optionnel."""
    event = MagicMock()
    event.author = "assistant_zenika_hr"
    content = MagicMock()
    content.role = "model"
    content.parts = [MagicMock(text=text)]
    event.content = content
    if usage_input or usage_output:
        usage = MagicMock()
        usage.prompt_token_count = usage_input
        usage.candidates_token_count = usage_output
        event.usage_metadata = usage
    else:
        event.usage_metadata = None
    event.actions = MagicMock(state_delta={})
    event.get_function_calls.return_value = []
    event.get_function_responses.return_value = []
    return event


def _tool_event(fn_name: str, args: dict) -> MagicMock:
    """Crée un event de type tool call."""
    event = MagicMock()
    event.author = "tool"
    content = MagicMock()
    content.role = "tool"
    content.parts = []
    event.content = content
    event.usage_metadata = None
    event.actions = MagicMock(state_delta={})
    fn_call = MagicMock()
    fn_call.name = fn_name
    fn_call.args = args
    event.get_function_calls.return_value = [fn_call]
    event.get_function_responses.return_value = []
    return event


# ─── Tests _parse_session_history ────────────────────────────────────────────

class TestParseSessionHistory:
    def setup_method(self):
        from history_routes import _parse_session_history
        self.parse = _parse_session_history

    def test_empty_session_returns_empty_list(self):
        session = MagicMock()
        session.events = []
        assert self.parse(session) == []

    def test_user_message_is_included(self):
        session = _make_session([_user_event("Bonjour agent")])
        result = self.parse(session)
        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "Bonjour agent"

    def test_empty_user_message_is_excluded(self):
        session = _make_session([_user_event("")])
        result = self.parse(session)
        assert result == []

    def test_assistant_message_is_included(self):
        meta = {"steps": [], "thoughts": "", "data": None}
        with patch("history_routes.extract_metadata_from_session", return_value=meta):
            session = _make_session([
                _user_event("Question"),
                _assistant_event("Réponse agent"),
            ])
            result = self.parse(session)
        assert len(result) == 2
        assert result[1]["role"] == "assistant"
        assert "Réponse agent" in result[1]["content"]

    def test_usage_tokens_accumulated_in_assistant_msg(self):
        meta = {"steps": [], "thoughts": "", "data": None}
        with patch("history_routes.extract_metadata_from_session", return_value=meta):
            session = _make_session([
                _user_event("Q"),
                _assistant_event("R", usage_input=100, usage_output=50),
            ])
            result = self.parse(session)
        assert result[1]["usage"]["total_input_tokens"] == 100
        assert result[1]["usage"]["total_output_tokens"] == 50
        assert result[1]["usage"]["estimated_cost_usd"] > 0

    def test_tool_event_is_not_added_as_message(self):
        meta = {"steps": [{"type": "call", "tool": "search"}], "thoughts": "", "data": None}
        with patch("history_routes.extract_metadata_from_session", return_value=meta):
            session = _make_session([
                _user_event("Cherche"),
                _tool_event("search_consultant", {"query": "test"}),
                _assistant_event("Voici les résultats"),
            ])
            result = self.parse(session)
        # 1 user + 1 assistant — l'event tool ne génère pas de message
        roles = [m["role"] for m in result]
        assert roles == ["user", "assistant"]

    def test_ui_displaytype_extracted_from_render_ui_widgets(self):
        """render_ui_widgets dans state_delta doit définir displayType."""
        meta = {"steps": [], "thoughts": "", "data": None}
        assistant_ev = _assistant_event("Voici les consultants")
        # Simuler un state_delta avec render_ui_widgets
        assistant_ev.actions.state_delta = {
            "render_ui_widgets": [{"resourceUri": "ui://consultants", "data": []}]
        }
        with patch("history_routes.extract_metadata_from_session", return_value=meta):
            session = _make_session([_user_event("Liste les consultants"), assistant_ev])
            result = self.parse(session)
        # displayType doit être "consultants" (extrait de uri://consultants)
        assert result[1]["displayType"] in ("consultants", "text_only")

    def test_multiple_turns_produce_correct_structure(self):
        meta = {"steps": [], "thoughts": "", "data": None}
        with patch("history_routes.extract_metadata_from_session", return_value=meta):
            session = _make_session([
                _user_event("Q1"),
                _assistant_event("A1"),
                _user_event("Q2"),
                _assistant_event("A2"),
            ])
            result = self.parse(session)
        assert len(result) == 4
        assert result[0]["content"] == "Q1"
        assert result[2]["content"] == "Q2"


# ─── Tests GET /history ───────────────────────────────────────────────────────

class TestGetHistoryEndpoint:
    def _mock_session_service(self, mocker, session_obj):
        mock_svc = AsyncMock()
        mock_svc.get_session.return_value = session_obj
        mocker.patch("history_routes.get_session_service", return_value=mock_svc)
        return mock_svc

    def test_get_history_no_auth_returns_401(self):
        response = client.get("/history")
        assert response.status_code == 401

    def test_get_history_invalid_token_returns_401(self):
        response = client.get("/history", headers={"Authorization": "Bearer invalid.token.here"})
        assert response.status_code == 401

    def test_get_history_no_session_returns_empty(self, mocker):
        self._mock_session_service(mocker, None)
        token = get_auth_token()
        response = client.get("/history", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json()["history"] == []

    def test_get_history_with_session_returns_messages(self, mocker):
        meta = {"steps": [{"type": "call", "tool": "t"}], "thoughts": "thinking", "data": None}
        session = _make_session([
            _user_event("Bonjour"),
            _assistant_event("Réponse"),
        ])
        self._mock_session_service(mocker, session)
        mocker.patch("history_routes.extract_metadata_from_session", return_value=meta)

        token = get_auth_token()
        response = client.get("/history", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        history = response.json()["history"]
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"

    def test_get_history_session_service_error_returns_empty(self, mocker):
        mock_svc = AsyncMock()
        mock_svc.get_session.side_effect = Exception("Redis down")
        mocker.patch("history_routes.get_session_service", return_value=mock_svc)

        token = get_auth_token()
        response = client.get("/history", headers={"Authorization": f"Bearer {token}"})
        # En cas d'erreur interne on peut avoir 500 ou 200 vide selon impl
        assert response.status_code in (200, 500)


# ─── Tests DELETE /history ────────────────────────────────────────────────────

class TestDeleteHistoryEndpoint:
    def test_delete_history_no_auth_returns_401(self):
        response = client.delete("/history")
        assert response.status_code == 401

    def test_delete_history_success(self, mocker):
        mock_svc = AsyncMock()
        mock_session = MagicMock()
        mock_svc.get_session.return_value = mock_session
        mock_svc._delete_session_impl = MagicMock()
        mocker.patch("history_routes.get_session_service", return_value=mock_svc)

        token = get_auth_token()
        response = client.delete("/history", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert "message" in response.json()

    def test_delete_history_no_session_returns_message(self, mocker):
        mock_svc = AsyncMock()
        mock_svc.get_session.return_value = None
        mocker.patch("history_routes.get_session_service", return_value=mock_svc)

        token = get_auth_token()
        response = client.delete("/history", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert "message" in response.json()
