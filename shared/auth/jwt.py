import os
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from shared.auth.context import auth_header_var

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
        try:
            payload = jwt.decode(
                credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM], options={"leeway": 300}
            )
            # Propagate auth context
            auth_header_var.set(f"Bearer {credentials.credentials}")
            return payload
        except JWTError:
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
        auth_header_var.set(f"Bearer {token}")
        return payload
    except JWTError:
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
    try:
        payload = jwt.decode(
            auth.credentials, SECRET_KEY, algorithms=[ALGORITHM], options={"leeway": 300}
        )
        if not payload.get("sub"):
            raise HTTPException(status_code=401, detail="Token invalide : claim 'sub' manquant")
        auth_header_var.set(f"Bearer {auth.credentials}")
        return payload
    except JWTError:
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
    token = auth_header.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={"leeway": 300})
        if not payload.get("sub"):
            raise HTTPException(status_code=401, detail="Token invalide : claim 'sub' manquant")
        auth_header_var.set(auth_header)
        return payload
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Token invalide ou expiré: {e}")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid JWT: {e}")
