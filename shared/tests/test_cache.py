"""Tests unitaires pour shared/cache.py.

Couvre :
- RedisServiceDB enum (mapping service → DB number)
- _build_redis_url() : priorité REDIS_URL, SERVICE_NAME, fallback
- get_cache / set_cache / delete_cache / clear_namespace : cas nominaux et erreurs
- Edge cases : préfixe vide, ttl=0, valeur non-JSON, multi-page SCAN
"""
import json
from unittest.mock import AsyncMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures communes
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_redis_pool():
    """Reset le pool global avant chaque test pour garantir l'isolation."""
    import shared.cache
    shared.cache._redis_pool = None
    yield
    shared.cache._redis_pool = None


# ─────────────────────────────────────────────────────────────────────────────
# Section A — RedisServiceDB enum
# ─────────────────────────────────────────────────────────────────────────────

class TestRedisServiceDB:

    def test_all_services_have_unique_db(self):
        """Chaque service doit avoir un numéro de DB unique."""
        from shared.cache import RedisServiceDB
        values = [m.value for m in RedisServiceDB]
        assert len(values) == len(set(values)), "Collision de numéro de DB Redis détectée"

    def test_known_services_db_numbers(self):
        """Vérifie le mapping canonique service → DB number."""
        from shared.cache import RedisServiceDB
        assert RedisServiceDB.users_api == 0
        assert RedisServiceDB.items_api == 1
        assert RedisServiceDB.agent_router_api == 2
        assert RedisServiceDB.competencies_api == 3
        assert RedisServiceDB.cv_api == 4
        assert RedisServiceDB.prompts_api == 5
        assert RedisServiceDB.drive_api == 6
        assert RedisServiceDB.analytics_mcp == 7
        assert RedisServiceDB.missions_api == 8
        assert RedisServiceDB.monitoring_mcp == 9
        assert RedisServiceDB.agent_hr_api == 10
        assert RedisServiceDB.agent_ops_api == 11
        assert RedisServiceDB.agent_missions_api == 12

    def test_enum_is_int(self):
        """RedisServiceDB.cv_api est utilisable directement comme int."""
        from shared.cache import RedisServiceDB
        assert RedisServiceDB.cv_api == 4
        assert int(RedisServiceDB.cv_api) == 4
        url = f"redis://redis:6379/{RedisServiceDB.cv_api}"
        assert url == "redis://redis:6379/4"


# ─────────────────────────────────────────────────────────────────────────────
# Section B — _build_redis_url : logique de priorité
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildRedisUrl:

    def test_explicit_redis_url_takes_priority(self, monkeypatch):
        """REDIS_URL explicit override > SERVICE_NAME."""
        from shared.cache import _build_redis_url
        monkeypatch.setenv("REDIS_URL", "redis://custom:6380/9")
        monkeypatch.setenv("SERVICE_NAME", "cv_api")
        url = _build_redis_url()
        assert url == "redis://custom:6380/9"

    def test_service_name_resolves_correct_db(self, monkeypatch):
        """SERVICE_NAME=cv_api → DB 4."""
        from shared.cache import _build_redis_url
        monkeypatch.delenv("REDIS_URL", raising=False)
        monkeypatch.setenv("SERVICE_NAME", "cv_api")
        url = _build_redis_url()
        assert url == "redis://redis:6379/4"

    def test_service_name_missions_api(self, monkeypatch):
        """SERVICE_NAME=missions_api → DB 8."""
        from shared.cache import _build_redis_url
        monkeypatch.delenv("REDIS_URL", raising=False)
        monkeypatch.setenv("SERVICE_NAME", "missions_api")
        url = _build_redis_url()
        assert url == "redis://redis:6379/8"

    def test_service_name_agent_router_api(self, monkeypatch):
        """SERVICE_NAME=agent_router_api → DB 2."""
        from shared.cache import _build_redis_url
        monkeypatch.delenv("REDIS_URL", raising=False)
        monkeypatch.setenv("SERVICE_NAME", "agent_router_api")
        url = _build_redis_url()
        assert url == "redis://redis:6379/2"

    def test_unknown_service_name_raises_value_error(self, monkeypatch):
        """SERVICE_NAME inconnu → ValueError explicite (fail-fast)."""
        from shared.cache import _build_redis_url
        monkeypatch.delenv("REDIS_URL", raising=False)
        monkeypatch.setenv("SERVICE_NAME", "unknown_service_xyz")
        with pytest.raises(ValueError, match="inconnu"):
            _build_redis_url()

    def test_no_env_fallback_returns_db0(self, monkeypatch):
        """Sans REDIS_URL ni SERVICE_NAME → fallback redis://redis:6379/0."""
        from shared.cache import _build_redis_url
        monkeypatch.delenv("REDIS_URL", raising=False)
        monkeypatch.delenv("SERVICE_NAME", raising=False)
        url = _build_redis_url()
        assert url == "redis://redis:6379/0"

    def test_custom_redis_host_port_via_env(self, monkeypatch):
        """REDIS_HOST + REDIS_PORT sont respectés quand SERVICE_NAME est fourni."""
        from shared.cache import _build_redis_url
        monkeypatch.delenv("REDIS_URL", raising=False)
        monkeypatch.setenv("SERVICE_NAME", "users_api")
        monkeypatch.setenv("REDIS_HOST", "myredis.internal")
        monkeypatch.setenv("REDIS_PORT", "6380")
        url = _build_redis_url()
        assert url == "redis://myredis.internal:6380/0"


