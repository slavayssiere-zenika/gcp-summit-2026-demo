from jose import JWTError, jwt
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import Depends, HTTPException, status
import os

SECRET_KEY = os.getenv("SECRET_KEY", "zenika_super_secret_key_change_me_in_production")
ALGORITHM = "HS256"

# In items_api, we use HTTPBearer so Swagger UI just asks for the Bearer token directly
security = HTTPBearer()

def verify_jwt(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou manquant",
            headers={"WWW-Authenticate": "Bearer"},
        )
