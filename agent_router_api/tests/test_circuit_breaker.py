"""Tests unitaires pour le circuit-breaker A2A (Guardrail P0-3).

Couvre :
- _is_circuit_open : fermé par défaut, s'ouvre après CB_FAILURE_THRESHOLD échecs.
- _record_failure / _record_success : transitions d'état correctes.
- Réouverture automatique après CB_OPEN_DURATION_S (test avec freeze du temps).
- _call_sub_agent : retour immédiat en mode dégradé si circuit ouvert.
- _call_sub_agent : appelle _record_failure après deux échecs réseau.
- _call_sub_agent : appelle _record_success après un succès et reset le circuit.
- Structure de la réponse dégradée du circuit-breaker (CB_OPEN).
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

import a2a_tools
from a2a_tools import (
    CB_FAILURE_THRESHOLD,
    CB_OPEN_DURATION_S,
    _cb_state,
    _is_circuit_open,
    _record_failure,
    _record_success,
)


# ---------------------------------------------------------------------------
# Fixture : réinitialise l'état du circuit-breaker avant chaque test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_cb_state():
    """Ensure circuit-breaker state is clean between tests."""
    _cb_state.clear()
    yield
    _cb_state.clear()


# ---------------------------------------------------------------------------
# Tests des fonctions pures du circuit-breaker
# ---------------------------------------------------------------------------

class TestCircuitBreakerState:
    def test_circuit_closed_by_default(self):
        """Un agent inconnu a un circuit fermé par défaut."""
        assert _is_circuit_open("unknown_agent") is False

    def test_circuit_stays_closed_below_threshold(self):
        """Moins de CB_FAILURE_THRESHOLD échecs → circuit fermé."""
        for _ in range(CB_FAILURE_THRESHOLD - 1):
            _record_failure("hr_agent")
        assert _is_circuit_open("hr_agent") is False

    def test_circuit_opens_at_threshold(self):
        """Exactement CB_FAILURE_THRESHOLD échecs → circuit ouvert."""
        for _ in range(CB_FAILURE_THRESHOLD):
            _record_failure("missions_agent")
        assert _is_circuit_open("missions_agent") is True

    def test_circuit_remains_open_above_threshold(self):
        """Plus de CB_FAILURE_THRESHOLD échecs → circuit toujours ouvert."""
        for _ in range(CB_FAILURE_THRESHOLD + 3):
            _record_failure("ops_agent")
        assert _is_circuit_open("ops_agent") is True

    def test_success_resets_circuit(self):
        """Un succès après des échecs remet le circuit à zéro."""
        for _ in range(CB_FAILURE_THRESHOLD):
            _record_failure("hr_agent")
        assert _is_circuit_open("hr_agent") is True
        _record_success("hr_agent")
        assert _is_circuit_open("hr_agent") is False

    def test_success_on_unknown_agent_is_safe(self):
        """_record_success sur un agent inconnu ne doit pas lever d'exception."""
        _record_success("nonexistent_agent")  # must not raise

    def test_circuit_auto_closes_after_cooldown(self):
        """Après CB_OPEN_DURATION_S, le circuit doit se fermer automatiquement."""
        for _ in range(CB_FAILURE_THRESHOLD):
            _record_failure("hr_agent")
        assert _is_circuit_open("hr_agent") is True

        # Simulate time passing beyond the cooldown period
        _cb_state["hr_agent"]["open_until"] = time.monotonic() - 1.0
        assert _is_circuit_open("hr_agent") is False

    def test_failure_counter_resets_after_success(self):
        """Après _record_success, un nouvel échec unique ne rouvre pas le circuit."""
        for _ in range(CB_FAILURE_THRESHOLD):
            _record_failure("missions_agent")
        _record_success("missions_agent")
        _record_failure("missions_agent")
        # Only 1 failure after reset — circuit must be closed
        assert _is_circuit_open("missions_agent") is False

    def test_multiple_agents_are_independent(self):
        """Les états des agents sont indépendants les uns des autres."""
        for _ in range(CB_FAILURE_THRESHOLD):
            _record_failure("hr_agent")
        # ops_agent should remain closed
        assert _is_circuit_open("hr_agent") is True
        assert _is_circuit_open("ops_agent") is False

    def test_cb_state_dict_created_on_first_failure(self):
        """_cb_state est initialisé à la première défaillance."""
        assert "new_agent" not in _cb_state
        _record_failure("new_agent")
        assert "new_agent" in _cb_state


