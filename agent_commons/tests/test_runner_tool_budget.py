"""Tests unitaires pour le budget compteur de tools (P2-2) dans runner.py.

Couvre :
- Aucun step TOOL_BUDGET si le nombre d'appels est sous le seuil.
- Injection d'un step TOOL_BUDGET exactement au seuil MAX_TOOL_CALLS_WARNING.
- TOOL_BUDGET injecté une seule fois même si les appels dépassent le seuil.
- Structure du step TOOL_BUDGET (type, tool, args avec message/count/threshold).
- Idempotence : les appels dupliqués (même sig) ne comptent pas.
- MAX_TOOL_CALLS_WARNING configurable via variable de module.
- run_agent_and_collect retourne la bonne signature de tuple.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

import agent_commons.runner as runner_module
from agent_commons.runner import MAX_TOOL_CALLS_WARNING, run_agent_and_collect


# ---------------------------------------------------------------------------
# Helpers pour simuler des événements ADK
# ---------------------------------------------------------------------------

def _make_tool_call_event(tool_name: str, args: dict = None) -> MagicMock:
    """Simule un événement ADK portant un tool_call."""
    args = args or {}
    event = MagicMock()
    event.content = MagicMock()
    event.content.role = "tool"
    # Simule une part avec function_call
    call = MagicMock()
    call.name = tool_name
    call.args = args
    part = MagicMock()
    part.thought = None
    part.tool_call = None
    part.function_call = call
    part.function_response = None
    part.text = None
    event.content.parts = [part]
    event.actions = None
    event.response = None
    event.usage_metadata = None
    return event


def _make_text_event(text: str) -> MagicMock:
    """Simule un événement ADK portant une réponse texte (rôle model)."""
    event = MagicMock()
    event.content = MagicMock()
    event.content.role = "model"
    part = MagicMock()
    part.thought = None
    part.tool_call = None
    part.function_call = None
    part.function_response = None
    part.text = text
    event.content.parts = [part]
    event.actions = None
    event.response = None
    event.usage_metadata = None
    return event


def _make_async_runner(events: list) -> MagicMock:
    """Crée un mock de Runner ADK dont run_async() yielde une liste d'événements."""
    async def _gen(*args, **kwargs):
        for ev in events:
            yield ev

    runner = MagicMock()
    runner.run_async = MagicMock(side_effect=_gen)
    return runner


# ---------------------------------------------------------------------------
# Tests sur le compteur TOOL_BUDGET
# ---------------------------------------------------------------------------

class TestToolBudgetCounter:
    @pytest.mark.asyncio
    async def test_no_budget_step_below_threshold(self):
        """Pas de TOOL_BUDGET si le nombre d'appels est < MAX_TOOL_CALLS_WARNING."""
        events = [_make_tool_call_event(f"tool_{i}") for i in range(MAX_TOOL_CALLS_WARNING - 1)]
        events.append(_make_text_event("OK"))
        mock_runner = _make_async_runner(events)

        _, steps, *_ = await run_agent_and_collect(
            mock_runner, "user1", "sess1", "query", "test_agent", "[TEST]"
        )

        budget_steps = [s for s in steps if s.get("tool") == "TOOL_BUDGET"]
        assert len(budget_steps) == 0, "TOOL_BUDGET ne doit pas s'injecter avant le seuil"

    @pytest.mark.asyncio
    async def test_budget_step_injected_exactly_at_threshold(self):
        """TOOL_BUDGET est injecté exactement au MAX_TOOL_CALLS_WARNING ème appel unique."""
        events = [_make_tool_call_event(f"tool_{i}") for i in range(MAX_TOOL_CALLS_WARNING)]
        events.append(_make_text_event("OK"))
        mock_runner = _make_async_runner(events)

        _, steps, *_ = await run_agent_and_collect(
            mock_runner, "user1", "sess1", "query", "test_agent", "[TEST]"
        )

        budget_steps = [s for s in steps if s.get("tool") == "TOOL_BUDGET"]
        assert len(budget_steps) == 1

    @pytest.mark.asyncio
    async def test_budget_step_injected_only_once_above_threshold(self):
        """TOOL_BUDGET est injecté une seule fois même si le seuil est largement dépassé."""
        n = MAX_TOOL_CALLS_WARNING + 5
        events = [_make_tool_call_event(f"tool_{i}") for i in range(n)]
        events.append(_make_text_event("OK"))
        mock_runner = _make_async_runner(events)

        _, steps, *_ = await run_agent_and_collect(
            mock_runner, "user1", "sess1", "query", "test_agent", "[TEST]"
        )

        budget_steps = [s for s in steps if s.get("tool") == "TOOL_BUDGET"]
        assert len(budget_steps) == 1, "TOOL_BUDGET doit être injecté exactement 1 fois"

    @pytest.mark.asyncio
    async def test_budget_step_has_correct_type(self):
        """Le step TOOL_BUDGET doit avoir type='warning'."""
        events = [_make_tool_call_event(f"tool_{i}") for i in range(MAX_TOOL_CALLS_WARNING)]
        events.append(_make_text_event("OK"))
        mock_runner = _make_async_runner(events)

        _, steps, *_ = await run_agent_and_collect(
            mock_runner, "user1", "sess1", "query", "test_agent", "[TEST]"
        )

        budget_step = next(s for s in steps if s.get("tool") == "TOOL_BUDGET")
        assert budget_step["type"] == "warning"

    @pytest.mark.asyncio
    async def test_budget_step_args_structure(self):
        """Le step TOOL_BUDGET contient message, tool_call_count, threshold dans args."""
        events = [_make_tool_call_event(f"tool_{i}") for i in range(MAX_TOOL_CALLS_WARNING)]
        events.append(_make_text_event("OK"))
        mock_runner = _make_async_runner(events)

        _, steps, *_ = await run_agent_and_collect(
            mock_runner, "user1", "sess1", "query", "test_agent", "[TEST]"
        )

        budget_step = next(s for s in steps if s.get("tool") == "TOOL_BUDGET")
        assert "args" in budget_step
        args = budget_step["args"]
        assert "message" in args and len(args["message"]) > 10
        assert args["tool_call_count"] == MAX_TOOL_CALLS_WARNING
        assert args["threshold"] == MAX_TOOL_CALLS_WARNING

    @pytest.mark.asyncio
    async def test_duplicate_tool_calls_not_counted_twice(self):
        """Les appels identiques (même tool + mêmes args) ne comptent qu'une seule fois."""
        # Only MAX_TOOL_CALLS_WARNING - 1 unique calls, but duplicated 3x
        unique_events = [_make_tool_call_event(f"tool_{i}") for i in range(MAX_TOOL_CALLS_WARNING - 1)]
        # Duplicate the first tool call (same name + args → same signature)
        duplicate_event = _make_tool_call_event("tool_0", {})
        events = unique_events + [duplicate_event, duplicate_event, _make_text_event("OK")]
        mock_runner = _make_async_runner(events)

        _, steps, *_ = await run_agent_and_collect(
            mock_runner, "user1", "sess1", "query", "test_agent", "[TEST]"
        )

        # Duplicates must NOT trigger TOOL_BUDGET (only MAX-1 unique calls)
        budget_steps = [s for s in steps if s.get("tool") == "TOOL_BUDGET"]
        assert len(budget_steps) == 0

    @pytest.mark.asyncio
    async def test_budget_step_positioned_after_triggering_call(self):
        """Le step TOOL_BUDGET est inséré juste après l'appel qui atteint le seuil."""
        events = [_make_tool_call_event(f"tool_{i}") for i in range(MAX_TOOL_CALLS_WARNING)]
        events.append(_make_text_event("OK"))
        mock_runner = _make_async_runner(events)

        _, steps, *_ = await run_agent_and_collect(
            mock_runner, "user1", "sess1", "query", "test_agent", "[TEST]"
        )

        call_indices = [i for i, s in enumerate(steps) if s.get("type") == "call"]
        budget_index = next(i for i, s in enumerate(steps) if s.get("tool") == "TOOL_BUDGET")

        # TOOL_BUDGET must appear after the last call step (inserted right after threshold)
        assert budget_index > call_indices[-1] or budget_index == call_indices[-1] + 1

    @pytest.mark.asyncio
    async def test_no_tools_no_budget_step(self):
        """Sans appel d'outil, aucun step TOOL_BUDGET ne doit être injecté."""
        events = [_make_text_event("Réponse directe sans outil.")]
        mock_runner = _make_async_runner(events)

        _, steps, *_ = await run_agent_and_collect(
            mock_runner, "user1", "sess1", "query", "test_agent", "[TEST]"
        )

        assert not any(s.get("tool") == "TOOL_BUDGET" for s in steps)


