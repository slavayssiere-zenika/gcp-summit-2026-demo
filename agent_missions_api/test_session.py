import pickle
import pytest
from unittest.mock import MagicMock, patch


# ── Tests RedisSessionService ──────────────────────────────────────────────────

@pytest.fixture
def mock_redis():
    return MagicMock()


@pytest.fixture
def service(mock_redis):
    with patch("redis.from_url", return_value=mock_redis):
        from session import RedisSessionService
        svc = RedisSessionService()
    return svc, mock_redis


def test_session_service_uses_redis_db12(mock_redis):
    """La session doit utiliser Redis DB 12 (isolation totale)."""
    with patch("redis.from_url", return_value=mock_redis) as mock_from_url:
        from session import RedisSessionService
        RedisSessionService()
        call_args = mock_from_url.call_args[0][0]
        assert "/12" in call_args, f"Expected Redis DB 12, got: {call_args}"


def test_session_key_prefix_is_missions(service):
    """La clé Redis doit avoir le préfixe adk:missions:sessions:."""
    svc, mock_redis = service
    session_id = "test-session-abc"

    svc.sessions = {"test": "data"}
    svc.user_state = {}
    svc.app_state = {}
    svc._save_all(session_id)

    call_args = mock_redis.set.call_args
    key_used = call_args[0][0]
    assert key_used == f"adk:missions:sessions:{session_id}", (
        f"Wrong Redis key prefix: {key_used}"
    )


def test_load_all_restores_state(service):
    """_load_all doit restaurer sessions/user_state/app_state depuis Redis."""
    svc, mock_redis = service
    session_id = "restore-session"

    payload = {
        "s": {"session-1": {"messages": ["hello"]}},
        "u": {"user-1": {"prefs": "dark-mode"}},
        "a": {"global": "state"},
    }
    mock_redis.get.return_value = pickle.dumps(payload)

    svc._load_all(session_id)

    assert svc.sessions == payload["s"]
    assert svc.user_state == payload["u"]
    assert svc.app_state == payload["a"]


def test_load_all_empty_session_id_is_noop(service):
    """_load_all avec session_id vide ne doit pas appeler Redis."""
    svc, mock_redis = service
    svc._load_all("")
    mock_redis.get.assert_not_called()


def test_save_all_empty_session_id_is_noop(service):
    """_save_all avec session_id vide ne doit pas appeler Redis."""
    svc, mock_redis = service
    svc._save_all("")
    mock_redis.set.assert_not_called()


def test_load_all_handles_corrupt_data_gracefully(service):
    """_load_all doit logger l'erreur et ne pas crasher si les données Redis sont corrompues."""
    svc, mock_redis = service
    mock_redis.get.return_value = b"corrupted-pickle-data"

    # Ne doit pas lever d'exception
    svc._load_all("some-session")


def test_load_all_handles_missing_key(service):
    """_load_all ne doit pas modifier l'état si la clé n'existe pas en Redis."""
    svc, mock_redis = service
    mock_redis.get.return_value = None
    original_sessions = dict(svc.sessions)

    svc._load_all("nonexistent-session")

    assert svc.sessions == original_sessions


def test_save_uses_30day_ttl(service):
    """Les sessions doivent avoir un TTL de 30 jours."""
    svc, mock_redis = service
    svc._save_all("test-session")
    call_kwargs = mock_redis.set.call_args[1]
    expected_ttl = 30 * 24 * 60 * 60
    assert call_kwargs.get("ex") == expected_ttl, (
        f"Expected TTL {expected_ttl}s, got {call_kwargs.get('ex')}"
    )
