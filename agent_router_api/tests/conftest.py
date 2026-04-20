"""
conftest.py — tests/
Configuration minimale pour les tests autonomes (test_semantic_cache, test_a2a_resilience, test_jwt_propagation).
Ces tests ne dépendent pas de main.py et tournent hors Docker.
"""
import os
import sys

# Ajouter le répertoire parent (agent_router_api/) au path pour accéder aux modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Variables d'environnement minimales pour les tests
os.environ.setdefault("GOOGLE_API_KEY", "test-key")
os.environ.setdefault("GEMINI_MODEL", "gemini-2.0-flash")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-tests-only")
os.environ.setdefault("REDIS_URL", "redis://redis:6379/1")
os.environ.setdefault("SEMANTIC_CACHE_ENABLED", "true")
os.environ.setdefault("SEMANTIC_CACHE_THRESHOLD", "0.95")
os.environ.setdefault("SEMANTIC_CACHE_TTL", "900")
os.environ.setdefault("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