# ─────────────────────────────────────────────────────────────────────────────
# Section C — get_cache
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_cache_success():
    from shared.cache import get_cache
    mock_redis = AsyncMock()
    mock_redis.get.return_value = json.dumps({"test": "value"})
    with patch("shared.cache._get_redis", return_value=mock_redis):
        result = await get_cache("my_key")
    assert result == {"test": "value"}
    mock_redis.get.assert_called_once_with("my_key")


@pytest.mark.asyncio
async def test_get_cache_miss():
    from shared.cache import get_cache
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    with patch("shared.cache._get_redis", return_value=mock_redis):
        result = await get_cache("missing_key")
    assert result is None


@pytest.mark.asyncio
async def test_get_cache_connection_error():
    """Erreur Redis → retourne None sans crasher (fail-open)."""
    from shared.cache import get_cache
    mock_redis = AsyncMock()
    mock_redis.get.side_effect = Exception("Redis down")
    with patch("shared.cache._get_redis", return_value=mock_redis):
        result = await get_cache("error_key")
    assert result is None


@pytest.mark.asyncio
async def test_get_cache_non_json_value_returns_none():
    """Valeur Redis non-JSON (source externe) → retourne None sans crasher."""
    from shared.cache import get_cache
    mock_redis = AsyncMock()
    mock_redis.get.return_value = "not-json-{broken"
    with patch("shared.cache._get_redis", return_value=mock_redis):
        result = await get_cache("bad_json_key")
    assert result is None


@pytest.mark.asyncio
async def test_get_cache_plain_string_is_non_json():
    """Valeur Redis = chaîne brute sans guillemets JSON → retourne None."""
    from shared.cache import get_cache
    mock_redis = AsyncMock()
    mock_redis.get.return_value = "plain_text_no_quotes"
    with patch("shared.cache._get_redis", return_value=mock_redis):
        result = await get_cache("str_key")
    assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# Section D — set_cache
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_set_cache_success():
    from shared.cache import set_cache
    mock_redis = AsyncMock()
    mock_redis.set.return_value = True
    with patch("shared.cache._get_redis", return_value=mock_redis):
        result = await set_cache("my_key", {"a": 1}, 60)
    assert result is True
    mock_redis.set.assert_called_once_with("my_key", '{"a": 1}', ex=60)


@pytest.mark.asyncio
async def test_set_cache_connection_error():
    """Erreur Redis → retourne False sans crasher."""
    from shared.cache import set_cache
    mock_redis = AsyncMock()
    mock_redis.set.side_effect = Exception("Connection lost")
    with patch("shared.cache._get_redis", return_value=mock_redis):
        result = await set_cache("my_key", {"a": 1}, 60)
    assert result is False


