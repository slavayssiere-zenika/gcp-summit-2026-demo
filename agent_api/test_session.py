import pytest
from unittest.mock import MagicMock, patch
import pickle
import asyncio

from session import RedisSessionService

@pytest.fixture
def mock_redis(mocker):
    mock = MagicMock()
    mock_dict = {}
    
    def mock_set(key, val, ex=None):
        mock_dict[key] = val
        
    def mock_get(key):
        return mock_dict.get(key)
        
    mock.set.side_effect = mock_set
    mock.get.side_effect = mock_get
    
    mocker.patch("session.redis.from_url", return_value=mock)
    return mock, mock_dict

def test_init(mock_redis):
    service = RedisSessionService()
    assert service.ttl == 30 * 24 * 60 * 60

def test_save_all(mock_redis):
    mock_r, mock_dict = mock_redis
    service = RedisSessionService()
    service.sessions = {"test": "session"}
    service.user_state = {"u": 1}
    service.app_state = {"a": 2}
    
    service._save_all("user1")
    
    assert "adk:sessions:user1" in mock_dict
    data = pickle.loads(mock_dict["adk:sessions:user1"])
    assert data["s"] == {"test": "session"}
    assert data["u"] == {"u": 1}
    assert data["a"] == {"a": 2}

def test_save_all_no_session(mock_redis):
    mock_r, mock_dict = mock_redis
    service = RedisSessionService()
    service._save_all(None)
    assert not mock_dict

def test_save_all_exception(mock_redis, mocker):
    mock_r, _ = mock_redis
    mock_r.set.side_effect = Exception("Redis error")
    mock_logger = mocker.patch("session.logger.error")
    
    service = RedisSessionService()
    service._save_all("user1")
    mock_logger.assert_called_once()

def test_load_all(mock_redis):
    mock_r, mock_dict = mock_redis
    service = RedisSessionService()
    
    # Pre-populate
    dump = pickle.dumps({
        "s": {"s1": "v1"},
        "u": {"u1": "v2"},
        "a": {"a1": "v3"}
    })
    mock_dict["adk:sessions:user1"] = dump
    
    service._load_all("user1")
    assert service.sessions == {"s1": "v1"}
    assert service.user_state == {"u1": "v2"}
    assert service.app_state == {"a1": "v3"}

def test_load_all_no_session(mock_redis):
    service = RedisSessionService()
    service._load_all(None)

def test_load_all_exception(mock_redis, mocker):
    mock_r, _ = mock_redis
    mock_r.get.side_effect = Exception("Redis error")
    mock_logger = mocker.patch("session.logger.error")
    
    service = RedisSessionService()
    service._load_all("user1")
    mock_logger.assert_called_once()

def test_get_session_impl(mock_redis, mocker):
    service = RedisSessionService()
    mocker.patch.object(service, "_load_all")
    mocker.patch("session.InMemorySessionService._get_session_impl", return_value="sess")
    
    res = service._get_session_impl(session_id="user1")
    service._load_all.assert_called_once_with("user1")
    assert res == "sess"

def test_create_session_impl(mock_redis, mocker):
    service = RedisSessionService()
    mocker.patch.object(service, "_load_all")
    mocker.patch.object(service, "_save_all")
    mocker.patch("session.InMemorySessionService._create_session_impl", return_value="new_sess")
    
    res = service._create_session_impl(session_id="user1")
    service._load_all.assert_called_once_with("user1")
    service._save_all.assert_called_once_with("user1")
    assert res == "new_sess"

def test_delete_session_impl(mock_redis, mocker):
    service = RedisSessionService()
    mocker.patch.object(service, "_load_all")
    mocker.patch.object(service, "_save_all")
    mocker.patch("session.InMemorySessionService._delete_session_impl")
    
    service._delete_session_impl(session_id="user1")
    service._load_all.assert_called_once_with("user1")
    service._save_all.assert_called_once_with("user1")

@pytest.mark.asyncio
async def test_append_event(mock_redis, mocker):
    service = RedisSessionService()
    mocker.patch.object(service, "_load_all")
    mocker.patch.object(service, "_save_all")
    
    async def mock_super_append(*args, **kwargs):
        return "event_appended"
        
    mocker.patch("session.InMemorySessionService.append_event", new=mock_super_append)
    
    mock_sess = MagicMock()
    mock_sess.id = "user1"
    
    res = await service.append_event(mock_sess, "event")
    service._load_all.assert_called_once_with("user1")
    service._save_all.assert_called_once_with("user1")
    assert res == "event_appended"
