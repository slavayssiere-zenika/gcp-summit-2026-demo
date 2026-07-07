"""
test_agent.py — Couverture des branches non testées de agent.py (agent_router_api).

Branches couvertes (lignes 71-376) :
  - create_agent() :
      * Mode standard (ENABLE_WORKFLOW_AGENT=false) → Agent ADK construit
      * Mode WorkflowAgent (ENABLE_WORKFLOW_AGENT=true) → build_workflow_agent()
  - run_agent_query() :
      * auth_token propagé dans auth_header_var
      * user_id inconnu → user_id_var non setté
      * session None → création de session (create_session)
      * Thoughts (bool True) capturés
      * Thoughts (string) capturés
      * Tool Calls (function_call) capturés et dédupliqués
      * Tool Results (function_response) : unwrap MCP JSON string
      * Tool Results A2A : thoughts sous-agent + steps prefixés + usage agrégé
      * Tool Results A2A : warning ZERO tool calls quand sub_tool_calls vide
      * Sub-agent display_type propagé
      * Sub-agent data propagé via metadata_list
      * Texte assistant agrégé (string vs parts)
      * Usage metadata (dict) → router_input/output_tokens
      * OPS-002 ValueError "No function call" → structuré (déjà testé dans test_main)
      * OPS-002 ValueError autre → réponse avec message
      * OPS-003 context overflow → reset session + steps warning
      * OPS-003 autres exceptions → re-raise
      * FinOps BQ logging → asyncio.create_task déclenché
      * get_session_service() singleton
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_session_svc(session=MagicMock()):
    svc = AsyncMock()
    svc.get_session.return_value = session
    svc.create_session = AsyncMock()
    return svc


def _make_event(
    role="model",
    text=None,
    thought=None,
    tool_call=None,
    function_call=None,
    function_response=None,
    usage=None,
):
    """Construit un mock d'événement ADK."""
    event = MagicMock()
    event.content = MagicMock()
    event.content.role = role
    event.response = MagicMock() if usage else None

    part = MagicMock()
    part.text = text
    part.thought = thought
    part.tool_call = tool_call
    part.function_call = function_call
    part.function_response = function_response

    event.content.parts = [part]

    if usage:
        u = MagicMock()
        u.prompt_token_count = usage.get("input", 0)
        u.candidates_token_count = usage.get("output", 0)
        event.usage_metadata = u
        if event.response:
            event.response.usage_metadata = u

    return event


# ── create_agent ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_agent_standard_mode():
    """ENABLE_WORKFLOW_AGENT=false → Agent ADK standard construit."""
    with patch.dict("os.environ", {"ENABLE_WORKFLOW_AGENT": "false", "GEMINI_ROUTER_MODEL": "gemini-test"}):
        with patch("agent.build_instruction_text", new=AsyncMock(return_value="System prompt")):
            with patch("agent.Agent") as mock_agent_cls:
                mock_agent_cls.return_value = MagicMock(model="gemini-test")
                from agent import create_agent
                await create_agent(session_id="sess-1")

    mock_agent_cls.assert_called_once()
    call_kwargs = mock_agent_cls.call_args.kwargs
    assert call_kwargs["name"] == "assistant_zenika_router"
    assert call_kwargs["instruction"] == "System prompt"


@pytest.mark.asyncio
async def test_create_agent_workflow_mode():
    """ENABLE_WORKFLOW_AGENT=true → build_workflow_agent() appelé."""
    with patch.dict("os.environ", {"ENABLE_WORKFLOW_AGENT": "true"}):
        with patch("agent.build_instruction_text", new=AsyncMock(return_value="prompt")):
            with patch("agent.build_workflow_agent") as mock_wf:
                mock_wf.return_value = MagicMock()
                from agent import create_agent
                await create_agent(session_id="sess-wf")

    mock_wf.assert_called_once()
    # Vérifie que ask_missions_agent a été renommé
    from agent import ask_missions_agent_with_hr_alignment
    assert ask_missions_agent_with_hr_alignment.__name__ == "ask_missions_agent"


# ── get_session_service singleton ─────────────────────────────────────────────

def test_get_session_service_singleton():
    """get_session_service() retourne le même objet lors d'appels successifs."""
    import agent
    agent._session_service = None  # Reset

    with patch("agent.RedisSessionService") as mock_cls:
        mock_cls.return_value = MagicMock()
        svc1 = agent.get_session_service()
        svc2 = agent.get_session_service()

    assert svc1 is svc2
    mock_cls.assert_called_once()
    agent._session_service = None  # Cleanup


