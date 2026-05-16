"""
test_sessions.py — Tests unitaires et d'intégration pour les routes /sessions
et la modification de GET /history avec ?session_id=.

Couverture :
  - Helpers Redis : _load_sessions, _save_sessions, _migrate_legacy_session
  - GET  /sessions  : init vierge, migration legacy, retour liste existante
  - POST /sessions  : création, limite 10, nom par défaut
  - PATCH /sessions/{id} : renommage, session introuvable, nom vide
  - DELETE /sessions/{id} : suppression, protection dernière session, 404
  - GET /history    : avec et sans ?session_id=
  - Zero-trust     : toutes les routes exigent un JWT valide
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers JWT
# ---------------------------------------------------------------------------

def get_auth_token(sub: str = "user@zenika.com") -> str:
    import jwt
    from router import SECRET_KEY
    from shared.auth.jwt import ALGORITHM
    payload = {"sub": sub, "role": "admin"}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


# ---------------------------------------------------------------------------
# Fixtures Redis mock
# ---------------------------------------------------------------------------

class FakeRedis:
    """Redis synchrone ultra-minimal pour les tests des helpers."""

    def __init__(self, initial: dict | None = None):
        self._store: dict = dict(initial or {})

    def get(self, key: str):
        val = self._store.get(key)
        return val.encode() if isinstance(val, str) else val

    def set(self, key: str, value, ex=None):
        self._store[key] = value

    def exists(self, key: str) -> int:
        return 1 if key in self._store else 0

    def delete(self, key: str):
        self._store.pop(key, None)


def _sessions_json(sessions: list) -> bytes:
    return json.dumps(sessions).encode()


# ---------------------------------------------------------------------------
# Tests unitaires — helpers Redis
# ---------------------------------------------------------------------------


class TestLoadSessions:
    def test_returns_empty_when_no_key(self, mocker):
        fake_r = FakeRedis()
        mocker.patch("router._get_redis", return_value=fake_r)
        from router import _load_sessions
        assert _load_sessions("user@test.com") == []

    def test_returns_parsed_list(self, mocker):
        sessions = [{"id": "u1", "name": "Défaut", "created_at": "2026-01-01T00:00:00+00:00"}]
        fake_r = FakeRedis({"chat:sessions:u1": json.dumps(sessions)})
        mocker.patch("router._get_redis", return_value=fake_r)
        from router import _load_sessions
        result = _load_sessions("u1")
        assert result == sessions

    def test_returns_empty_on_redis_error(self, mocker):
        bad_r = MagicMock()
        bad_r.get.side_effect = Exception("Redis down")
        mocker.patch("router._get_redis", return_value=bad_r)
        from router import _load_sessions
        assert _load_sessions("u1") == []


class TestSaveSessions:
    def test_serializes_to_json(self, mocker):
        fake_r = FakeRedis()
        mocker.patch("router._get_redis", return_value=fake_r)
        from router import _save_sessions
        sessions = [{"id": "u1:abc", "name": "Test", "created_at": "2026-01-01T00:00:00+00:00"}]
        _save_sessions("u1", sessions)
        stored = json.loads(fake_r._store["chat:sessions:u1"])
        assert stored == sessions

    def test_silent_on_redis_error(self, mocker):
        bad_r = MagicMock()
        bad_r.set.side_effect = Exception("Redis down")
        mocker.patch("router._get_redis", return_value=bad_r)
        from router import _save_sessions
        # Ne doit pas lever d'exception
        _save_sessions("u1", [])


class TestMigrateLegacySession:
    def test_migrates_when_legacy_key_exists(self, mocker):
        fake_r = FakeRedis({"adk:sessions:u@test.com": b"pickled_data"})
        mocker.patch("router._get_redis", return_value=fake_r)
        from router import _migrate_legacy_session
        result = _migrate_legacy_session("u@test.com", [])
        assert len(result) == 1
        assert result[0]["id"] == "u@test.com"
        assert result[0]["name"] == "Défaut"

    def test_no_migration_when_no_legacy_key(self, mocker):
        fake_r = FakeRedis()
        mocker.patch("router._get_redis", return_value=fake_r)
        from router import _migrate_legacy_session
        result = _migrate_legacy_session("u@test.com", [])
        assert result == []

    def test_returns_input_list_on_redis_error(self, mocker):
        bad_r = MagicMock()
        bad_r.exists.side_effect = Exception("Redis down")
        mocker.patch("router._get_redis", return_value=bad_r)
        from router import _migrate_legacy_session
        result = _migrate_legacy_session("u@test.com", [])
        assert result == []


# ---------------------------------------------------------------------------
# Tests d'intégration — GET /sessions
# ---------------------------------------------------------------------------


class TestGetSessions:
    def test_requires_auth(self):
        response = client.get("/sessions")
        assert response.status_code == 401

    def test_creates_default_session_when_empty(self, mocker):
        fake_r = FakeRedis()
        mocker.patch("router._get_redis", return_value=fake_r)
        token = get_auth_token("alice@zenika.com")
        response = client.get("/sessions", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        sessions = response.json()["sessions"]
        assert len(sessions) == 1
        assert sessions[0]["name"] == "Défaut"
        assert sessions[0]["id"] == "alice@zenika.com"

    def test_migrates_legacy_and_returns_it(self, mocker):
        # Simule un historique ADK existant sous la clé jwt_sub
        fake_r = FakeRedis({"adk:sessions:alice@zenika.com": b"pickled_data"})
        mocker.patch("router._get_redis", return_value=fake_r)
        token = get_auth_token("alice@zenika.com")
        response = client.get("/sessions", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        sessions = response.json()["sessions"]
        assert len(sessions) == 1
        assert sessions[0]["name"] == "Défaut"

    def test_returns_existing_sessions(self, mocker):
        existing = [
            {"id": "alice@zenika.com:abc", "name": "Analyse Q2", "created_at": "2026-01-01T00:00:00+00:00"},
            {"id": "alice@zenika.com:def", "name": "Défaut", "created_at": "2026-01-02T00:00:00+00:00"},
        ]
        fake_r = FakeRedis({"chat:sessions:alice@zenika.com": json.dumps(existing)})
        mocker.patch("router._get_redis", return_value=fake_r)
        token = get_auth_token("alice@zenika.com")
        response = client.get("/sessions", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert len(response.json()["sessions"]) == 2


# ---------------------------------------------------------------------------
# Tests d'intégration — POST /sessions
# ---------------------------------------------------------------------------


class TestPostSessions:
    def test_requires_auth(self):
        response = client.post("/sessions", json={"name": "Test"})
        assert response.status_code == 401

    def test_creates_session_with_name(self, mocker):
        fake_r = FakeRedis()
        mocker.patch("router._get_redis", return_value=fake_r)
        token = get_auth_token("bob@zenika.com")
        response = client.post(
            "/sessions",
            json={"name": "Mission Alpha"},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Mission Alpha"
        assert data["id"].startswith("bob@zenika.com:")
        assert "created_at" in data

    def test_creates_session_with_default_name_when_empty(self, mocker):
        fake_r = FakeRedis()
        mocker.patch("router._get_redis", return_value=fake_r)
        token = get_auth_token("bob@zenika.com")
        response = client.post(
            "/sessions",
            json={"name": ""},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Nouvelle session"

    def test_rejects_when_10_sessions_exist(self, mocker):
        sessions_10 = [
            {"id": f"u@z.com:s{i}", "name": f"S{i}", "created_at": "2026-01-01T00:00:00+00:00"}
            for i in range(10)
        ]
        fake_r = FakeRedis({"chat:sessions:u@z.com": json.dumps(sessions_10)})
        mocker.patch("router._get_redis", return_value=fake_r)
        token = get_auth_token("u@z.com")
        response = client.post(
            "/sessions",
            json={"name": "Une de trop"},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 400
        assert "Limite" in response.json()["detail"]

    def test_session_id_is_unique(self, mocker):
        fake_r = FakeRedis()
        mocker.patch("router._get_redis", return_value=fake_r)
        token = get_auth_token("carol@zenika.com")
        headers = {"Authorization": f"Bearer {token}"}
        r1 = client.post("/sessions", json={"name": "A"}, headers=headers)
        r2 = client.post("/sessions", json={"name": "B"}, headers=headers)
        assert r1.json()["id"] != r2.json()["id"]


# ---------------------------------------------------------------------------
# Tests d'intégration — PATCH /sessions/{id}
# ---------------------------------------------------------------------------


class TestPatchSessions:
    def test_requires_auth(self):
        response = client.patch("/sessions/some-id", json={"name": "New"})
        assert response.status_code == 401

    def test_renames_session(self, mocker):
        existing = [{"id": "u@z.com:abc", "name": "Ancien", "created_at": "2026-01-01T00:00:00+00:00"}]
        fake_r = FakeRedis({"chat:sessions:u@z.com": json.dumps(existing)})
        mocker.patch("router._get_redis", return_value=fake_r)
        token = get_auth_token("u@z.com")
        response = client.patch(
            "/sessions/u%40z.com%3Aabc",
            json={"name": "Nouveau nom"},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Nouveau nom"

    def test_returns_404_when_session_not_found(self, mocker):
        existing = [{"id": "u@z.com:abc", "name": "Test", "created_at": "2026-01-01T00:00:00+00:00"}]
        fake_r = FakeRedis({"chat:sessions:u@z.com": json.dumps(existing)})
        mocker.patch("router._get_redis", return_value=fake_r)
        token = get_auth_token("u@z.com")
        response = client.patch(
            "/sessions/u%40z.com%3Ainexistant",
            json={"name": "X"},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 404

    def test_returns_400_when_name_is_empty(self, mocker):
        existing = [{"id": "u@z.com:abc", "name": "Test", "created_at": "2026-01-01T00:00:00+00:00"}]
        fake_r = FakeRedis({"chat:sessions:u@z.com": json.dumps(existing)})
        mocker.patch("router._get_redis", return_value=fake_r)
        token = get_auth_token("u@z.com")
        response = client.patch(
            "/sessions/u%40z.com%3Aabc",
            json={"name": "   "},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Tests d'intégration — DELETE /sessions/{id}
# ---------------------------------------------------------------------------


class TestDeleteSessions:
    def test_requires_auth(self):
        response = client.delete("/sessions/some-id")
        assert response.status_code == 401

    def test_deletes_session_and_adk_history(self, mocker):
        existing = [
            {"id": "u@z.com:aaa", "name": "A supprimer", "created_at": "2026-01-01T00:00:00+00:00"},
            {"id": "u@z.com:bbb", "name": "À garder", "created_at": "2026-01-02T00:00:00+00:00"},
        ]
        fake_r = FakeRedis({"chat:sessions:u@z.com": json.dumps(existing)})
        mocker.patch("router._get_redis", return_value=fake_r)

        mock_svc = AsyncMock()
        mock_svc.get_session.return_value = None  # Session ADK déjà absente
        mocker.patch("router.get_session_service", return_value=mock_svc)

        token = get_auth_token("u@z.com")
        response = client.delete(
            "/sessions/u%40z.com%3Aaaa",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        assert response.json()["success"] is True

        # Vérifier que la session a bien été retirée de Redis
        remaining = json.loads(fake_r._store["chat:sessions:u@z.com"])
        assert len(remaining) == 1
        assert remaining[0]["id"] == "u@z.com:bbb"

    def test_rejects_deletion_of_last_session(self, mocker):
        existing = [{"id": "u@z.com:only", "name": "Seule", "created_at": "2026-01-01T00:00:00+00:00"}]
        fake_r = FakeRedis({"chat:sessions:u@z.com": json.dumps(existing)})
        mocker.patch("router._get_redis", return_value=fake_r)
        token = get_auth_token("u@z.com")
        response = client.delete(
            "/sessions/u%40z.com%3Aonly",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 400
        assert "dernière" in response.json()["detail"]

    def test_returns_404_when_session_not_found(self, mocker):
        existing = [
            {"id": "u@z.com:aaa", "name": "A", "created_at": "2026-01-01T00:00:00+00:00"},
            {"id": "u@z.com:bbb", "name": "B", "created_at": "2026-01-02T00:00:00+00:00"},
        ]
        fake_r = FakeRedis({"chat:sessions:u@z.com": json.dumps(existing)})
        mocker.patch("router._get_redis", return_value=fake_r)
        token = get_auth_token("u@z.com")
        response = client.delete(
            "/sessions/u%40z.com%3Ainexistant",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 404

    def test_calls_delete_session_impl_when_adk_session_exists(self, mocker):
        existing = [
            {"id": "u@z.com:aaa", "name": "A", "created_at": "2026-01-01T00:00:00+00:00"},
            {"id": "u@z.com:bbb", "name": "B", "created_at": "2026-01-02T00:00:00+00:00"},
        ]
        fake_r = FakeRedis({"chat:sessions:u@z.com": json.dumps(existing)})
        mocker.patch("router._get_redis", return_value=fake_r)

        mock_svc = AsyncMock()
        mock_adk_session = MagicMock()
        mock_svc.get_session.return_value = mock_adk_session
        mock_svc._delete_session_impl = MagicMock()
        mocker.patch("router.get_session_service", return_value=mock_svc)

        token = get_auth_token("u@z.com")
        client.delete(
            "/sessions/u%40z.com%3Aaaa",
            headers={"Authorization": f"Bearer {token}"}
        )
        mock_svc._delete_session_impl.assert_called_once_with(
            app_name="zenika_assistant",
            user_id="u@z.com",
            session_id="u@z.com:aaa"
        )


# ---------------------------------------------------------------------------
# Tests d'intégration — GET /history avec ?session_id=
# ---------------------------------------------------------------------------


class TestGetHistoryWithSessionId:
    def test_uses_session_id_query_param(self, mocker):
        mock_svc = AsyncMock()
        mock_svc.get_session.return_value = None  # Session vide
        mocker.patch("router.get_session_service", return_value=mock_svc)

        token = get_auth_token("alice@zenika.com")
        response = client.get(
            "/history?session_id=alice%40zenika.com%3Aabc",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        # Vérifie que get_session a été appelé avec le session_id transmis
        mock_svc.get_session.assert_called_once_with(
            app_name="zenika_assistant",
            user_id="alice@zenika.com",
            session_id="alice@zenika.com:abc"
        )

    def test_fallback_to_jwt_sub_when_no_session_id(self, mocker):
        mock_svc = AsyncMock()
        mock_svc.get_session.return_value = None
        mocker.patch("router.get_session_service", return_value=mock_svc)

        token = get_auth_token("alice@zenika.com")
        response = client.get(
            "/history",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        mock_svc.get_session.assert_called_once_with(
            app_name="zenika_assistant",
            user_id="alice@zenika.com",
            session_id="alice@zenika.com"
        )

    def test_returns_empty_history_for_unknown_session(self, mocker):
        mock_svc = AsyncMock()
        mock_svc.get_session.return_value = None
        mocker.patch("router.get_session_service", return_value=mock_svc)

        token = get_auth_token("alice@zenika.com")
        response = client.get(
            "/history?session_id=alice%40zenika.com%3Aunknown",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        assert response.json()["history"] == []
