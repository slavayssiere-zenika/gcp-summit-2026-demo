import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
import jwt

from shared.auth.jwt import SECRET_KEY as _SECRET_KEY, verify_jwt


@pytest.fixture
def mock_request():
    class MockRequest:
        def __init__(self):
            self.cookies = {}
    return MockRequest()


def test_verify_jwt_no_token(mock_request):
    with pytest.raises(HTTPException) as exc:
        verify_jwt(mock_request, credentials=None)
    assert exc.value.status_code == 401
    assert "manquant" in exc.value.detail


def test_verify_jwt_with_header(mock_request):
    token = jwt.encode({"sub": "user@example.com"}, _SECRET_KEY, algorithm="HS256")
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    payload = verify_jwt(mock_request, credentials=creds)
    assert payload["sub"] == "user@example.com"


def test_verify_jwt_with_cookie(mock_request):
    token = jwt.encode({"sub": "user@example.com"}, _SECRET_KEY, algorithm="HS256")
    mock_request.cookies["access_token"] = token

    payload = verify_jwt(mock_request, credentials=None)
    assert payload["sub"] == "user@example.com"


def test_verify_jwt_no_sub(mock_request):
    token = jwt.encode({"other": "value"}, _SECRET_KEY, algorithm="HS256")
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(HTTPException) as exc:
        verify_jwt(mock_request, credentials=creds)
    assert exc.value.status_code == 401
    assert "claim 'sub' manquant" in exc.value.detail


def test_verify_jwt_invalid_token(mock_request):
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid_token")

    with pytest.raises(HTTPException) as exc:
        verify_jwt(mock_request, credentials=creds)
    assert exc.value.status_code == 401
    assert "invalide ou expiré" in exc.value.detail
