"""
Tests unitaires pour le circuit breaker avec backend Redis distribué.

Couvre :
  - Chargement et application de l'état depuis Redis (_from_dict, merge)
  - Persistance après transition (CLOSED → OPEN)
  - Fallback in-memory quand Redis retourne None ou une erreur
  - Absence de REDIS_URL → backend désactivé silencieusement
"""

import asyncio
import json
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agent_commons.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
    _RedisStateBackend,
    get_circuit_breaker,
    _registry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_cb(**kwargs) -> CircuitBreaker:
    name = kwargs.pop("name", f"test_cb_{id(kwargs)}")
    failure_threshold = kwargs.pop("failure_threshold", 3)
    recovery_timeout = kwargs.pop("recovery_timeout", 30.0)
    return CircuitBreaker(name=name, failure_threshold=failure_threshold, recovery_timeout=recovery_timeout, **kwargs)


async def _ok_func():
    return "ok"


async def _fail_func():
    raise RuntimeError("service unavailable")


# ---------------------------------------------------------------------------
# Tests _RedisStateBackend
# ---------------------------------------------------------------------------

class TestRedisStateBackend:

    @pytest.mark.asyncio
    async def test_load_returns_none_when_no_redis_url(self):
        """Sans REDIS_URL, le backend ne contacte pas Redis et retourne None."""
        backend = _RedisStateBackend("test")
        with patch.dict("os.environ", {}, clear=True):
            # S'assurer que REDIS_URL n'est pas dans l'env
            import os
            os.environ.pop("REDIS_URL", None)
            backend._initialized = False
            result = await backend.load()
        assert result is None

    @pytest.mark.asyncio
    async def test_load_returns_parsed_json(self):
        """Vérifie que load() désérialise correctement la valeur Redis."""
        backend = _RedisStateBackend("test")
        mock_client = AsyncMock()
        mock_client.get.return_value = json.dumps({"state": "OPEN", "failure_count": 5})
        backend._client = mock_client
        backend._initialized = True

        result = await backend.load()
        assert result == {"state": "OPEN", "failure_count": 5}

    @pytest.mark.asyncio
    async def test_load_returns_none_on_redis_error(self):
        """Si Redis lève une exception, load() retourne None (fail-open)."""
        backend = _RedisStateBackend("test")
        mock_client = AsyncMock()
        mock_client.get.side_effect = ConnectionError("Redis down")
        backend._client = mock_client
        backend._initialized = True

        result = await backend.load()
        assert result is None

    @pytest.mark.asyncio
    async def test_save_serializes_json(self):
        """Vérifie que save() appelle SET avec le JSON de l'état et un TTL."""
        backend = _RedisStateBackend("my_service")
        mock_client = AsyncMock()
        backend._client = mock_client
        backend._initialized = True

        state = {"state": "CLOSED", "failure_count": 0}
        await backend.save(state)

        mock_client.set.assert_called_once()
        call_args = mock_client.set.call_args
        assert call_args[0][0] == "cb:my_service"
        assert json.loads(call_args[0][1]) == state
        assert "ex" in call_args[1]  # TTL présent

    @pytest.mark.asyncio
    async def test_save_silently_ignores_redis_error(self):
        """Une erreur Redis dans save() ne propage pas d'exception."""
        backend = _RedisStateBackend("test")
        mock_client = AsyncMock()
        mock_client.set.side_effect = ConnectionError("Redis down")
        backend._client = mock_client
        backend._initialized = True

        # Ne doit pas lever d'exception
        await backend.save({"state": "OPEN", "failure_count": 3})


# ---------------------------------------------------------------------------
# Tests CircuitBreaker._from_dict (merge optimiste)
# ---------------------------------------------------------------------------

