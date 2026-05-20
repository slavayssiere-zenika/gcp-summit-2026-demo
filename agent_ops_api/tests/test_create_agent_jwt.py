"""
test_create_agent_jwt.py — Régression Zero-Trust sur create_agent().

Vérifie que create_agent() propage bien le JWT (auth_header_var) lors de
l'appel à prompts_api pour charger le system_instruction.

Cas de test :
  1. JWT présent → header Authorization transmis à prompts_api ✅ (200 → instruction chargée)
  2. JWT présent → prompts_api répond 401 → fallback instruction utilisée
  3. JWT absent (None) → appel sans header Authorization, fallback activé sans crash
  4. prompts_api indisponible (exception réseau) → fallback sans plantage
"""
import os
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ.setdefault("SECRET_KEY", "testsecret_must_be_32_characters_long_for_sha256")
os.environ.setdefault("GEMINI_OPS_MODEL", "gemini-stub")
os.environ.setdefault("PROMPTS_API_URL", "http://prompts_api_test:8000")


@pytest.fixture(autouse=True)
def _reset_tools_cache():
    """Vide le cache MCP entre chaque test pour éviter les effets de bord."""
    import agent as ag
    ag._OPS_TOOLS_CACHE.clear()
    yield
    ag._OPS_TOOLS_CACHE.clear()


@pytest.fixture(autouse=True)
def _mock_prompt_cache(mocker):
    """Désactive le cache Redis pour que chaque test appelle prompts_api."""
    mocker.patch("shared.cache.get_cache", new=AsyncMock(return_value=None))
    mocker.patch("shared.cache.set_cache", new=AsyncMock(return_value=None))


def _make_http_response(status: int, body: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = body
    return resp


def _make_mock_async_client(mock_get_coro):
    """Construit un mock de httpx.AsyncClient utilisable comme context manager async."""
    mock_client = AsyncMock()
    mock_client.get = mock_get_coro
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx, mock_client


@pytest.mark.asyncio
async def test_create_agent_propagates_jwt_to_prompts_api(mocker):
    """Le JWT présent dans auth_header_var est bien envoyé à prompts_api."""
    import agent as ag
    token = "Bearer test.jwt.token"
    ag.auth_header_var.set(token)

    mock_get = AsyncMock(return_value=_make_http_response(200, {"value": "Instruction depuis prompts_api"}))
    ctx, _ = _make_mock_async_client(mock_get)

    mocker.patch("agent.get_cached_tools", new=AsyncMock(return_value=[MagicMock()]))
    # Patcher via le module agent (là où httpx est importé)
    mocker.patch("agent_commons.prompt_loader.httpx.AsyncClient", return_value=ctx)

    result_agent = await ag.create_agent()

    # Vérifier que l'appel httpx a bien reçu le header Authorization
    assert mock_get.called, "prompts_api n'a pas été appelé"
    call_kwargs = mock_get.call_args.kwargs
    headers_sent = call_kwargs.get("headers", {})
    assert "Authorization" in headers_sent, "Le header Authorization est absent de l'appel prompts_api"
    assert headers_sent["Authorization"] == token

    # Vérifier que l'instruction est chargée correctement
    assert "Instruction depuis prompts_api" in result_agent.instruction


@pytest.mark.asyncio
async def test_create_agent_fallback_on_prompts_api_401(mocker):
    """Si prompts_api retourne 401, create_agent utilise l'instruction de fallback."""
    import agent as ag
    ag.auth_header_var.set("Bearer valid.but.prompts.says.no")

    mock_get = AsyncMock(return_value=_make_http_response(401, {"detail": "Unauthorized"}))
    ctx, _ = _make_mock_async_client(mock_get)

    mocker.patch("agent.get_cached_tools", new=AsyncMock(return_value=[MagicMock()]))
    mocker.patch("agent_commons.prompt_loader.httpx.AsyncClient", return_value=ctx)

    result_agent = await ag.create_agent()

    # Fallback : instruction contient [Fallback Instruction]
    assert "Tu es l'Agent Ops" in result_agent.instruction


@pytest.mark.asyncio
async def test_create_agent_no_jwt_no_auth_header(mocker):
    """Sans JWT dans auth_header_var, l'appel se fait sans Authorization → pas de crash."""
    import agent as ag
    ag.auth_header_var.set(None)  # type: ignore[arg-type]

    mock_get = AsyncMock(return_value=_make_http_response(401, {}))
    ctx, _ = _make_mock_async_client(mock_get)

    mocker.patch("agent.get_cached_tools", new=AsyncMock(return_value=[MagicMock()]))
    mocker.patch("agent_commons.prompt_loader.httpx.AsyncClient", return_value=ctx)

    result_agent = await ag.create_agent()

    # Sans JWT, Authorization ne doit pas être dans les headers
    call_kwargs = mock_get.call_args.kwargs
    headers_sent = call_kwargs.get("headers", {})
    assert not headers_sent.get("Authorization"), "Authorization ne doit pas être envoyé sans JWT"

    # Doit quand même retourner un agent avec fallback
    assert result_agent is not None
    assert "Tu es l'Agent Ops" in result_agent.instruction


@pytest.mark.asyncio
async def test_create_agent_fallback_on_network_error(mocker):
    """Exception réseau sur prompts_api → create_agent ne plante pas et utilise le fallback."""
    import agent as ag
    ag.auth_header_var.set("Bearer some.token")

    mock_get = AsyncMock(side_effect=Exception("Connection refused"))
    ctx, _ = _make_mock_async_client(mock_get)

    mocker.patch("agent.get_cached_tools", new=AsyncMock(return_value=[MagicMock()]))
    mocker.patch("agent_commons.prompt_loader.httpx.AsyncClient", return_value=ctx)

    # Ne doit pas lever d'exception
    result_agent = await ag.create_agent()
    assert result_agent is not None
    # En cas d'exception, l'instruction de base (sans Fallback) est utilisée
    assert result_agent.instruction
    assert "Zenika" in result_agent.instruction
