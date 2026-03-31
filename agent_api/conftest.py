import os
import sys
import pytest
from unittest.mock import MagicMock, patch

# Mock missing modules BEFORE any imports from the app
def mock_package(name):
    mock = MagicMock()
    sys.modules[name] = mock
    return mock

mock_package("google")
mock_package("google.genai")
mock_package("google.adk")
mock_package("google.adk.agents")
mock_package("google.adk.tools")
mock_package("google.adk.sessions")
mock_package("opentelemetry")
mock_package("opentelemetry.trace")
mock_package("opentelemetry.propagate")
mock_package("opentelemetry.sdk")
mock_package("opentelemetry.sdk.trace")
mock_package("opentelemetry.sdk.trace.export")
mock_package("opentelemetry.sdk.resources")
mock_package("opentelemetry.semconv")
mock_package("opentelemetry.semconv.resource")
mock_package("opentelemetry.exporter")
mock_package("opentelemetry.exporter.otlp")
mock_package("opentelemetry.exporter.otlp.proto")
mock_package("opentelemetry.exporter.otlp.proto.grpc")
mock_package("opentelemetry.exporter.otlp.proto.grpc.trace_exporter")
mock_package("opentelemetry.instrumentation")
mock_package("opentelemetry.instrumentation.fastapi")
mock_package("opentelemetry.instrumentation.sqlalchemy")

# Set environment variables
os.environ["GOOGLE_API_KEY"] = "test-key"
os.environ["GEMINI_MODEL"] = "gemini-2.0-flash"

# Now we can safely import the app
from main import app

@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        yield c
