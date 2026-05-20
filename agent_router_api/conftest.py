from fastapi.testclient import TestClient
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# CRITICAL: Set environment variables BEFORE any imports
os.environ["SECRET_KEY"] = "testsecret_must_be_32_characters_long_for_sha256"
os.environ["GOOGLE_API_KEY"] = "test-key"
os.environ["GEMINI_ROUTER_MODEL"] = "gemini-3.1-flash-lite-preview"
os.environ["GEMINI_MODEL"] = "gemini-3.1-flash-lite-preview"

import pytest  # noqa: E402
from main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c
