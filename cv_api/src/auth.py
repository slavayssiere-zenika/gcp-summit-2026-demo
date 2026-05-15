"""
cv_api/src/auth.py — Authentification spécifique à cv_api.

Réexporte `verify_jwt` et `security` depuis `shared.auth.jwt`,
et ajoute `verify_admin` (logique propre à cv_api : rôle admin check).
"""
import logging

from fastapi import Depends, HTTPException, status

from shared.auth.jwt import security, verify_jwt  # noqa: F401 — réexport pour les tests et routers

logger = logging.getLogger(__name__)


def verify_admin(payload: dict = Depends(verify_jwt)) -> dict:
    """Vérifie que l'utilisateur a le rôle admin. Spécifique à cv_api."""
    role = payload.get("role")
    if role != "admin":
        logger.warning(
            f"[Auth] Tentative d'accès admin par un utilisateur non-admin: "
            f"{payload.get('sub')} (role: {role})"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès refusé : privilèges administrateur requis."
        )
    return payload
