"""Tests unitaires pour la null-safety de event.content.parts dans runner.py.

Cas couverts :
- event.content.parts = None  → ne doit pas lever TypeError 'NoneType' object is not iterable
- event.content.parts = []    → event vide géré sans erreur
- Mix d'événements None/vides avec des events valides → seuls les valides contribuent
"""

from unittest.mock import MagicMock

import pytest

from agent_commons.runner import run_agent_and_collect


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_none_parts_event(role: str = "model") -> MagicMock:
    """Simule un event intermédiaire du SDK Gemini où parts vaut explicitement None.

    C'est exactement ce que Gemini renvoie lors des étapes de réflexion (Thinking)
    ou de certains événements de streaming intermédiaires — et qui causait le bug
    TypeError: 'NoneType' object is not iterable.
    """
    event = MagicMock()
    event.content = MagicMock()
    event.content.role = role
    event.content.parts = None  # <-- le cas problématique
    event.actions = None
    event.response = None
    event.usage_metadata = None
    return event


def _make_empty_parts_event(role: str = "model") -> MagicMock:
    """Simule un event avec une liste parts vide."""
    event = MagicMock()
    event.content = MagicMock()
    event.content.role = role
    event.content.parts = []
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
# Tests null-safety sur event.content.parts
# ---------------------------------------------------------------------------

class TestNullSafetyParts:

    @pytest.mark.asyncio
    async def test_none_parts_does_not_raise(self):
        """Un event avec parts=None ne doit PAS lever TypeError.

        Régression : 'NoneType' object is not iterable — observé en prod lors
        d'appels A2A (question 'qui est compétent à Zenika pour l'architecture cloud ?').
        """
        events = [_make_none_parts_event()]
        mock_runner = _make_async_runner(events)

        try:
            result = await run_agent_and_collect(
                mock_runner, "user1", "sess1", "query", "test_agent", "[TEST]"
            )
        except TypeError as e:
            pytest.fail(
                f"run_agent_and_collect a levé TypeError sur parts=None : {e}\n"
                "Corrigez en remplaçant 'list(event.content.parts)' par "
                "'list(parts) if parts is not None else []'."
            )

        assert result is not None
        assert len(result) == 7

    @pytest.mark.asyncio
    async def test_none_parts_returns_empty_response(self):
        """Un event avec parts=None produit une réponse vide (aucune donnée extraite)."""
        events = [_make_none_parts_event()]
        mock_runner = _make_async_runner(events)

        response_text, steps, thoughts, it, ot, last_data, display = await run_agent_and_collect(
            mock_runner, "user1", "sess1", "query", "test_agent", "[TEST]"
        )

        assert response_text == ""
        assert steps == []
        assert thoughts == []
        assert last_data is None

    @pytest.mark.asyncio
    async def test_empty_parts_does_not_raise(self):
        """Un event avec parts=[] (liste vide) ne doit pas non plus lever d'erreur."""
        events = [_make_empty_parts_event()]
        mock_runner = _make_async_runner(events)

        result = await run_agent_and_collect(
            mock_runner, "user1", "sess1", "query", "test_agent", "[TEST]"
        )

        assert result is not None

    @pytest.mark.asyncio
    async def test_mixed_none_and_valid_events(self):
        """Mélange d'événements None/vides avec des events valides.

        Les événements None doivent être silencieusement ignorés.
        Le texte de réponse doit être extrait uniquement des events valides.
        """
        events = [
            _make_none_parts_event(),
            _make_empty_parts_event(),
            _make_text_event("Réponse valide"),
            _make_none_parts_event(role="tool"),
        ]
        mock_runner = _make_async_runner(events)

        response_text, *_ = await run_agent_and_collect(
            mock_runner, "user1", "sess1", "query", "test_agent", "[TEST]"
        )

        assert response_text == "Réponse valide"

    @pytest.mark.asyncio
    async def test_multiple_none_parts_events_accumulation(self):
        """Plusieurs événements consécutifs avec parts=None ne provoquent pas d'erreur
        et n'accumulent pas de données parasites dans steps ou thoughts."""
        events = [_make_none_parts_event() for _ in range(10)]
        events.append(_make_text_event("Résultat final"))
        mock_runner = _make_async_runner(events)

        response_text, steps, thoughts, *_ = await run_agent_and_collect(
            mock_runner, "user1", "sess1", "query", "test_agent", "[TEST]"
        )

        assert response_text == "Résultat final"
        assert steps == []
        assert thoughts == []
