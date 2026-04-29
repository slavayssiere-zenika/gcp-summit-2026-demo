from jose import JWTError, jwt
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import Depends, HTTPException, status, Request
import os
import logging
from typing import Optional
from google.oauth2 import id_token
from google.auth.transport import requests
from google.auth import jwt as google_jwt

logger = logging.getLogger(__name__)

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY must be set in environment variables")
ALGORITHM = "HS256"

security = HTTPBearer(auto_error=False)




def verify_jwt(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> dict:
    """
    Vérifie le token JWT. Priorité au header Authorization, puis au cookie access_token.
    Supporte les tokens HS256 (applicatifs) et RS256 (Google OIDC pour Cloud Scheduler).
    """
    # 1. Tentative via le Header Authorization
    if credentials:
        try:
            return _decode_and_validate(credentials.credentials)
        except HTTPException:
            raise # Re-raise 403 (Service Account unauthorized)
        except Exception as e:
            logger.debug(f"Échec validation via header, tentative via cookie: {e}")
            pass

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
    """Helper interne pour décoder et valider un token (HS256 ou RS256)"""
    try:
        unverified_header = jwt.get_unverified_header(token)
        if unverified_header.get("alg") == "RS256":
            # Potentiel token OIDC Google (Cloud Scheduler)
            try:
                unverified_claims = google_jwt.decode(token, verify=False)
                token_aud = unverified_claims.get("aud")
                
                # Validation complète de la signature OIDC via les serveurs Google
                payload = id_token.verify_oauth2_token(token, requests.Request(), audience=token_aud)
                
                # Validation applicative (Zéro-Trust)
                if payload.get("email") and "sa-drive" in payload.get("email"):
                    return payload
                else:
                    logger.warning(f"Tentative d'accès avec un Service Account non autorisé : {payload.get('email')}")
                    raise HTTPException(status_code=403, detail="Service Account non autorisé")
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