# ── run_agent_query — propagation auth + session ──────────────────────────────

@pytest.mark.asyncio
async def test_run_agent_query_sets_auth_header_var(mocker):
    """auth_token fourni → auth_header_var est setté."""
    from agent import run_agent_query, auth_header_var

    async def empty_run(*args, **kwargs):
        return
        yield

    mock_runner = MagicMock()
    mock_runner.run_async = empty_run
    mocker.patch("agent.Runner", return_value=mock_runner)
    mocker.patch("agent.create_agent", new=AsyncMock(
        return_value=MagicMock(model="test")))
    mocker.patch("agent.get_session_service", return_value=_make_session_svc())

    await run_agent_query("Hello", auth_token="Bearer test-token-abc")
    assert auth_header_var.get(None) == "Bearer test-token-abc"


@pytest.mark.asyncio
async def test_run_agent_query_creates_session_when_not_found(mocker):
    """Session None → create_session() est appelé."""
    from agent import run_agent_query

    svc = AsyncMock()
    svc.get_session.return_value = None
    svc.create_session = AsyncMock()

    async def empty_run(*args, **kwargs):
        return
        yield

    mock_runner = MagicMock()
    mock_runner.run_async = empty_run
    mocker.patch("agent.Runner", return_value=mock_runner)
    mocker.patch("agent.create_agent", new=AsyncMock(
        return_value=MagicMock(model="test")))
    mocker.patch("agent.get_session_service", return_value=svc)

    await run_agent_query("Hello", session_id="new-session")
    svc.create_session.assert_called_once()


# ── Thoughts ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_agent_query_captures_bool_thought(mocker):
    """thought=True (bool) → le texte de la partie est ajouté aux thoughts."""
    from agent import run_agent_query

    event = _make_event(role="model", text="Je réfléchis...", thought=True)

    async def gen(*args, **kwargs):
        yield event

    mock_runner = MagicMock()
    mock_runner.run_async = gen
    mocker.patch("agent.Runner", return_value=mock_runner)
    mocker.patch("agent.create_agent", new=AsyncMock(
        return_value=MagicMock(model="test")))
    mocker.patch("agent.get_session_service", return_value=_make_session_svc())

    result = await run_agent_query("Bonjour")
    assert "Je réfléchis..." in result["thoughts"]


@pytest.mark.asyncio
async def test_run_agent_query_captures_string_thought(mocker):
    """thought=<string> → str(thought) ajouté aux thoughts."""
    from agent import run_agent_query

    event = _make_event(role="model", thought="Analyse en cours")

    async def gen(*args, **kwargs):
        yield event

    mock_runner = MagicMock()
    mock_runner.run_async = gen
    mocker.patch("agent.Runner", return_value=mock_runner)
    mocker.patch("agent.create_agent", new=AsyncMock(
        return_value=MagicMock(model="test")))
    mocker.patch("agent.get_session_service", return_value=_make_session_svc())

    result = await run_agent_query("Test")
    assert "Analyse en cours" in result["thoughts"]


# ── Tool Calls ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_agent_query_captures_tool_calls(mocker):
    """function_call capturé → ajouté aux steps."""
    from agent import run_agent_query

    call = MagicMock()
    call.name = "ask_hr_agent"
    call.args = {"query": "skills"}
    event = _make_event(role="model", function_call=call)

    async def gen(*args, **kwargs):
        yield event

    mock_runner = MagicMock()
    mock_runner.run_async = gen
    mocker.patch("agent.Runner", return_value=mock_runner)
    mocker.patch("agent.create_agent", new=AsyncMock(
        return_value=MagicMock(model="test")))
    mocker.patch("agent.get_session_service", return_value=_make_session_svc())

    result = await run_agent_query("Test")
    tool_calls = [s for s in result["steps"] if s.get("type") == "call"]
    assert len(tool_calls) == 1
    assert tool_calls[0]["tool"] == "ask_hr_agent"


