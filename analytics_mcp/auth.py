import logging
import os
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.auth import jwt as google_jwt
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from jose import JWTError, jwt

# --- Configuration JWT ---
# SECRET_KEY est obligatoire au démarrage — aucun fallback permis (AGENTS.md §4)
_SECRET_KEY = os.getenv("SECRET_KEY")
if not _SECRET_KEY:
    raise ValueError(
        "SECRET_KEY environment variable is not set. "
        "For local dev, add SECRET_KEY=<dev-value> to your .env file."
    )
# Purge immédiate de l'environnement (anti prompt-injection / anti leakage)
os.environ.pop("SECRET_KEY", None)

ALGORITHM = "HS256"
logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


def verify_jwt(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """Validate JWT from Authorization header or HTTP-Only cookie.

    Priority:
      1. Authorization: Bearer <token>  (API / inter-service calls)
      2. Cookie 'access_token'           (browser SPA calls)

    Raises HTTP 401 if:
      - No token found in header or cookie
      - Token signature is invalid
      - Token is expired
      - Claim 'sub' is missing

    NO fallback is permitted regardless of environment (AGENTS.md §4).
    """
    # 1. Try Authorization Bearer header first
    token: Optional[str] = None
    if credentials and credentials.credentials:
        token = credentials.credentials

    # 2. Fallback to HTTP-Only cookie (legitimate for browser SPA)
    if not token:
        token = request.cookies.get("access_token")

    if not token:
        logger.warning("Authentication failed: no token in Authorization header or cookie.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token d'authentification manquant",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        unverified_header = jwt.get_unverified_header(token)
        if unverified_header.get("alg") == "RS256":
            try:
                unverified_claims = google_jwt.decode(token, verify=False)
                token_aud = unverified_claims.get("aud")

                payload = id_token.verify_oauth2_token(
                    token, google_requests.Request(), audience=token_aud
                )

                if payload.get("email") and "sa-agent-router" in payload.get("email"):
                    payload["role"] = "admin"
                    payload["sub"] = payload.get("email")
                    return payload
                else:
                    logger.warning("Tentative d'accès OIDC non autorisé: %s", payload.get("email"))
                    raise HTTPException(status_code=403, detail="Service Account non autorisé")
            except HTTPException:
                raise
            except Exception as e:
                logger.debug("Échec validation OIDC: %s", e)
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token OIDC invalide",
                    headers={"WWW-Authenticate": "Bearer"},
                )

        payload = jwt.decode(token, _SECRET_KEY, algorithms=[ALGORITHM])
        if not payload.get("sub"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token invalide : claim 'sub' manquant",
            )
        return payload
    except JWTError as exc:
        logger.debug("JWT validation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expiré",
            headers={"WWW-Authenticate": "Bearer"},
        )
