"""
Tests de résilience A2A — Circuit-Breaker [ADR12-2]

Ces tests s'exécutent dans l'environnement Docker standard (via run_tests.sh).
Ils mockent uniquement les appels httpx sortants, sans toucher aux dépendances système.
"""
import pytest
import json
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call
import httpx


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_A2A_RESPONSE = {
    "response": "Voici les résultats.",
    "data": {"items": []},
    "steps": [{"type": "call", "tool": "search_best_candidates", "args": {}}],
    "thoughts": "Je cherche dans la base...",
    "usage": {"total_input_tokens": 100, "total_output_tokens": 50},
}


def make_mock_async_client(responses):
    """
    Retourne un context manager AsyncClient dont post() retourne
    successivement les éléments de `responses` (peut être Exception ou MagicMock).
    """
    call_count = 0

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def post(self, *a, **kw):
            nonlocal call_count
            r = responses[min(call_count, len(responses) - 1)]
            call_count += 1
            if isinstance(r, BaseException):
                raise r
            return r

    return _FakeClient(), call_count


# ---------------------------------------------------------------------------
# Tests _call_sub_agent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_call_sub_agent_success_first_attempt(mocker):
    """Succès au premier essai — aucune métrique d'erreur ou retry."""
    mock_duration = mocker.patch("agent.A2A_CALL_DURATION")
    mock_errors = mocker.patch("agent.A2A_CALL_ERRORS_TOTAL")
    mock_retries = mocker.patch("agent.A2A_CALL_RETRIES_TOTAL")

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = VALID_A2A_RESPONSE
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mocker.patch("agent.httpx.AsyncClient", return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=mock_client),
        __aexit__=AsyncMock(return_value=False),
    ))

    from agent import _call_sub_agent
    result = await _call_sub_agent(
        agent_name="hr_agent",
        url="http://fake-hr:8080",
        query="Trouve-moi des candidats Python",
        user_id="user_1",
        timeout=60.0,
        auth_header="Bearer fake-token",
    )

    assert result["response"] == "Voici les résultats."
    assert result.get("degraded") is None
    mock_duration.labels.assert_called_once_with(agent="hr_agent")
    mock_errors.labels.assert_not_called()
    mock_retries.labels.assert_not_called()


@pytest.mark.asyncio
async def test_call_sub_agent_retry_on_connect_error(mocker):
    """Erreur réseau au 1er essai → retry → succès."""
    mocker.patch("agent.A2A_CALL_RETRIES_TOTAL")
    mocker.patch("agent.A2A_CALL_ERRORS_TOTAL")
    mocker.patch("agent.A2A_CALL_DURATION")
    mocker.patch("asyncio.sleep", new_callable=AsyncMock)

    call_count = 0
    mock_resp_ok = MagicMock(spec=httpx.Response)
    mock_resp_ok.status_code = 200
    mock_resp_ok.json.return_value = VALID_A2A_RESPONSE
    mock_resp_ok.raise_for_status = MagicMock()

    mock_client = AsyncMock()

    async def post_side_effect(*a, **kw):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.ConnectError("Connection refused")
        return mock_resp_ok

    mock_client.post.side_effect = post_side_effect
    mocker.patch("agent.httpx.AsyncClient", return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=mock_client),
        __aexit__=AsyncMock(return_value=False),
    ))

    from agent import _call_sub_agent
    result = await _call_sub_agent(
        agent_name="hr_agent",
        url="http://fake-hr:8080",
        query="test",
        user_id="user_1",
        timeout=60.0,
        auth_header=None,
    )

    assert result["response"] == "Voici les résultats."
    assert result.get("degraded") is None
    assert call_count == 2  # 1 échec + 1 retry réussi


@pytest.mark.asyncio
async def test_call_sub_agent_no_retry_on_4xx(mocker):
    """Erreur 4xx → dégradation immédiate, PAS de retry."""
    mocker.patch("agent.A2A_CALL_RETRIES_TOTAL")
    mock_errors = mocker.patch("agent.A2A_CALL_ERRORS_TOTAL")
    mocker.patch("agent.A2A_CALL_DURATION")

    mock_resp_401 = MagicMock(spec=httpx.Response)
    mock_resp_401.status_code = 401
    mock_resp_401.text = "Unauthorized"
    mock_resp_401.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp_401

    mocker.patch("agent.httpx.AsyncClient", return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=mock_client),
        __aexit__=AsyncMock(return_value=False),
    ))

    from agent import _call_sub_agent
    result = await _call_sub_agent(
        agent_name="missions_agent",
        url="http://fake-missions:8080",
        query="test",
        user_id="user_1",
        timeout=90.0,
        auth_header=None,
    )

    assert result["degraded"] is True
    assert "missions_agent" in result["response"]
    # Un seul appel HTTP — pas de retry sur 4xx
    assert mock_client.post.call_count == 1
    mock_errors.labels.assert_called_once_with(agent="missions_agent", reason="client_error")


