from auth import verify_jwt
from fastapi.testclient import TestClient
import pytest
from unittest.mock import MagicMock, patch
import os
import sys
from mcp_app import app

# Assure que la racine du monorepo est dans sys.path pour résoudre `shared/`
_MONOREPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _MONOREPO_ROOT not in sys.path:
    sys.path.insert(0, _MONOREPO_ROOT)

# CRITICAL: Set environment variables BEFORE any imports
os.environ["SECRET_KEY"] = "testsecret"
print("CONFTEST SAYS SECRET_KEY:", os.environ.get("SECRET_KEY"))

os.environ["REDIS_URL"] = "redis://localhost:6379/14"
os.environ["GCP_PROJECT_ID"] = "test-project"


with patch("opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter", return_value=MagicMock()):
    with patch("mcp_server.client", MagicMock()):
        pass


def override_verify_jwt():
    return {"sub": "test", "email": "test@zenika.com", "role": "admin"}


app.dependency_overrides[verify_jwt] = override_verify_jwt


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c
