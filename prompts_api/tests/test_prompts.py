import pytest
from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200

def test_get_not_found():
    response = client.get("/prompts/fake.prompt.unknown")
    assert response.status_code == 404