@pytest.mark.asyncio
async def test_call_sub_agent_all_attempts_fail_degraded_structure(mocker):
    """Toutes les tentatives échouent → réponse dégradée structurée correcte."""
    mocker.patch("agent.A2A_CALL_RETRIES_TOTAL")
    mocker.patch("agent.A2A_CALL_ERRORS_TOTAL")
    mocker.patch("agent.A2A_CALL_DURATION")
    mocker.patch("asyncio.sleep", new_callable=AsyncMock)

    mock_client = AsyncMock()
    mock_client.post.side_effect = httpx.ConnectError("Port 8080 closed")

    mocker.patch("agent.httpx.AsyncClient", return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=mock_client),
        __aexit__=AsyncMock(return_value=False),
    ))

    from agent import _call_sub_agent
    result = await _call_sub_agent(
        agent_name="hr_agent",
        url="http://fake-hr:8080",
        query="Cherche des devs Python",
        user_id="user_1",
        timeout=60.0,
        auth_header=None,
    )

    # Structure de la réponse dégradée
    assert result["degraded"] is True
    assert "❌" in result["response"]
    assert "hr_agent" in result["response"]
    assert isinstance(result["steps"], list)
    assert len(result["steps"]) == 1
    assert result["steps"][0]["type"] == "warning"
    assert result["steps"][0]["tool"] == "hr_agent:UNAVAILABLE"
    assert result["data"] is None
    assert result["usage"]["total_input_tokens"] == 0
    assert result["usage"]["estimated_cost_usd"] == 0


# ---------------------------------------------------------------------------
# Tests ask_* : propagation du flag degraded
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ask_hr_agent_propagates_degraded(mocker):
    """ask_hr_agent encapsule correctement la réponse dégradée dans 'result' JSON."""
    mocker.patch("mcp_client.auth_header_var")
    degraded = {
        "degraded": True,
        "response": "❌ Le sous-agent hr_agent est temporairement indisponible.",
        "reason": "Connection refused",
        "data": None,
        "steps": [{"type": "warning", "tool": "hr_agent:UNAVAILABLE", "args": {}}],
        "thoughts": "",
        "usage": {"total_input_tokens": 0, "total_output_tokens": 0, "estimated_cost_usd": 0},
    }
    mocker.patch("agent._call_sub_agent", new=AsyncMock(return_value=degraded))

    from agent import ask_hr_agent
    result = await ask_hr_agent("test query")

    parsed = json.loads(result["result"])
    assert parsed["degraded"] is True
    assert "indisponible" in parsed["response"]


@pytest.mark.asyncio
async def test_ask_missions_agent_nominal(mocker):
    """ask_missions_agent retourne le format standard quand le sous-agent répond."""
    mocker.patch("mcp_client.auth_header_var")
    mocker.patch("agent._call_sub_agent", new=AsyncMock(return_value=VALID_A2A_RESPONSE))

    from agent import ask_missions_agent
    result = await ask_missions_agent("Staff la mission M-001")

    parsed = json.loads(result["result"])
    assert parsed["agent"] == "missions_agent"
    assert parsed["response"] == "Voici les résultats."
    assert parsed.get("degraded") is None


@pytest.mark.asyncio
async def test_ask_ops_agent_nominal(mocker):
    """ask_ops_agent retourne le format standard quand le sous-agent répond."""
    mocker.patch("mcp_client.auth_header_var")
    mocker.patch("agent._call_sub_agent", new=AsyncMock(return_value=VALID_A2A_RESPONSE))

    from agent import ask_ops_agent
    result = await ask_ops_agent("Quelle est la santé du système?")

    parsed = json.loads(result["result"])
    assert parsed["agent"] == "ops_agent"
    assert parsed["response"] == "Voici les résultats."
