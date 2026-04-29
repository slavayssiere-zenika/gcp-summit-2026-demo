import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# CRITICAL: Set environment variables BEFORE any imports
os.environ["SECRET_KEY"] = "testsecret"
os.environ["GOOGLE_API_KEY"] = "test-key"
os.environ["GEMINI_ROUTER_MODEL"] = "gemini-3.1-flash-lite-preview"
os.environ["GEMINI_MODEL"] = "gemini-3.1-flash-lite-preview"

from main import app

@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        yield c
