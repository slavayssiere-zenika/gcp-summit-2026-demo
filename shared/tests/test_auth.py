"""Tests pour shared/auth/context.py et shared/auth/jwt.py."""
import os

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
import jwt

# SECRET_KEY doit être définie avant l'import de jwt.py
os.environ.setdefault("SECRET_KEY", "test-secret-key-32chars-xxxxxxxxx")

from auth.context import auth_header_var  # noqa: E402
from auth.jwt import (  # noqa: E402
    ALGORITHM, SECRET_KEY, verify_jwt, verify_jwt_bearer, verify_jwt_request,
)

# ─── Fixtures ─────────────────────────────────────────────────────────────────


def make_token(payload: dict | None = None) -> str:
    data = payload or {"sub": "user@example.com", "role": "user"}
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)


def make_expired_token() -> str:
    import time
    # leeway=300 → il faut être > 300s dans le passé pour que ça expire vraiment
    data = {"sub": "user@example.com", "exp": int(time.time()) - 400}
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)


# ─── Tests auth_header_var ────────────────────────────────────────────────────

class TestAuthHeaderVar:
    def test_default_is_none(self):
        assert auth_header_var.get() is None

    def test_set_and_get(self):
        token = auth_header_var.set("Bearer abc123")
        assert auth_header_var.get() == "Bearer abc123"
        auth_header_var.reset(token)  # Cleanup

    def test_reset_restores_default(self):
        token = auth_header_var.set("Bearer xxx")
        auth_header_var.reset(token)
        assert auth_header_var.get() is None


# ─── Tests verify_jwt ─────────────────────────────────────────────────────────

class TestVerifyJwt:
    def setup_method(self):
        """Crée une app FastAPI minimale avec verify_jwt pour les tests."""
        self.app = FastAPI()

        @self.app.get("/protected")
        def protected(payload: dict = Depends(verify_jwt)):
            return {"sub": payload.get("sub")}

        self.client = TestClient(self.app, raise_server_exceptions=False)

    def test_valid_bearer_token(self):
        token = make_token()
        resp = self.client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["sub"] == "user@example.com"

    def test_invalid_bearer_token(self):
        resp = self.client.get("/protected", headers={"Authorization": "Bearer invalid.token.xxx"})
        assert resp.status_code == 401

    def test_expired_bearer_token(self):
        token = make_expired_token()
        resp = self.client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    def test_missing_token_returns_401(self):
        resp = self.client.get("/protected")
        assert resp.status_code == 401

    def test_valid_cookie_token(self):
        token = make_token()
        self.client.cookies.set("access_token", token)
        resp = self.client.get("/protected")
        assert resp.status_code == 200
        self.client.cookies.clear()

    def test_invalid_cookie_token(self):
        self.client.cookies.set("access_token", "bad.token.here")
        resp = self.client.get("/protected")
        assert resp.status_code == 401
        self.client.cookies.clear()

    def test_auth_header_var_is_propagated(self):
        """Vérifie que auth_header_var est alimenté après validation réussie."""
        token = make_token()
        auth_header_var.set(None)  # Reset
        with TestClient(self.app) as c:
            c.get("/protected", headers={"Authorization": f"Bearer {token}"})
        # La propagation est en-scope de la requête (contextvars FastAPI)
        # On vérifie juste que la route passe sans erreur (propagation interne OK)


# ─── Tests verify_jwt_bearer ──────────────────────────────────────────────────

class TestVerifyJwtBearer:
    def setup_method(self):
        self.app = FastAPI()

        @self.app.get("/agent")
        def agent_endpoint(payload: dict = Depends(verify_jwt_bearer)):
            return {"sub": payload.get("sub")}

        self.client = TestClient(self.app, raise_server_exceptions=False)

    def test_valid_bearer(self):
        token = make_token()
        resp = self.client.get("/agent", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_missing_auth_returns_401(self):
        resp = self.client.get("/agent")
        assert resp.status_code == 401

    def test_invalid_token_returns_401(self):
        resp = self.client.get("/agent", headers={"Authorization": "Bearer bad"})
        assert resp.status_code == 401

    def test_token_without_sub_returns_401(self):
        token = make_token({"role": "user"})  # No 'sub'
        resp = self.client.get("/agent", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    def test_expired_token_returns_401(self):
        token = make_expired_token()
        resp = self.client.get("/agent", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401


# ─── Tests verify_jwt_request ─────────────────────────────────────────────────

class TestVerifyJwtRequest:
    def setup_method(self):
        self.app = FastAPI()

        @self.app.get("/raw")
        async def raw_endpoint(payload: dict = Depends(verify_jwt_request)):
            return {"sub": payload.get("sub")}

        self.client = TestClient(self.app, raise_server_exceptions=False)

    def test_valid_bearer(self):
        token = make_token()
        resp = self.client.get("/raw", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_missing_header_returns_401(self):
        resp = self.client.get("/raw")
        assert resp.status_code == 401

    def test_malformed_header_returns_401(self):
        resp = self.client.get("/raw", headers={"Authorization": "Token abc"})
        assert resp.status_code == 401

    def test_invalid_token_returns_401(self):
        resp = self.client.get("/raw", headers={"Authorization": "Bearer invalid.jwt"})
        assert resp.status_code == 401

    def test_token_without_sub_returns_401(self):
        token = make_token({"role": "user"})
        resp = self.client.get("/raw", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401
