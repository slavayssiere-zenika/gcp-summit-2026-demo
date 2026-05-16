import os
os.environ["SECRET_KEY"] = "test-secret-key-missions"

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from main import app
import jwt

SECRET_KEY = os.environ.get("SECRET_KEY", "test-secret-key-missions")
ALGORITHM = "HS256"

def make_jwt(sub: str = "test@zenika.com") -> str:
    return jwt.encode({"sub": sub, "exp": 9999999999}, SECRET_KEY, algorithm=ALGORITHM)

client = TestClient(app, raise_server_exceptions=True)

mock_session_service = AsyncMock()
mock_session_service.get_session.return_value = None

with patch("main.get_session_service", return_value=mock_session_service):
    resp = client.get("/history", headers={"Authorization": f"Bearer {make_jwt()}"})
    print("STATUS CODE:", resp.status_code)
    print("RESPONSE BODY:", resp.json())
