"""conftest.py — Configuration pytest racine pour cv_api.

Note architecturale : cv_api utilise des types PostgreSQL-only (Vector(3072), JSONB, ARRAY)
qui sont incompatibles avec SQLite. Le conftest racine utilise donc un mock AsyncSession
à spec strict pour les tests unitaires. Les tests d'intégration (tests/integration/) utilisent
Testcontainers pgvector pour la couverture des types PostgreSQL.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

# Assure que la racine du monorepo est dans sys.path pour résoudre `shared/`
_MONOREPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _MONOREPO_ROOT not in sys.path:
    sys.path.insert(0, _MONOREPO_ROOT)

# CRITICAL: Variables d'environnement AVANT tout import qui les utilise au niveau module
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./cv_test.db"
os.environ["SECRET_KEY"] = "testsecret"
os.environ["REDIS_URL"] = "redis://localhost:6379/7"
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test-project")

# Mock OTel et Redis AVANT l'import de main (initialisés au niveau module)
_mock_redis = AsyncMock()
_mock_redis.get.return_value = None
_mock_redis.set.return_value = True
_mock_redis.delete.return_value = 1

with patch("opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter",
           return_value=MagicMock()):
    with patch("redis.asyncio.from_url", return_value=_mock_redis):
        from main import app  # noqa: E402
        from shared.database import get_db  # noqa: E402
        from shared.auth.jwt import verify_jwt  # noqa: E402


# ── Overrides globaux ──────────────────────────────────────────────────────────

def override_verify_jwt():
    return {"sub": "test", "email": "test@zenika.com", "role": "admin"}


async def override_get_db():
    """Mock AsyncSession à spec strict pour les tests unitaires.

    Utilise spec=AsyncSession pour garantir que :
    - Les méthodes retournent des coroutines (pas des MagicMock)
    - Les appels db.execute(), db.commit(), db.rollback() sont correctement awaitable
    - Les AttributeError sont levées si une méthode inexistante est appelée

    Limitation : les tests SQL réels (SELECT, INSERT...) nécessitent Testcontainers
    (voir tests/integration/conftest.py).
    """
    db = AsyncMock(spec=AsyncSession)
    # Configurer les retours par défaut pour les patterns courants
    execute_result = AsyncMock()
    execute_result.scalars.return_value.all.return_value = []
    execute_result.scalars.return_value.first.return_value = None
    execute_result.scalar_one_or_none.return_value = None
    execute_result.scalar_one.return_value = 0
    db.execute.return_value = execute_result
    yield db


app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[verify_jwt] = override_verify_jwt


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def wipe_redis_state():
    """Réinitialise l'état du mock Redis entre chaque test pour garantir l'isolation."""
    _mock_redis.reset_mock()
    _mock_redis.get.return_value = None
    _mock_redis.set.return_value = True
    _mock_redis.delete.return_value = 1
    yield


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c
