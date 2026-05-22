"""test_jwt_security.py — Integration tests for JWT security mechanisms.

Validates that token encoding, decoding, expirations, and claim constraints are
perfectly robust under HS256 algorithm without any mock bypass.
"""

import os
import time
from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
import jwt
import pytest

# Ensure SECRET_KEY is set for testing
os.environ["SECRET_KEY"] = "integration-test-secret-key-12345-long-key-32-chars"

from shared.auth.jwt import (  # noqa: E402
    ALGORITHM,
    SECRET_KEY,
    verify_jwt,
    verify_jwt_bearer,
    verify_jwt_request,
)


class MockRequest:
    """A minimal mock request to simulate FastAPI requests."""

    def __init__(self, headers=None, cookies=None):
        self.headers = headers or {}
        self.cookies = cookies or {}


def test_verify_jwt_valid_bearer():
    """Validates that a correctly signed HS256 bearer token is successfully parsed."""
    payload = {"sub": "alice@zenika.com", "role": "admin", "exp": int(time.time()) + 3600}
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    req = MockRequest()

    decoded_payload = verify_jwt(req, credentials)
    assert decoded_payload["sub"] == "alice@zenika.com"
    assert decoded_payload["role"] == "admin"


def test_verify_jwt_invalid_secret():
    """Validates that a token signed with an invalid secret is correctly rejected."""
    payload = {"sub": "alice@zenika.com", "role": "admin", "exp": int(time.time()) + 3600}
    bad_token = jwt.encode(payload, "wrong-secret-key-that-is-at-least-32-chars-long", algorithm=ALGORITHM)

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=bad_token)
    req = MockRequest()

    with pytest.raises(HTTPException) as exc_info:
        verify_jwt(req, credentials)
    assert exc_info.value.status_code == 401
    assert "Token invalide" in exc_info.value.detail


def test_verify_jwt_missing_sub():
    """Validates that a token missing the 'sub' claim is rejected."""
    payload = {"role": "admin", "exp": int(time.time()) + 3600}
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    req = MockRequest()

    with pytest.raises(HTTPException) as exc_info:
        verify_jwt(req, credentials)
    assert exc_info.value.status_code == 401
    assert "claim 'sub' manquant ou vide" in exc_info.value.detail


def test_verify_jwt_expired():
    """Validates that an expired token is correctly rejected."""
    # leeway in verify_jwt is 300s (5 mins), so set exp to -400s to force expiration failure
    payload = {"sub": "alice@zenika.com", "exp": int(time.time()) - 400}
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    req = MockRequest()

    with pytest.raises(HTTPException) as exc_info:
        verify_jwt(req, credentials)
    assert exc_info.value.status_code == 401
    assert "Token invalide ou expiré" in exc_info.value.detail


def test_verify_jwt_via_cookie():
    """Validates that JWT token can be securely parsed from cookies fallback."""
    payload = {"sub": "bob@zenika.com", "exp": int(time.time()) + 3600}
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    req = MockRequest(cookies={"access_token": token})

    decoded_payload = verify_jwt(req, None)
    assert decoded_payload["sub"] == "bob@zenika.com"


def test_verify_jwt_bearer_isolated():
    """Validates verify_jwt_bearer endpoint utility used in agents."""
    payload = {"sub": "hr_agent@zenika.com", "exp": int(time.time()) + 3600}
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    decoded = verify_jwt_bearer(credentials)
    assert decoded["sub"] == "hr_agent@zenika.com"


def test_verify_jwt_request_helper():
    """Validates verify_jwt_request helper directly fetching from Request header."""
    payload = {"sub": "ops@zenika.com", "exp": int(time.time()) + 3600}
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    class FastApiRequestMock(Request):
        def __init__(self, headers):
            self._headers = headers

        @property
        def headers(self):
            return self._headers

    req = FastApiRequestMock(headers={"Authorization": f"Bearer {token}"})

    # Run the coroutine synchronously for simple pytest integration
    import asyncio
    decoded = asyncio.run(verify_jwt_request(req))
    assert decoded["sub"] == "ops@zenika.com"