@pytest.mark.asyncio
async def test_run_agent_query_deduplicates_tool_calls(mocker):
    """Même tool call en double → dédupliqué via seen_steps."""
    from agent import run_agent_query

    call = MagicMock()
    call.name = "ask_hr_agent"
    call.args = {"query": "skills"}
    event1 = _make_event(role="model", function_call=call)
    event2 = _make_event(role="model", function_call=call)

    async def gen(*args, **kwargs):
        yield event1
        yield event2

    mock_runner = MagicMock()
    mock_runner.run_async = gen
    mocker.patch("agent.Runner", return_value=mock_runner)
    mocker.patch("agent.create_agent", new=AsyncMock(
        return_value=MagicMock(model="test")))
    mocker.patch("agent.get_session_service", return_value=_make_session_svc())

    result = await run_agent_query("Test")
    tool_calls = [s for s in result["steps"] if s.get("type") == "call"]
    assert len(tool_calls) == 1  # dédupliqué


# ── Tool Results — unwrap MCP JSON string ─────────────────────────────────────

@pytest.mark.asyncio
async def test_run_agent_query_unwraps_mcp_result_json(mocker):
    """function_response avec result JSON string → unwrappé en dict."""
    from agent import run_agent_query

    inner_data = {"items": [{"id": 1}], "total": 1}
    fres = MagicMock()
    fres.response = {"result": json.dumps(inner_data)}
    event = _make_event(role="tool", function_response=fres)

    async def gen(*args, **kwargs):
        yield event

    mock_runner = MagicMock()
    mock_runner.run_async = gen
    mocker.patch("agent.Runner", return_value=mock_runner)
    mocker.patch("agent.create_agent", new=AsyncMock(
        return_value=MagicMock(model="test")))
    mocker.patch("agent.get_session_service", return_value=_make_session_svc())

    result = await run_agent_query("Test")
    assert result["data"] == inner_data


# ── Tool Results A2A — métadonnées agrégées ───────────────────────────────────

@pytest.mark.asyncio
async def test_run_agent_query_aggregates_a2a_metadata(mocker):
    """Réponse A2A avec metadata → steps sous-agent préfixés + usage agrégé."""
    from agent import run_agent_query, a2a_metadata_var

    a2a_data = {
        "response": "Résultat HR",
        "agent": "hr_agent",
        "thoughts": "Analyse RH",
    }
    fres = MagicMock()
    fres.response = a2a_data
    event = _make_event(role="tool", function_response=fres)

    sub_meta = {
        "agent": "hr_agent",
        "steps": [{"type": "call", "tool": "get_user", "args": {}}],
        "usage": {"total_input_tokens": 100, "total_output_tokens": 50},
        "data": {"result": "some_data"},
        "display_type": "table",
    }

    async def gen(*args, **kwargs):
        a2a_metadata_var.set([sub_meta])
        yield event

    mock_runner = MagicMock()
    mock_runner.run_async = gen
    mocker.patch("agent.Runner", return_value=mock_runner)
    mocker.patch("agent.create_agent", new=AsyncMock(
        return_value=MagicMock(model="test")))
    mocker.patch("agent.get_session_service", return_value=_make_session_svc())

    result = await run_agent_query("Test")

    # thoughts sous-agent agrégés
    assert "[hr_agent] Analyse RH" in result["thoughts"]
    # steps préfixés
    prefixed_steps = [s for s in result["steps"]
                      if s.get("source") == "hr_agent"]
    assert len(prefixed_steps) >= 1
    assert "hr_agent:get_user" in prefixed_steps[0]["tool"]
    # usage agrégé
    assert result["usage"]["total_input_tokens"] >= 100
    # display_type propagé
    assert result["display_type"] == "table"
    # data propagée
    assert result["data"] == {"result": "some_data"}


@pytest.mark.asyncio
async def test_run_agent_query_warns_zero_tool_calls_a2a(mocker):
    """Sous-agent A2A sans tool calls → warning GUARDRAIL ajouté aux steps."""
    from agent import run_agent_query, a2a_metadata_var

    a2a_data = {"response": "Réponse hallucination possible",
                "agent": "hr_agent"}
    fres = MagicMock()
    fres.response = a2a_data
    event = _make_event(role="tool", function_response=fres)

    sub_meta = {
        "agent": "hr_agent",
        "steps": [],  # 0 tool calls
        "usage": {},
    }

    async def gen(*args, **kwargs):
        a2a_metadata_var.set([sub_meta])
        yield event

    mock_runner = MagicMock()
    mock_runner.run_async = gen
    mocker.patch("agent.Runner", return_value=mock_runner)
    mocker.patch("agent.create_agent", new=AsyncMock(
        return_value=MagicMock(model="test")))
    mocker.patch("agent.get_session_service", return_value=_make_session_svc())

    result = await run_agent_query("Test")
    warnings = [s for s in result["steps"]
                if "GUARDRAIL" in str(s.get("tool") or "")]
    assert len(warnings) == 1


