import asyncio
from fastapi.testclient import TestClient
from competencies_api.main import app

client = TestClient(app)

def test_get_evaluations():
    # Provide a fake valid JWT token if verify_jwt is active.
    # Actually verify_jwt is mocked or requires token?
    pass
