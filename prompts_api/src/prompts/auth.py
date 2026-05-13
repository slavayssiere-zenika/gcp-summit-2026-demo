import logging
import os
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.auth import jwt as google_jwt
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from jose import JWTError, jwt

logger = logging.getLogger(__name__)

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY must be set in environment variables")
os.environ.pop("SECRET_KEY", None)  # Purge post-démarrage — anti prompt-injection (AGENTS.md §2)
ALGORITHM = "HS256"

# Email du Service Account cv_api autorisé à appeler prompts_api via OIDC (batch taxonomy).
# Injecté via Terraform (cr_prompts.tf → BATCH_CALLER_SA_EMAIL = google_service_account.cv_sa.email).
BATCH_CALLER_SA_EMAIL: str = os.getenv("BATCH_CALLER_SA_EMAIL", "")

security = HTTPBearer(auto_error=False)


def verify_jwt(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """
    Vérifie le token JWT. Priorité au header Authorization, puis au cookie access_token.
    Supporte les tokens HS256 (applicatifs) et RS256 (Google OIDC — sa-cv pour le batch taxonomy).
    """
    # 1. Tentative via le Header Authorization
    if credentials:
        try:
            return _decode_and_validate(credentials.credentials)
        except HTTPException:
            raise
        except Exception as e:
            logger.debug(f"Échec validation via header, tentative via cookie: {e}")

    # 2. Fallback via le Cookie
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou manquant",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return _decode_and_validate(token)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur de validation JWT (tout mode): {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expiré",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _decode_and_validate(token: str) -> dict:
    """Helper interne pour décoder et valider un token (HS256 ou RS256 OIDC Google)."""
    try:
        unverified_header = jwt.get_unverified_header(token)
        if unverified_header.get("alg") == "RS256":
            # Potentiel token OIDC Google (sa-cv via batch taxonomy)
            try:
                unverified_claims = google_jwt.decode(token, verify=False)
                token_aud = unverified_claims.get("aud")

                # Validation complète de la signature OIDC via les serveurs Google
                payload = id_token.verify_oauth2_token(
                    token, google_requests.Request(), audience=token_aud
                )

                caller_email: str = payload.get("email", "")
                # Zero-Trust : seul le SA cv_api (configuré via BATCH_CALLER_SA_EMAIL) est autorisé
                if BATCH_CALLER_SA_EMAIL and caller_email == BATCH_CALLER_SA_EMAIL:
                    logger.info(
                        f"[auth] Accès OIDC autorisé pour le Service Account batch : {caller_email}"
                    )
                    # Enrichissement du payload pour la compatibilité avec les guards existants
                    payload["role"] = "service_account"
                    payload["sub"] = caller_email
                    return payload
                else:
                    logger.warning(
                        f"[auth] Tentative d'accès OIDC avec un Service Account non autorisé : "
                        f"{caller_email!r} (attendu : {BATCH_CALLER_SA_EMAIL!r})"
                    )
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Service Account non autorisé",
                    )
            except HTTPException:
                raise
            except Exception as e:
                logger.debug(f"Échec de la validation Google OIDC : {e}")
                raise JWTError("Invalid OIDC Token")

        # Validation JWT applicative classique (HS256)
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if not payload.get("sub"):
            logger.warning("[JWT] Token HS256 valide mais claim 'sub' manquant — accès refusé.")
            raise HTTPException(status_code=401, detail="Claim 'sub' manquant")
        return payload
    except JWTError as e:
        logger.debug(f"[JWT] Erreur de décodage JWTError: {e}")
        raise
