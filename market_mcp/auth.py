from typing import Optional
from jose import JWTError, jwt
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import Depends, HTTPException, status, Request
import os

# Configuration for JWT
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"

security = HTTPBearer(auto_error=False)

def verify_jwt(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> dict:
    if not SECRET_KEY:
        # In development, we might not have the secret immediately, but in prod it's mandatory
        if os.getenv("ENVIRONMENT") == "prod":
            raise ValueError("SECRET_KEY must be set in environment variables")
        # Fallback for local dev if not set
        return {"sub": "dev-user", "role": "admin"}

    # 1. Try token from Authorization header if present
    if credentials:
        try:
            payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
            return payload
        except JWTError as je:
            import logging
            logging.debug(f"Header JWT validation failed: {je}")
            pass
    
    # 2. Try token from HTTP-Only cookie (for browser calls)
    token = request.cookies.get("access_token")
    if not token and not credentials:
        import logging
        logging.warning("Authentication failed: No token in cookie AND no credentials in header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token d'authentification manquant",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    try:
        final_token = token if token else credentials.credentials
        payload = jwt.decode(final_token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except Exception as e:
        import logging
        logging.error(f"JWT Verification Error in Market MCP: {e} (Secret Key present: {bool(SECRET_KEY)})")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expiré",
            headers={"WWW-Authenticate": "Bearer"},
        )
