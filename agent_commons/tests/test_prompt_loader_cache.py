"""Tests unitaires pour get_or_create_gemini_context_cache dans prompt_loader.py."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from agent_commons.prompt_loader import get_or_create_gemini_context_cache


@pytest.fixture
def mock_cache():
    """Mock les fonctions get_cache et set_cache de shared.cache."""
    with patch("shared.cache.get_cache", new_callable=AsyncMock) as mock_get, \
         patch("shared.cache.set_cache", new_callable=AsyncMock) as mock_set:
        yield mock_get, mock_set


@pytest.fixture
def mock_genai_client():
    """Mock le client Gemini Client du SDK google.genai."""
    with patch("google.genai.Client") as mock_client_class:
        mock_instance = MagicMock()
        mock_client_class.return_value = mock_instance
        yield mock_instance


@pytest.mark.asyncio
async def test_cache_hit_in_redis_and_gemini(mock_cache, mock_genai_client):
    """Vérifie le cas idéal (HIT) : présent dans Redis et validé dans Gemini."""
    mock_get, mock_set = mock_cache
    mock_get.return_value = "cachedContents/test_cache_id_123"

    # Mock Gemini get success
    mock_genai_client.caches.get.return_value = MagicMock()

    result = await get_or_create_gemini_context_cache(
        prompt_key="agent_hr_api.system_instruction",
        prompt_text="A" * 200,  # Suffisamment long
        model="gemini-2.5-flash",
    )

    assert result == "cachedContents/test_cache_id_123"
    mock_get.assert_called_once_with("gemini:cache:agent_hr_api.system_instruction:gemini-2.5-flash")
    mock_genai_client.caches.get.assert_called_once_with(name="cachedContents/test_cache_id_123")
    mock_genai_client.caches.create.assert_not_called()
    mock_set.assert_not_called()


@pytest.mark.asyncio
async def test_cache_expired_in_gemini_recreated(mock_cache, mock_genai_client):
    """Vérifie que si le cache a expiré dans Gemini, il est recréé et mis à jour."""
    mock_get, mock_set = mock_cache
    mock_get.return_value = "cachedContents/expired_cache_id"

    # Mock Gemini get lève une exception (cache introuvable / expiré)
    mock_genai_client.caches.get.side_effect = Exception("Cache not found")

    # Mock Gemini create success
    mock_created = MagicMock()
    mock_created.name = "cachedContents/new_cache_id"
    mock_genai_client.caches.create.return_value = mock_created

    result = await get_or_create_gemini_context_cache(
        prompt_key="agent_hr_api.system_instruction",
        prompt_text="A" * 200,
        model="gemini-2.5-flash",
    )

    assert result == "cachedContents/new_cache_id"
    mock_genai_client.caches.get.assert_called_once_with(name="cachedContents/expired_cache_id")
    mock_genai_client.caches.create.assert_called_once()
    mock_set.assert_called_once_with(
        "gemini:cache:agent_hr_api.system_instruction:gemini-2.5-flash",
        "cachedContents/new_cache_id",
        500
    )


@pytest.mark.asyncio
async def test_cache_creation_fallback_on_gemini_error(mock_cache, mock_genai_client):
    """Vérifie que si Gemini renvoie une erreur lors de la création, on fallback sur None."""
    mock_get, mock_set = mock_cache
    mock_get.return_value = None

    # Mock Gemini create lève une exception (ex: quota ou modèle incompatible)
    mock_genai_client.caches.create.side_effect = Exception("Model not supported")

    result = await get_or_create_gemini_context_cache(
        prompt_key="agent_hr_api.system_instruction",
        prompt_text="A" * 200,
        model="gemini-legacy-model",
    )

    assert result is None
    mock_genai_client.caches.create.assert_called_once()
    mock_set.assert_not_called()


@pytest.mark.asyncio
async def test_cache_prompt_too_short(mock_cache, mock_genai_client):
    """Vérifie que si le prompt est trop court, le cache n'est pas utilisé ni créé."""
    mock_get, mock_set = mock_cache

    result = await get_or_create_gemini_context_cache(
        prompt_key="agent_hr_api.system_instruction",
        prompt_text="Short prompt",
        model="gemini-2.5-flash",
    )

    assert result is None
    mock_get.assert_not_called()
    mock_genai_client.caches.create.assert_not_called()
