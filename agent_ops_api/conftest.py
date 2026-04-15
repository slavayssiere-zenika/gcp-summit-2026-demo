import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ["GOOGLE_API_KEY"] = "test-key"
os.environ["GEMINI_MODEL"] = "gemini-2.0-flash"

from main import app

@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        yield c