# ---------------------------------------------------------------------------
# Tests sur la signature de retour de run_agent_and_collect
# ---------------------------------------------------------------------------

class TestRunnerReturnSignature:
    @pytest.mark.asyncio
    async def test_returns_seven_tuple(self):
        """run_agent_and_collect doit retourner un tuple de 7 éléments."""
        events = [_make_text_event("OK")]
        mock_runner = _make_async_runner(events)

        result = await run_agent_and_collect(
            mock_runner, "user1", "sess1", "query", "test_agent", "[TEST]"
        )

        assert len(result) == 7

    @pytest.mark.asyncio
    async def test_response_text_aggregated(self):
        """Le texte de réponse est correctement agrégé depuis les events model."""
        events = [_make_text_event("Bonjour "), _make_text_event("monde")]
        mock_runner = _make_async_runner(events)

        response_text, *_ = await run_agent_and_collect(
            mock_runner, "user1", "sess1", "query", "test_agent", "[TEST]"
        )

        assert response_text == "Bonjour monde"

    @pytest.mark.asyncio
    async def test_empty_events_returns_empty_response(self):
        """Un runner sans événements retourne une réponse vide."""
        mock_runner = _make_async_runner([])

        response_text, steps, thoughts, it, ot, last_data, display = await run_agent_and_collect(
            mock_runner, "user1", "sess1", "query", "test_agent", "[TEST]"
        )

        assert response_text == ""
        assert steps == []
        assert thoughts == []
        assert it == 0
        assert ot == 0
        assert last_data is None
        assert display is None


# ---------------------------------------------------------------------------
# Tests sur MAX_TOOL_CALLS_WARNING configurable
# ---------------------------------------------------------------------------

class TestMaxToolCallsConfig:
    def test_default_threshold_is_twelve(self):
        """MAX_TOOL_CALLS_WARNING doit valoir 12 par défaut."""
        assert MAX_TOOL_CALLS_WARNING == 12

    @pytest.mark.asyncio
    async def test_custom_threshold_via_monkeypatch(self, monkeypatch):
        """Un seuil de 3 doit déclencher TOOL_BUDGET après 3 appels uniques."""
        monkeypatch.setattr(runner_module, "MAX_TOOL_CALLS_WARNING", 3)

        events = [_make_tool_call_event(f"tool_{i}") for i in range(3)]
        events.append(_make_text_event("OK"))
        mock_runner = _make_async_runner(events)

        _, steps, *_ = await run_agent_and_collect(
            mock_runner, "user1", "sess1", "query", "test_agent", "[TEST]"
        )

        budget_steps = [s for s in steps if s.get("tool") == "TOOL_BUDGET"]
        assert len(budget_steps) == 1
        assert budget_steps[0]["args"]["threshold"] == 3
