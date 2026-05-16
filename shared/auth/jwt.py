import logging
import os
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
import jwt
from jwt.exceptions import InvalidTokenError

from shared.auth.context import auth_header_var

logger = logging.getLogger(__name__)

SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    raise ValueError(
        "SECRET_KEY est absente ou vide. "
        "Définissez-la dans votre .env ou via Secret Manager GCP."
    )

ALGORITHM = "HS256"

# HTTPBearer is used for Swagger UI and generic Bearer token extraction
security = HTTPBearer(auto_error=False)


def verify_jwt(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> dict:
    """Valide un JWT fourni via HTTPAuthorizationCredentials ou Cookie (Data APIs)."""
    # 1. Try Authorization header
    if credentials:
        token = credentials.credentials.strip()  # Défense : strip espaces parasites (ex: double espace)
        if token:
            try:
                payload = jwt.decode(
                    token, SECRET_KEY, algorithms=[ALGORITHM], options={"leeway": 300}
                )
                if not payload.get("sub", "").strip():
                    raise HTTPException(status_code=401, detail="Token invalide : claim 'sub' manquant ou vide")
                # Propagate auth context
                auth_header_var.set(f"Bearer {token}")
                return payload
            except InvalidTokenError:
                pass

    # 2. Try cookie
    token = request.cookies.get("access_token")
    if not token:
        if credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token invalide ou expiré",
                headers={"WWW-Authenticate": "Bearer"},
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou manquant",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={"leeway": 300})
        if not payload.get("sub", "").strip():
            raise HTTPException(status_code=401, detail="Token invalide : claim 'sub' manquant ou vide")
        auth_header_var.set(f"Bearer {token}")
        return payload
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expiré",
            headers={"WWW-Authenticate": "Bearer"},
        )


def verify_jwt_bearer(auth: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Valide un JWT fourni via HTTPAuthorizationCredentials (Agents MCP)."""
    if not auth:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou manquant",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = auth.credentials.strip()  # Défense : strip espaces parasites
    if not token:
        raise HTTPException(status_code=401, detail="Token invalide ou manquant")
    try:
        payload = jwt.decode(
            token, SECRET_KEY, algorithms=[ALGORITHM], options={"leeway": 300}
        )
        if not payload.get("sub", "").strip():
            raise HTTPException(status_code=401, detail="Token invalide : claim 'sub' manquant ou vide")
        auth_header_var.set(f"Bearer {token}")
        return payload
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token invalide ou expiré")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Token invalide")


async def verify_jwt_request(request: Request) -> dict:
    """Valide un JWT fourni via l'objet Request FastAPI (Authorization header)."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
    token = auth_header.split(" ", 1)[1].strip()  # Défense : strip espaces parasites
    if not token:
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={"leeway": 300})
        if not payload.get("sub", "").strip():
            raise HTTPException(status_code=401, detail="Token invalide : claim 'sub' manquant ou vide")
        auth_header_var.set(auth_header)
        return payload
    except InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Token invalide ou expiré: {e}")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid JWT: {e}")


class VerifyOIDC:
    def __init__(self, allowed_sa_emails: list[str] = None, audience_env_var: str = None):
        self.allowed_sa_emails = allowed_sa_emails
        self.audience_env_var = audience_env_var

    async def __call__(self, request: Request) -> dict:
        auth_header_val = request.headers.get("Authorization", "")
        if not auth_header_val.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing OIDC Token")

        oidc_token = auth_header_val.replace("Bearer ", "")

        # En local dev (SA non configuré), bypass contrôlé
        invoker_sa_email = os.getenv("PUBSUB_INVOKER_SA_EMAIL", "")
        if not invoker_sa_email or "your-project" in invoker_sa_email:
            return {"sub": "scheduler", "role": "admin"}

        try:
            audience = None
            if self.audience_env_var:
                audience = os.getenv(self.audience_env_var)
            if not audience:
                # Fallback heuristique Cloud Run
                audience = f"https://{request.headers.get('host', '')}"

            decoded = google_id_token.verify_oauth2_token(
                oidc_token, google_requests.Request(), audience=audience
            )
            token_email = decoded.get("email", "")

            allowed = self.allowed_sa_emails or []
            if not allowed:
                # Fallback sur les env vars communes
                cv_sa = os.getenv("CV_SA_EMAIL")
                sch_sa = os.getenv("SCHEDULER_SA_EMAIL")
                if cv_sa:
                    allowed.append(cv_sa)
                if sch_sa:
                    allowed.append(sch_sa)
                if invoker_sa_email:
                    allowed.append(invoker_sa_email)

            if allowed and token_email not in allowed:
                logger.warning(f"[OIDC] Unauthorized SA email: {token_email}. Allowed: {allowed}")
                raise HTTPException(status_code=401, detail="Unauthorized scheduler invoker")

            return {"sub": token_email, "role": "scheduler"}
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning(f"[OIDC] Échec validation OIDC: {exc}")
            raise HTTPException(status_code=401, detail=f"Invalid OIDC token: {exc}")


class VerifyJwtOrOidc:
    def __init__(self, allowed_sa_emails: list[str] = None, audience_env_var: str = None):
        self.oidc_validator = VerifyOIDC(allowed_sa_emails, audience_env_var)

    async def __call__(self, request: Request) -> dict:
        try:
            return await verify_jwt_request(request)
        except HTTPException as e:
            jwt_error = e

        try:
            return await self.oidc_validator(request)
        except HTTPException as oidc_error:
            raise HTTPException(
                status_code=401,
                detail=f"Invalid JWT ({jwt_error.detail}) AND Invalid OIDC ({oidc_error.detail})"
            )