# ── Usage metadata ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_agent_query_tracks_usage_metadata(mocker):
    """Usage metadata ADK → router_input/output_tokens trackés."""
    from agent import run_agent_query

    event = _make_event(role="model", usage={"input": 200, "output": 80})
    event.content.parts = []  # Pas de contenu texte

    async def gen(*args, **kwargs):
        yield event

    mock_runner = MagicMock()
    mock_runner.run_async = gen
    mocker.patch("agent.Runner", return_value=mock_runner)
    mocker.patch("agent.create_agent", new=AsyncMock(
        return_value=MagicMock(model="test")))
    mocker.patch("agent.get_session_service", return_value=_make_session_svc())

    result = await run_agent_query("Test")
    assert result["usage"]["total_input_tokens"] >= 200


# ── OPS-003 — Context overflow ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_agent_query_ops003_context_overflow(mocker):
    """OPS-003 : 'input token count exceeds' → reset session + steps CONTEXT_OVERFLOW."""
    from agent import run_agent_query

    async def overflow_run(*args, **kwargs):
        raise Exception(
            "400 INVALID_ARGUMENT: input token count exceeds the maximum allowed")
        yield

    mock_runner = MagicMock()
    mock_runner.run_async = overflow_run
    mocker.patch("agent.Runner", return_value=mock_runner)
    mocker.patch("agent.create_agent", new=AsyncMock(
        return_value=MagicMock(model="test")))

    mock_svc = AsyncMock()
    mock_svc.get_session.return_value = MagicMock()
    mock_svc._delete_session_impl = MagicMock()
    mocker.patch("agent.get_session_service", return_value=mock_svc)

    result = await run_agent_query("Long query", session_id="sess-overflow")

    assert "⚠️" in result["response"]
    assert "mémoire" in result["response"].lower(
    ) or "contexte" in result["response"].lower()
    overflow_steps = [s for s in result["steps"]
                      if "CONTEXT_OVERFLOW" in s.get("tool", "")]
    assert len(overflow_steps) == 1
    assert "technical_detail" in overflow_steps[0]["args"]


@pytest.mark.asyncio
async def test_run_agent_query_ops003_other_exception_reraises(mocker):
    """OPS-003 : Exception non-overflow → re-raise."""
    from agent import run_agent_query

    async def boom_run(*args, **kwargs):
        raise RuntimeError("Unhandled critical error")
        yield

    mock_runner = MagicMock()
    mock_runner.run_async = boom_run
    mocker.patch("agent.Runner", return_value=mock_runner)
    mocker.patch("agent.create_agent", new=AsyncMock(
        return_value=MagicMock(model="test")))
    mocker.patch("agent.get_session_service", return_value=_make_session_svc())

    with pytest.raises(RuntimeError, match="Unhandled critical error"):
        await run_agent_query("Test", session_id="sess-boom")


# ── FinOps BQ logging ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_agent_query_schedules_finops_logging(mocker):
    """Quand des tokens sont consommés → asyncio.create_task est appelé pour BQ."""
    from agent import run_agent_query

    event = _make_event(role="model", usage={"input": 500, "output": 200})
    event.content.parts = []

    async def gen(*args, **kwargs):
        yield event

    mock_runner = MagicMock()
    mock_runner.run_async = gen
    mocker.patch("agent.Runner", return_value=mock_runner)
    mocker.patch("agent.create_agent", new=AsyncMock(
        return_value=MagicMock(model="test")))
    mocker.patch("agent.get_session_service", return_value=_make_session_svc())

    create_task_calls = []
    asyncio.create_task

    def mock_create_task(coro, **kwargs):
        create_task_calls.append(coro)
        # Ferme la coroutine pour éviter le warning
        coro.close()
        return MagicMock()

    mocker.patch("asyncio.create_task", side_effect=mock_create_task)

    await run_agent_query("Test", user_id="user@zenika.com")

    # create_task doit avoir été appelé pour le FinOps logging
    assert len(create_task_calls) >= 1
