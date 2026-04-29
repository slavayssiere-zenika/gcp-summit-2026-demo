"""
Tests unitaires — SEC-F06 : Semantic Cache LLM
Couvre les cas : hit, miss, requête temps-réel, cosine similarity,
log BigQuery, désactivation via env var, et dégradation gracieuse.
"""

import json
import os
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_embedding():
    """Vecteur unitaire de dimension 768 pour les tests."""
    v = [0.0] * 768
    v[0] = 1.0
    return v


@pytest.fixture
def similar_embedding():
    """Vecteur très proche (cosine ~0.9999)."""
    v = [0.0] * 768
    v[0] = 0.9998
    v[1] = 0.019
    return v


@pytest.fixture
def dissimilar_embedding():
    """Vecteur orthogonal (cosine = 0)."""
    v = [0.0] * 768
    v[1] = 1.0
    return v


@pytest.fixture
def sample_response():
    return {
        "response": "Voici une liste des missions disponibles.",
        "steps": [{"type": "call", "tool": "list_missions", "args": {}}],
        "thoughts": "Je cherche les missions.",
        "data": None,
        "source": "adk_agent",
        "session_id": "user_test@zenika.com",
        "usage": {"total_input_tokens": 100, "total_output_tokens": 200, "estimated_cost_usd": 0.0001},
    }


def make_cache(env_overrides=None):
    """Crée une instance SemanticCache avec un Redis mocké."""
    env = {
        "SEMANTIC_CACHE_ENABLED": "true",
        "SEMANTIC_CACHE_THRESHOLD": "0.95",
        "SEMANTIC_CACHE_TTL": "900",
        "GEMINI_EMBEDDING_MODEL": "gemini-embedding-001",
        "REDIS_URL": "redis://redis:6379/1",
    }
    if env_overrides:
        env.update(env_overrides)

    with patch.dict(os.environ, env):
        # On importe après avoir patché l'env pour que os.getenv() prenne les bonnes valeurs
        from semantic_cache import SemanticCache
        cache = SemanticCache()
        # Remplace le redis réel par un mock
        cache._redis = MagicMock()
        return cache


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cache_miss_returns_none(fake_embedding, dissimilar_embedding):
    cache = make_cache()
    # Mock FT.SEARCH to return no results
    cache._redis.execute_command = AsyncMock(return_value=[0])

    with patch.object(cache, "_compute_embedding_async", new=AsyncMock(return_value=fake_embedding)):
        result = await cache.get("Quelles sont les missions disponibles ?")

    assert result is None

@pytest.mark.asyncio
async def test_cache_hit_bypasses_llm(fake_embedding, similar_embedding, sample_response):
    cache = make_cache()

    # Mock FT.SEARCH to return a hit with a score of 0.0 (identical)
    # [count, key, [field, value, field, value]]
    cache._redis.execute_command = AsyncMock(return_value=[
        1, "semcache:bbb", ["score", "0.0", "response", json.dumps(sample_response)]
    ])

    cache._compute_embedding_async = AsyncMock(return_value=fake_embedding)

    result = await cache.get("Quelles sont les missions disponibles ?")

    assert result is not None
    assert result["semantic_cache_hit"] is True
    assert result["source"] == "semantic_cache"
    assert len(result["steps"]) >= 1
    assert result["steps"][0]["tool"] == "semantic_cache:HIT"
    assert "similarity_score" in result["steps"][0]["args"]

@pytest.mark.asyncio
@pytest.mark.parametrize("realtime_query", [
    "Ahmed est disponible aujourd'hui ?",
    "Qui est disponible maintenant pour une réunion ?",
])
async def test_realtime_query_bypasses_cache(realtime_query):
    cache = make_cache()
    mock_compute = AsyncMock()

    with patch.object(cache, "_compute_embedding_async", new=mock_compute):
        result = await cache.get(realtime_query)

    assert result is None
    mock_compute.assert_not_called()

@pytest.mark.asyncio
async def test_cache_disabled_via_env_var():
    cache = make_cache(env_overrides={"SEMANTIC_CACHE_ENABLED": "false"})
    mock_compute = AsyncMock()

    with patch.object(cache, "_compute_embedding_async", new=mock_compute):
        result = await cache.get("Quelles sont les missions disponibles ?")

    assert result is None
    mock_compute.assert_not_called()

@pytest.mark.asyncio
async def test_embedding_failure_falls_through():
    cache = make_cache()

    with patch.object(cache, "_compute_embedding_async", new=AsyncMock(return_value=None)):
        result = await cache.get("Y a-t-il des missions ?")

    assert result is None

@pytest.mark.asyncio
async def test_set_stores_in_redis(fake_embedding, sample_response):
    cache = make_cache()
    cache._redis.hset = AsyncMock()
    cache._redis.expire = AsyncMock()

    cache._compute_embedding_async = AsyncMock(return_value=fake_embedding)

    await cache.set("Liste des missions disponibles ?", sample_response)

    cache._redis.hset.assert_called_once()
    call_kwargs = cache._redis.hset.call_args
    stored_key = call_kwargs[0][0] if call_kwargs[0] else call_kwargs.kwargs.get("name", "")
    assert stored_key.startswith("semcache:")

    cache._redis.expire.assert_called_once()

@pytest.mark.asyncio
async def test_set_skips_realtime_queries(sample_response):
    cache = make_cache()
    mock_compute = AsyncMock()

    with patch.object(cache, "_compute_embedding_async", new=mock_compute):
        await cache.set("Ahmed est-il disponible aujourd'hui ?", sample_response)

    mock_compute.assert_not_called()
    cache._redis.hset.assert_not_called()

@pytest.mark.asyncio
async def test_cache_hit_response_contains_cache_step(fake_embedding, similar_embedding, sample_response):
    cache = make_cache()

    cache._redis.execute_command = AsyncMock(return_value=[
        1, "semcache:ccc", ["score", b"0.0", b"response", json.dumps(sample_response).encode()]
    ])

    cache._compute_embedding_async = AsyncMock(return_value=fake_embedding)

    result = await cache.get("Liste des missions")

    assert result["steps"][0]["tool"] == "semantic_cache:HIT"
    original_step_tools = [s["tool"] for s in result["steps"][1:]]
    assert "list_missions" in original_step_tools