class TestCircuitBreakerMerge:

    def test_from_dict_adopts_open_state_from_remote(self):
        """Si Redis est OPEN et local est CLOSED, on adopte OPEN."""
        cb = make_cb(name="merge_test_open")
        cb._state = CircuitState.CLOSED
        cb._failure_count = 1
        cb._from_dict({
            "state": "OPEN",
            "failure_count": 5,
            "success_count": 0,
            "last_failure_time": time.monotonic(),
        })
        assert cb._state == CircuitState.OPEN
        assert cb._failure_count == 5

    def test_from_dict_keeps_local_if_worse(self):
        """Si local est déjà OPEN, un état CLOSED distant n'efface pas l'état local."""
        cb = make_cb(name="merge_test_keep")
        cb._state = CircuitState.OPEN
        cb._failure_count = 6
        cb._from_dict({
            "state": "CLOSED",
            "failure_count": 0,
            "success_count": 0,
            "last_failure_time": None,
        })
        # L'état dégradé local doit être conservé
        assert cb._state == CircuitState.OPEN
        assert cb._failure_count == 6

    def test_from_dict_ignores_parse_error(self):
        """Une donnée malformée depuis Redis ne doit pas faire crasher le circuit breaker."""
        cb = make_cb(name="merge_test_error")
        cb._state = CircuitState.CLOSED
        # Appel avec un dict invalide
        cb._from_dict({"state": "UNKNOWN_STATE", "failure_count": "not_a_number"})
        # L'état local ne doit pas avoir changé
        assert cb._state == CircuitState.CLOSED


# ---------------------------------------------------------------------------
# Tests CircuitBreaker.call() avec Redis mock
# ---------------------------------------------------------------------------

class TestCircuitBreakerCallWithRedis:

    @pytest.mark.asyncio
    async def test_call_success_does_not_persist_when_state_unchanged(self):
        """Un appel réussi en CLOSED n'appelle pas Redis.save() (optimisation)."""
        cb = make_cb(name="call_success_no_save")
        cb._redis._client = AsyncMock()
        cb._redis._initialized = True
        cb._redis._client.get.return_value = None  # Pas d'état Redis

        result = await cb.call(_ok_func)
        assert result == "ok"
        cb._redis._client.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_call_failure_persists_state_to_redis(self):
        """Un appel échoué doit persister le nouvel état dans Redis."""
        cb = make_cb(name="call_fail_save")
        mock_client = AsyncMock()
        mock_client.get.return_value = None
        cb._redis._client = mock_client
        cb._redis._initialized = True

        with pytest.raises(RuntimeError):
            await cb.call(_fail_func)

        mock_client.set.assert_called_once()
        saved_state = json.loads(mock_client.set.call_args[0][1])
        assert saved_state["failure_count"] == 1

    @pytest.mark.asyncio
    async def test_open_state_loaded_from_redis_blocks_call(self):
        """Si Redis indique OPEN, le circuit bloque sans appeler la fonction."""
        cb = make_cb(name="call_open_redis")
        mock_client = AsyncMock()
        mock_client.get.return_value = json.dumps({
            "state": "OPEN",
            "failure_count": 5,
            "success_count": 0,
            "last_failure_time": time.monotonic(),
        })
        cb._redis._client = mock_client
        cb._redis._initialized = True

        with pytest.raises(CircuitOpenError) as exc_info:
            await cb.call(_ok_func)

        assert exc_info.value.name == "call_open_redis"

    @pytest.mark.asyncio
    async def test_call_works_without_redis(self):
        """Sans Redis (client=None), le circuit fonctionne en mode in-memory."""
        cb = make_cb(name="call_no_redis")
        cb._redis._client = None
        cb._redis._initialized = True  # Force "pas de Redis"

        result = await cb.call(_ok_func)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_transition_open_persists_state(self):
        """Quand le circuit passe CLOSED → OPEN, l'état est persisté dans Redis."""
        cb = make_cb(name="call_transition_open", failure_threshold=2)
        mock_client = AsyncMock()
        mock_client.get.return_value = None
        cb._redis._client = mock_client
        cb._redis._initialized = True

        # 2 échecs → passage OPEN
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await cb.call(_fail_func)

        # La dernière persistance doit avoir state=OPEN
        last_call = mock_client.set.call_args
        saved_state = json.loads(last_call[0][1])
        assert saved_state["state"] == "OPEN"

    @pytest.mark.asyncio
    async def test_circuit_open_error_not_counted_as_failure(self):
        """Une CircuitOpenError re-levée ne doit pas incrémenter failure_count."""
        cb = make_cb(name="call_open_passthrough")
        # Simuler un circuit déjà OPEN
        cb._state = CircuitState.OPEN
        cb._last_failure_time = time.monotonic()
        cb._redis._initialized = True
        cb._redis._client = None

        failure_count_before = cb._failure_count

        with pytest.raises(CircuitOpenError):
            await cb.call(_ok_func)

        assert cb._failure_count == failure_count_before
