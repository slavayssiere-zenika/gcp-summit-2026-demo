"""
jwt_middleware.py — Validation JWT partagée pour tous les agents Zenika.

Fournit deux variantes de `verify_jwt` selon la convention FastAPI utilisée :
  - `verify_jwt_bearer(auth)` : pour les agents utilisant HTTPAuthorizationCredentials
    (agent_hr_api, agent_ops_api, agent_router_api)
  - `verify_jwt_request(request)` : pour les agents utilisant Request directement
    (agent_missions_api)

Les deux variantes :
  - Valident la signature HS256 avec SECRET_KEY
  - Vérifient l'expiration du token
  - Exigent la présence du claim `sub`
  - Propagent auth_header_var pour la traçabilité MCP sortante

Usage :
    from agent_commons.jwt_middleware import verify_jwt_bearer, ALGORITHM
    from fastapi import Depends
    from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

    security = HTTPBearer()
    protected_router = APIRouter(dependencies=[Depends(verify_jwt_bearer)])
"""

import logging
import os

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from jose import jwt as jose_jwt

from agent_commons.mcp_client import auth_header_var

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"
_security = HTTPBearer()


SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    raise ValueError(
        "SECRET_KEY est absente ou vide. "
        "Définissez-la dans votre .env ou via Secret Manager GCP."
    )


def verify_jwt_bearer(
    auth: HTTPAuthorizationCredentials = Depends(_security),
) -> dict:
    """Valide un JWT fourni via HTTPAuthorizationCredentials (Bearer header).

    Utilisé dans : agent_hr_api, agent_ops_api, agent_router_api.

    Valide :
    - Signature HS256 avec SECRET_KEY
    - Expiration du token
    - Présence obligatoire du claim `sub`

    Propage auth_header_var pour la traçabilité MCP sortante.

    Raises:
        HTTPException 401 si le token est invalide, expiré ou si `sub` est absent.
    """
    try:
        payload = jose_jwt.decode(auth.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        if not payload.get("sub"):
            raise HTTPException(
                status_code=401, detail="Token invalide : claim 'sub' manquant"
            )
        auth_header_var.set(f"Bearer {auth.credentials}")
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Token invalide ou expiré")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Token invalide")


async def verify_jwt_request(request: Request) -> dict:
    """Valide un JWT fourni via l'objet Request FastAPI (Authorization header).

    Utilisé dans : agent_missions_api.

    Valide :
    - Présence et format du header Authorization: Bearer <token>
    - Signature HS256 avec SECRET_KEY
    - Expiration du token
    - Présence obligatoire du claim `sub`

    Propage auth_header_var pour la traçabilité MCP sortante.

    Raises:
        HTTPException 401 si le header est absent, malformé, ou le token invalide.
    """
    import jwt as pyjwt  # PyJWT (agent_missions_api convention)

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or malformed Authorization header",
        )
    token = auth_header.split(" ", 1)[1]
    try:
        payload = jose_jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if not payload.get("sub"):
            raise HTTPException(
                status_code=401, detail="Token invalide : claim 'sub' manquant"
            )
        auth_header_var.set(auth_header)
        return payload
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Token invalide ou expiré: {e}")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid JWT: {e}")
