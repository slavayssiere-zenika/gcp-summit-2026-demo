import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ["GOOGLE_API_KEY"] = "test-key"
os.environ["GEMINI_HR_MODEL"] = "gemini-3.1-flash-lite-preview"
os.environ["GEMINI_MODEL"] = "gemini-3.1-flash-lite-preview"
os.environ["SECRET_KEY"] = "testsecret"

from main import app

@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        yield c
