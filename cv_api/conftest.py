# Scripts de debug manuels à la racine cv_api/ — exclus de la collecte pytest.
# deploy.sh invoque pytest avec "./cv_api" comme chemin explicite (bypass pytest.ini).
# test_client.py importe main → src.auth → os.environ.pop("SECRET_KEY") → 401 sur tous les tests suivants.
collect_ignore = ["test_client.py", "test_fastapi.py", "test_validation.py"]

from fastapi.testclient import TestClient  # noqa: E402
import pytest  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402
import os  # noqa: E402
import sys  # noqa: E402

# Assure que la racine du monorepo est dans sys.path pour résoudre `shared/`
_MONOREPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _MONOREPO_ROOT not in sys.path:
    sys.path.insert(0, _MONOREPO_ROOT)


# CRITICAL: Set environment variables BEFORE imports
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./cv_test.db"
os.environ["SECRET_KEY"] = "testsecret"
os.environ["REDIS_URL"] = "redis://localhost:6379/7"
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test-project")

with patch("opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter", return_value=MagicMock()):
    mock_redis = AsyncMock()
    # It needs to return a valid JSON string or None for get()
    mock_redis.get.return_value = None
    with patch("redis.asyncio.from_url", return_value=mock_redis):
        from main import app
        from database import get_db
    from src.auth import verify_jwt


def override_verify_jwt():
    return {"sub": "test", "email": "test@zenika.com", "role": "admin"}


async def override_get_db():
    db = AsyncMock()
    yield db

app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[verify_jwt] = override_verify_jwt


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c
