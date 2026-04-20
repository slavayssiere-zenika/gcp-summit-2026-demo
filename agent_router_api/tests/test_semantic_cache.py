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
    """Vecteur unitaire de dimension 5 pour les tests."""
    return [1.0, 0.0, 0.0, 0.0, 0.0]


@pytest.fixture
def similar_embedding():
    """Vecteur très proche (cosine ~0.9999)."""
    return [0.9998, 0.019, 0.0, 0.0, 0.0]


@pytest.fixture
def dissimilar_embedding():
    """Vecteur orthogonal (cosine = 0)."""
    return [0.0, 1.0, 0.0, 0.0, 0.0]


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
    """MISS : aucune entrée similaire → retourne None pour que l'appel LLM se fasse."""
    cache = make_cache()

    stored_entry = {
        "embedding": json.dumps(dissimilar_embedding),
        "query": "Mission Paris ?",
        "response": json.dumps({"response": "Cached"}),
        "created_at": "1714000000",
    }
    cache._redis.scan_iter.return_value = ["semcache:aaa"]
    cache._redis.hgetall.return_value = stored_entry

    with patch.object(cache, "_compute_embedding", new=AsyncMock(return_value=fake_embedding)):
        result = await cache.get("Quelles sont les missions disponibles ?")

    assert result is None


@pytest.mark.asyncio
async def test_cache_hit_bypasses_llm(fake_embedding, similar_embedding, sample_response):
    """HIT : requête similaire (>= 0.95) → retourne la réponse cachée avec semantic_cache_hit=True."""
    cache = make_cache()

    stored_entry = {
        "embedding": json.dumps(similar_embedding),
        "query": "Montre-moi les missions disponibles.",
        "response": json.dumps(sample_response),
        "created_at": "1714000000",
    }
    cache._redis.scan_iter.return_value = ["semcache:bbb"]
    cache._redis.hgetall.return_value = stored_entry

    # Direct monkey-patch de la méthode async sur l'instance
    async def _fake_embed(text):
        return fake_embedding
    cache._compute_embedding = _fake_embed

    result = await cache.get("Quelles sont les missions disponibles ?")

    assert result is not None
    assert result["semantic_cache_hit"] is True
    assert result["source"] == "semantic_cache"

    # Le step de cache doit être injecté en premier
    assert len(result["steps"]) >= 1
    assert result["steps"][0]["tool"] == "semantic_cache:HIT"
    assert "similarity_score" in result["steps"][0]["args"]


@pytest.mark.asyncio
@pytest.mark.parametrize("realtime_query", [
    "Ahmed est disponible aujourd'hui ?",
    "Qui est disponible maintenant pour une réunion ?",
    "Quelles sont les disponibilités actuellement",
    "Quel consultant a de la disponibilité en ce moment",
    "Est-ce qu'Ahmed est disponible cette semaine",
    "What's the status right now",
    "Today's available consultants",
    "Est-ce qu'Ahmed est disponible pour une mission ?",
])
async def test_realtime_query_bypasses_cache(realtime_query):
    """REALTIME : les requêtes temps-réel ne doivent JAMAIS toucher le cache."""
    cache = make_cache()
    mock_compute = AsyncMock()

    with patch.object(cache, "_compute_embedding", new=mock_compute):
        result = await cache.get(realtime_query)

    assert result is None
    mock_compute.assert_not_called()


def test_cosine_similarity_identical_vectors():
    """Deux vecteurs identiques → similarité = 1.0."""
    from semantic_cache import SemanticCache
    cache = make_cache()
    v = [1.0, 2.0, 3.0, 4.0]
    assert abs(cache._cosine_similarity(v, v) - 1.0) < 1e-6


def test_cosine_similarity_orthogonal_vectors():
    """Vecteurs orthogonaux → similarité = 0.0."""
    cache = make_cache()
    a = [1.0, 0.0, 0.0]
    b = [0.0, 1.0, 0.0]
    assert cache._cosine_similarity(a, b) == 0.0


def test_cosine_similarity_zero_vector():
    """Vecteur nul → similarité = 0.0 sans crash."""
    cache = make_cache()
    assert cache._cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


def test_cosine_similarity_different_lengths():
    """Vecteurs de tailles différentes → similarité = 0.0 sans crash."""
    cache = make_cache()
    assert cache._cosine_similarity([1.0, 2.0], [1.0]) == 0.0


@pytest.mark.asyncio
async def test_cache_disabled_via_env_var():
    """DISABLED : si SEMANTIC_CACHE_ENABLED=false, get() retourne toujours None."""
    cache = make_cache(env_overrides={"SEMANTIC_CACHE_ENABLED": "false"})
    mock_compute = AsyncMock()

    with patch.object(cache, "_compute_embedding", new=mock_compute):
        result = await cache.get("Quelles sont les missions disponibles ?")

    assert result is None
    mock_compute.assert_not_called()


@pytest.mark.asyncio
async def test_embedding_failure_falls_through():
    """RESILIENCE : si l'embedding API échoue → cache miss gracieux (None), pas d'exception."""
    cache = make_cache()

    with patch.object(cache, "_compute_embedding", new=AsyncMock(return_value=None)):
        result = await cache.get("Y a-t-il des missions ?")

    assert result is None


@pytest.mark.asyncio
async def test_set_stores_in_redis(fake_embedding, sample_response):
    """SET : après un miss LLM, la réponse est stockée dans Redis avec le bon TTL."""
    cache = make_cache()
    cache._redis.hset = MagicMock()
    cache._redis.expire = MagicMock()

    # Direct monkey-patch
    async def _fake_embed(text):
        return fake_embedding
    cache._compute_embedding = _fake_embed

    await cache.set("Liste des missions disponibles ?", sample_response)

    cache._redis.hset.assert_called_once()
    call_kwargs = cache._redis.hset.call_args

    # Vérifie que le nom de clé commence par semcache:
    stored_key = call_kwargs[0][0] if call_kwargs[0] else call_kwargs.kwargs.get("name", "")
    assert stored_key.startswith("semcache:")

    # Vérifie le TTL
    cache._redis.expire.assert_called_once()
    expire_args = cache._redis.expire.call_args[0]
    assert expire_args[1] == 900  # TTL par défaut


@pytest.mark.asyncio
async def test_set_skips_realtime_queries(sample_response):
    """SET : les requêtes temps-réel ne doivent pas être stockées en cache."""
    cache = make_cache()
    mock_compute = AsyncMock()

    with patch.object(cache, "_compute_embedding", new=mock_compute):
        await cache.set("Ahmed est-il disponible aujourd'hui ?", sample_response)

    mock_compute.assert_not_called()
    cache._redis.hset.assert_not_called()


@pytest.mark.asyncio
async def test_cache_hit_response_contains_cache_step(fake_embedding, similar_embedding, sample_response):
    """Le step 'semantic_cache:HIT' doit être PREMIER dans la liste des steps retournés."""
    cache = make_cache()

    stored_entry = {
        "embedding": json.dumps(similar_embedding),
        "query": "missions",
        "response": json.dumps(sample_response),
        "created_at": "1714000000",
    }
    cache._redis.scan_iter.return_value = ["semcache:ccc"]
    cache._redis.hgetall.return_value = stored_entry

    async def _fake_embed(text):
        return fake_embedding
    cache._compute_embedding = _fake_embed

    result = await cache.get("Liste des missions")

    assert result["steps"][0]["tool"] == "semantic_cache:HIT"
    # Les steps originaux doivent toujours être là
    original_step_tools = [s["tool"] for s in result["steps"][1:]]
    assert "list_missions" in original_step_tools
