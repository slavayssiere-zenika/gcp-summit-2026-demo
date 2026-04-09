from jose import JWTError, jwt
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import Depends, HTTPException, status
import os
import logging
from google.oauth2 import id_token
from google.auth.transport import requests
from google.auth import jwt as google_jwt

logger = logging.getLogger(__name__)

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY must be set in environment variables")
ALGORITHM = "HS256"

security = HTTPBearer()

def verify_jwt(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    token = credentials.credentials
    try:
        # Check token headers without verification to identify token type (HS256 vs RS256)
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
                # Si la validation Google échoue, on log et on passe au fallback local
                logger.debug(f"Échec de la validation Google OIDC : {e}")

        # Validation JWT applicative classique (HS256)
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError as e:
        logger.error(f"Erreur de validation JWT applicatif: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou manquant",
            headers={"WWW-Authenticate": "Bearer"},
        )