@pytest.mark.asyncio
async def test_set_cache_zero_ttl_raises_value_error():
    """ttl_seconds=0 → ValueError explicite (Redis refuse ex=0)."""
    from shared.cache import set_cache
    with pytest.raises(ValueError, match="ttl_seconds doit être >= 1"):
        await set_cache("key", "val", ttl_seconds=0)


@pytest.mark.asyncio
async def test_set_cache_negative_ttl_raises_value_error():
    """ttl_seconds négatif → ValueError."""
    from shared.cache import set_cache
    with pytest.raises(ValueError, match="ttl_seconds doit être >= 1"):
        await set_cache("key", "val", ttl_seconds=-5)


# ─────────────────────────────────────────────────────────────────────────────
# Section E — delete_cache
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_cache_success():
    from shared.cache import delete_cache
    mock_redis = AsyncMock()
    mock_redis.delete.return_value = 1
    with patch("shared.cache._get_redis", return_value=mock_redis):
        result = await delete_cache("my_key")
    assert result is True
    mock_redis.delete.assert_called_once_with("my_key")


@pytest.mark.asyncio
async def test_delete_cache_connection_error():
    """Erreur Redis → retourne False sans crasher."""
    from shared.cache import delete_cache
    mock_redis = AsyncMock()
    mock_redis.delete.side_effect = Exception("Connection lost")
    with patch("shared.cache._get_redis", return_value=mock_redis):
        result = await delete_cache("my_key")
    assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# Section F — clear_namespace
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_clear_namespace_success():
    from shared.cache import clear_namespace
    mock_redis = AsyncMock()
    mock_redis.scan.return_value = (0, ["cv_api:test1", "cv_api:test2"])
    with patch("shared.cache._get_redis", return_value=mock_redis):
        result = await clear_namespace("cv_api:")
    assert result == 2
    mock_redis.scan.assert_called_once_with(cursor=0, match="cv_api:*")
    mock_redis.delete.assert_called_once_with("cv_api:test1", "cv_api:test2")


@pytest.mark.asyncio
async def test_clear_namespace_empty_result():
    """Aucune clé correspondante → retourne 0."""
    from shared.cache import clear_namespace
    mock_redis = AsyncMock()
    mock_redis.scan.return_value = (0, [])
    with patch("shared.cache._get_redis", return_value=mock_redis):
        result = await clear_namespace("cv_api:")
    assert result == 0
    mock_redis.delete.assert_not_called()


@pytest.mark.asyncio
async def test_clear_namespace_pagination():
    """SCAN multi-pages → toutes les pages sont traitées."""
    from shared.cache import clear_namespace
    mock_redis = AsyncMock()
    mock_redis.scan.side_effect = [
        (10, ["key1", "key2"]),
        (0, ["key3"]),
    ]
    with patch("shared.cache._get_redis", return_value=mock_redis):
        result = await clear_namespace("test_prefix:")
    assert result == 3
    assert mock_redis.scan.call_count == 2
    assert mock_redis.delete.call_count == 2


@pytest.mark.asyncio
async def test_clear_namespace_empty_prefix_raises():
    """Préfixe vide → ValueError (protection contre FLUSHDB accidentel)."""
    from shared.cache import clear_namespace
    with pytest.raises(ValueError, match="TOUTE la base"):
        await clear_namespace("")


@pytest.mark.asyncio
async def test_clear_namespace_whitespace_prefix_raises():
    """Préfixe uniquement espaces → ValueError."""
    from shared.cache import clear_namespace
    with pytest.raises(ValueError, match="TOUTE la base"):
        await clear_namespace("   ")


@pytest.mark.asyncio
async def test_clear_namespace_connection_error():
    """Erreur Redis → retourne 0 sans crasher."""
    from shared.cache import clear_namespace
    mock_redis = AsyncMock()
    mock_redis.scan.side_effect = Exception("Connection error")
    with patch("shared.cache._get_redis", return_value=mock_redis):
        result = await clear_namespace("prefix:")
    assert result == 0
