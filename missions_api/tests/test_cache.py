import pytest
from unittest.mock import AsyncMock
from src.missions.cache import get_cached_prompt, force_invalidate_prompt, redis_client

@pytest.mark.asyncio
async def test_get_cached_prompt_hit(mocker):
    mocker.patch("src.missions.cache.redis_client.get", new_callable=AsyncMock, return_value="HIT PROMPT")
    
    http_client = AsyncMock()
    val = await get_cached_prompt(http_client, "some_key", {})
    assert val == "HIT PROMPT"

@pytest.mark.asyncio
async def test_force_invalidate_prompt(mocker):
    mock_del = mocker.patch("src.missions.cache.redis_client.delete", new_callable=AsyncMock)
    await force_invalidate_prompt("some_key")
    mock_del.assert_called_once_with("mission_prompt_v1:some_key")
    
@pytest.mark.asyncio
async def test_get_cached_prompt_fallback_missing(mocker):
    mocker.patch("src.missions.cache.redis_client.get", new_callable=AsyncMock, return_value=None)
    mocker.patch("src.missions.cache.redis_client.setex", new_callable=AsyncMock)
    
    http_client = AsyncMock()
    http_client.get.side_effect = Exception("HTTP ERR")
    
    with pytest.raises(Exception):
        await get_cached_prompt(http_client, "missions_api.non_existent", {})

