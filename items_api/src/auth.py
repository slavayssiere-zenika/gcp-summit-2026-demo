from jose import JWTError, jwt
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import Depends, HTTPException, status
import os

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY must be set in environment variables")
ALGORITHM = "HS256"

# In items_api, we use HTTPBearer so Swagger UI just asks for the Bearer token directly
security = HTTPBearer()

from fastapi import Request
from typing import Optional

def verify_jwt(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> dict:
    # 1. Try Authorization header
    if credentials:
        try:
            return jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        except JWTError:
            pass
            
    # 2. Try cookie
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou manquant",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expiré",
            headers={"WWW-Authenticate": "Bearer"},
        )