# ---------------------------------------------------------------------------
# Tests d'intégration : _call_sub_agent avec circuit-breaker
# ---------------------------------------------------------------------------

VALID_A2A_RESPONSE = {
    "response": "OK",
    "data": None,
    "steps": [{"type": "call", "tool": "search_users", "args": {}}],
    "thoughts": "",
    "usage": {"total_input_tokens": 10, "total_output_tokens": 5, "estimated_cost_usd": 0.0},
}


@pytest.mark.asyncio
async def test_call_sub_agent_returns_degraded_when_circuit_open(mocker):
    """Si le circuit est ouvert, _call_sub_agent retourne immédiatement en mode dégradé."""
    mocker.patch("a2a_tools.A2A_CALL_DURATION")
    mocker.patch("a2a_tools.A2A_CALL_ERRORS_TOTAL")
    mocker.patch("a2a_tools.A2A_CALL_RETRIES_TOTAL")

    # Force circuit open
    for _ in range(CB_FAILURE_THRESHOLD):
        _record_failure("hr_agent")
    assert _is_circuit_open("hr_agent") is True

    # http should never be called
    mock_client = AsyncMock()
    mocker.patch("a2a_tools.httpx.AsyncClient", return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=mock_client),
        __aexit__=AsyncMock(return_value=False),
    ))

    from a2a_tools import _call_sub_agent
    result = await _call_sub_agent("hr_agent", "http://fake:8080", "test", "user_1")

    assert result["degraded"] is True
    assert result["reason"] == "circuit_breaker_open"
    assert "CB_OPEN" in result["steps"][0]["tool"]
    # HTTP must NOT have been called
    mock_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_call_sub_agent_degraded_cb_open_response_structure(mocker):
    """La réponse dégradée CB_OPEN respecte la structure A2A standard."""
    mocker.patch("a2a_tools.A2A_CALL_DURATION")
    mocker.patch("a2a_tools.A2A_CALL_ERRORS_TOTAL")
    mocker.patch("a2a_tools.A2A_CALL_RETRIES_TOTAL")

    for _ in range(CB_FAILURE_THRESHOLD):
        _record_failure("missions_agent")

    from a2a_tools import _call_sub_agent
    result = await _call_sub_agent("missions_agent", "http://fake:8080", "test", "user_1")

    assert "response" in result
    assert "degraded" in result and result["degraded"] is True
    assert "reason" in result
    assert isinstance(result["steps"], list)
    assert len(result["steps"]) == 1
    assert result["steps"][0]["type"] == "warning"
    assert result["data"] is None
    assert result["usage"]["total_input_tokens"] == 0


@pytest.mark.asyncio
async def test_call_sub_agent_records_failure_on_network_error(mocker):
    """_call_sub_agent appelle _record_failure si tous les essais échouent."""
    mocker.patch("a2a_tools.A2A_CALL_DURATION")
    mocker.patch("a2a_tools.A2A_CALL_ERRORS_TOTAL")
    mocker.patch("a2a_tools.A2A_CALL_RETRIES_TOTAL")
    mocker.patch("asyncio.sleep", new_callable=AsyncMock)

    mock_client = AsyncMock()
    mock_client.post.side_effect = httpx.ConnectError("refused")
    mocker.patch("a2a_tools.httpx.AsyncClient", return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=mock_client),
        __aexit__=AsyncMock(return_value=False),
    ))

    from a2a_tools import _call_sub_agent
    # First failing call
    await _call_sub_agent("hr_agent", "http://fake:8080", "test", "user_1")
    assert _cb_state.get("hr_agent", {}).get("failures", 0) == 1

    # Second failing call triggers circuit open
    await _call_sub_agent("hr_agent", "http://fake:8080", "test", "user_1")
    assert _is_circuit_open("hr_agent") is True


