import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from auth import verify_jwt
from mcp_app import app

# CRITICAL: Set environment variables BEFORE imports
os.environ["SECRET_KEY"] = "testsecret"
os.environ["REDIS_URL"] = "redis://localhost:6379/13"
os.environ["GCP_PROJECT_ID"] = "test-project"

with patch("opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter", return_value=MagicMock()):
    pass


def override_verify_jwt():
    return {"sub": "test", "email": "test@zenika.com", "role": "admin"}


app.dependency_overrides[verify_jwt] = override_verify_jwt


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c
