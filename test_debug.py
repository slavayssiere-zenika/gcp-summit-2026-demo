import os
import pytest
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./prompts_test.db"
os.environ["SECRET_KEY"] = "testsecret"

from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from shared import database

with patch("opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter", return_value=MagicMock()):
    from main import app
    import src.prompts.router as router

def override_verify_jwt():
    return {"role": "admin", "sub": "test_user@zenika.com"}

async def override_get_db():
    yield "mock_db"

app.dependency_overrides[database.get_db] = override_get_db
app.dependency_overrides[router.verify_jwt] = override_verify_jwt

with TestClient(app) as client:
    response = client.get("/fake.prompt.unknown")
    print(response.status_code)
    print(response.json())