@pytest.mark.asyncio
async def test_call_sub_agent_records_success_and_resets_circuit(mocker):
    """_record_success est appelé après un call réussi et remet le circuit à 0."""
    mocker.patch("a2a_tools.A2A_CALL_DURATION")
    mocker.patch("a2a_tools.A2A_CALL_ERRORS_TOTAL")
    mocker.patch("a2a_tools.A2A_CALL_RETRIES_TOTAL")

    # Pre-seed one failure
    _record_failure("ops_agent")
    assert _cb_state["ops_agent"]["failures"] == 1

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = VALID_A2A_RESPONSE
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mocker.patch("a2a_tools.httpx.AsyncClient", return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=mock_client),
        __aexit__=AsyncMock(return_value=False),
    ))

    from a2a_tools import _call_sub_agent
    result = await _call_sub_agent("ops_agent", "http://fake:8080", "test", "user_1")

    assert result["response"] == "OK"
    assert _cb_state["ops_agent"]["failures"] == 0
    assert _cb_state["ops_agent"]["open_until"] == 0.0


@pytest.mark.asyncio
async def test_circuit_breaker_does_not_block_different_agents(mocker):
    """Un circuit ouvert sur hr_agent ne doit pas bloquer missions_agent."""
    mocker.patch("a2a_tools.A2A_CALL_DURATION")
    mocker.patch("a2a_tools.A2A_CALL_ERRORS_TOTAL")
    mocker.patch("a2a_tools.A2A_CALL_RETRIES_TOTAL")

    # Open circuit for hr_agent only
    for _ in range(CB_FAILURE_THRESHOLD):
        _record_failure("hr_agent")
    assert _is_circuit_open("hr_agent") is True
    assert _is_circuit_open("missions_agent") is False

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = VALID_A2A_RESPONSE
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mocker.patch("a2a_tools.httpx.AsyncClient", return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=mock_client),
        __aexit__=AsyncMock(return_value=False),
    ))

    from a2a_tools import _call_sub_agent
    result = await _call_sub_agent("missions_agent", "http://fake:8080", "test", "user_1")
    # missions_agent should succeed normally
    assert result["response"] == "OK"
    assert result.get("degraded") is None


@pytest.mark.asyncio
async def test_circuit_closes_after_cooldown_and_allows_new_call(mocker):
    """Après expiration du cooldown, le circuit se ferme et les appels passent à nouveau."""
    mocker.patch("a2a_tools.A2A_CALL_DURATION")
    mocker.patch("a2a_tools.A2A_CALL_ERRORS_TOTAL")
    mocker.patch("a2a_tools.A2A_CALL_RETRIES_TOTAL")

    # Force circuit open then immediately expire it
    for _ in range(CB_FAILURE_THRESHOLD):
        _record_failure("hr_agent")
    _cb_state["hr_agent"]["open_until"] = time.monotonic() - 1.0  # Expire cooldown

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = VALID_A2A_RESPONSE
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mocker.patch("a2a_tools.httpx.AsyncClient", return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=mock_client),
        __aexit__=AsyncMock(return_value=False),
    ))

    from a2a_tools import _call_sub_agent
    result = await _call_sub_agent("hr_agent", "http://fake:8080", "test", "user_1")
    # After cooldown expired, the call should go through
    assert result["response"] == "OK"
    assert result.get("degraded") is None


# ---------------------------------------------------------------------------
# Tests des constantes d'environnement
# ---------------------------------------------------------------------------

class TestCircuitBreakerConfig:
    def test_default_threshold_is_two(self):
        """CB_FAILURE_THRESHOLD doit valoir 2 par défaut."""
        assert CB_FAILURE_THRESHOLD == 2

    def test_default_open_duration_is_thirty(self):
        """CB_OPEN_DURATION_S doit valoir 30 par défaut."""
        assert CB_OPEN_DURATION_S == 30.0

    def test_threshold_configurable_via_env(self, monkeypatch):
        """CB_FAILURE_THRESHOLD est surchargeable via A2A_CB_FAILURE_THRESHOLD."""
        monkeypatch.setenv("A2A_CB_FAILURE_THRESHOLD", "5")
        import importlib
        importlib.reload(a2a_tools)
        assert a2a_tools.CB_FAILURE_THRESHOLD == 5
        # Restore default
        importlib.reload(a2a_tools)
