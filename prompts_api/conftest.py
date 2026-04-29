import os
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient

# CRITICAL: Set environment variables BEFORE imports
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./prompts_test.db"
os.environ["SECRET_KEY"] = "testsecret"
os.environ["GEMINI_PRO_MODEL"] = "gemini-1.5-pro-001"
os.environ["GCP_PROJECT_ID"] = "test-project"
os.environ["VERTEX_LOCATION"] = "europe-west1"

with patch("opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter", return_value=MagicMock()):
    from main import app
    from database import get_db
    from src.prompts.router import verify_jwt

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
