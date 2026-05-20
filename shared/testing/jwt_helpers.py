"""
Utilitaires JWT pour les tests de conformité Zero-Trust.

Usage:
    from shared.testing.jwt_helpers import make_jwt, make_expired_jwt, make_wrong_key_jwt

    def test_protected_endpoint(client):
        headers = {"Authorization": f"Bearer {make_jwt()}"}
        resp = client.get("/some-endpoint", headers=headers)
        assert resp.status_code == 200

        # Sans token → 401
        assert client.get("/some-endpoint").status_code == 401

        # Token expiré → 401
        resp = client.get("/some-endpoint", headers={
            "Authorization": f"Bearer {make_expired_jwt()}"
        })
        assert resp.status_code == 401
"""
import os
from datetime import datetime, timedelta, timezone

import jwt

ALGORITHM = "HS256"
_DEFAULT_SECRET = os.getenv("SECRET_KEY", "testsecret")


def make_jwt(
    sub: str = "testuser",
    role: str = "admin",
    secret: str = _DEFAULT_SECRET,
    expires_in: int = 60,
    extra_claims: dict | None = None,
) -> str:
    """Génère un token JWT valide HS256 pour les tests.

    Args:
        sub: Identifiant du sujet (username).
        role: Rôle de l'utilisateur (ex: 'admin', 'user').
        secret: Clé secrète HMAC-SHA256.
        expires_in: Durée de validité en minutes.
        extra_claims: Claims additionnels à fusionner dans le payload.

    Returns:
        Token JWT encodé (str).
    """
    payload = {
        "sub": sub,
        "role": role,
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=expires_in),
        "iat": datetime.now(timezone.utc),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def make_expired_jwt(
    sub: str = "testuser",
    role: str = "user",
    secret: str = _DEFAULT_SECRET,
) -> str:
    """Génère un token JWT valide mais expiré (exp dans le passé)."""
    payload = {
        "sub": sub,
        "role": role,
        "type": "access",
        "exp": datetime.now(timezone.utc) - timedelta(minutes=5),
        "iat": datetime.now(timezone.utc) - timedelta(minutes=10),
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def make_wrong_key_jwt(
    sub: str = "testuser",
    role: str = "user",
) -> str:
    """Génère un token signé avec une clé incorrecte — toujours invalide."""
    return make_jwt(sub=sub, role=role, secret="wrong-secret-key-that-is-not-the-real-one")


def make_refresh_jwt(
    sub: str = "testuser",
    secret: str = _DEFAULT_SECRET,
) -> str:
    """Génère un refresh token — INTERDIT d'utiliser comme access token."""
    payload = {
        "sub": sub,
        "type": "refresh",
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def auth_header(
    sub: str = "testuser",
    role: str = "admin",
    secret: str = _DEFAULT_SECRET,
) -> dict:
    """Retourne un dict headers prêt à l'emploi avec Bearer token valide.

    Usage:
        resp = client.get("/endpoint", headers=auth_header())
    """
    return {"Authorization": f"Bearer {make_jwt(sub=sub, role=role, secret=secret)}"}
