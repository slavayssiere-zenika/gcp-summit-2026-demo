from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os

# Configuration for JWT
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY must be set in environment variables")
os.environ.pop("SECRET_KEY", None)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15  # 15 minutes
REFRESH_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 # 7 days

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

security = HTTPBearer(auto_error=False)

def _is_user_blacklisted(username: str) -> bool:
    """Vérifie si un utilisateur est blacklisté (suspendu) en Redis (F-05)."""
    try:
        import redis as _redis
        import os as _os
        _r = _redis.from_url(_os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)
        return _r.exists(f"jwt:blacklist:user:{username}") > 0
    except Exception:
        return False  # Fail-open si Redis indisponible (évite le blocage total)

def verify_jwt(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> dict:
    # 1. Try token from Authorization header if present
    if credentials:
        try:
            payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
            if payload.get("type") == "refresh":
                raise JWTError("Refresh token cannot be used as access token")
            # Vérification blacklist Redis (compte suspendu)
            username = payload.get("sub")
            if username and _is_user_blacklisted(username):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Compte suspendu — accès révoqué",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return payload
        except JWTError:
            # If header token is invalid, we don't fail yet, we'll try the cookie
            pass
    
    # 2. Try token from HTTP-Only cookie
    token = request.cookies.get("access_token")
    if not token:
        # Check if we were provided a credentials object that failed
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
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") == "refresh":
            raise JWTError("Refresh token cannot be used as access token")
        # Vérification blacklist Redis (compte suspendu)
        username = payload.get("sub")
        if username and _is_user_blacklisted(username):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Compte suspendu — accès révoqué",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expiré",
            headers={"WWW-Authenticate": "Bearer"},
        )
