import pytest
from main import app
from fastapi.testclient import TestClient
import json

client = TestClient(app)

def test_metrics():
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "process_cpu_seconds_total" in response.text or "python_gc_objects_collected_total" in response.text

def test_docs():
    response = client.get("/docs")
    assert response.status_code == 200
    assert "Swagger" in response.text

def test_openapi_json():
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert "openapi" in response.json()
