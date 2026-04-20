"""
conftest.py — tests/
Configuration minimale pour les tests autonomes (test_semantic_cache, test_a2a_resilience, test_jwt_propagation).
Ces tests ne dépendent pas de main.py et tournent hors Docker.
"""
import os
import sys
import pytest
import fakeredis
from unittest.mock import patch

# Ajouter le répertoire parent (agent_router_api/) au path pour accéder aux modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Variables d'environnement minimales pour les tests
os.environ["GOOGLE_API_KEY"] = os.environ.get("GOOGLE_API_KEY", "test-key")
os.environ["GEMINI_MODEL"] = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
os.environ["SECRET_KEY"] = "testsecret"  # Clé fixe — aligne make_jwt() avec verify_jwt() dans main.py
os.environ["REDIS_URL"] = os.environ.get("REDIS_URL", "redis://redis:6379/1")
os.environ["SEMANTIC_CACHE_ENABLED"] = "true"
os.environ["SEMANTIC_CACHE_THRESHOLD"] = "0.95"
os.environ["SEMANTIC_CACHE_TTL"] = "900"
os.environ["GEMINI_EMBEDDING_MODEL"] = os.environ.get("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")

# ---------------------------------------------------------------------------
# Patch Redis au niveau session — avant TOUT import de main.py ou semantic_cache.py.
# SemanticCache instancie `redis.from_url(...)` au niveau module dans main.py (ligne 44).
# Sans ce patch, le TestClient échoue avec une connexion Redis refusée,
# ce qui corrompt l'état de l'app et provoque un 401 sur /query.
# ---------------------------------------------------------------------------
_fake_redis_server = fakeredis.FakeServer()
_fake_redis_client = fakeredis.FakeRedis(server=_fake_redis_server, decode_responses=True)

# Appliqué en scope="session" : le patch est actif pour tous les tests du module.
# pytest garantit que les fixtures session sont créées avant toute collecte de tests.
@pytest.fixture(scope="session", autouse=True)
def mock_redis_for_semantic_cache():
    """
    Remplace redis.from_url par un client FakeRedis in-memory pour toute la session.
    Nécessaire car SemanticCache est instancié au niveau module dans main.py,
    donc il est créé dès le premier import de main — avant qu'un fixture function puisse agir.
    """
    with patch("redis.from_url", return_value=_fake_redis_client):
        yield _fake_redis_client
    _fake_redis_client.flushall()
