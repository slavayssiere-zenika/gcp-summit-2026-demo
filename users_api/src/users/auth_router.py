import logging
import os
import secrets as pysecrets
import string
from datetime import timedelta
from urllib.parse import urlencode

import requests
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from cache import delete_cache, delete_cache_pattern
from database import get_db
from metrics import USER_LOGINS_TOTAL, USER_CREATIONS_TOTAL
from src.auth import (
    get_password_hash,
    verify_password,
    create_access_token,
    create_refresh_token,
    SECRET_KEY,
    ALGORITHM,
    verify_jwt,
)
from src.users.models import User, UserAuditLog
from src.users.schemas import LoginRequest, TokenResponse, ServiceAccountLoginRequest

_log = logging.getLogger(__name__)

auth_router = APIRouter(prefix="", tags=["auth"])

def _set_auth_cookies(request: Request, response: Response, access_token: str, refresh_token: str) -> None:
    is_https = request.headers.get("x-forwarded-proto", "http").lower() == "https"
    response.set_cookie(key="access_token", value=access_token, httponly=True, max_age=15 * 60, samesite="lax", secure=is_https)
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, max_age=3600 * 24 * 7, samesite="lax", secure=is_https)

@auth_router.post("/login", response_model=TokenResponse)
async def login(login_data: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).filter(User.email == login_data.email))).scalars().first()
    if not user or not verify_password(login_data.password, user.hashed_password):
        USER_LOGINS_TOTAL.labels(status="failure").inc()
        raise HTTPException(status_code=401, detail="Identifiants invalides")

    if not user.is_active:
        USER_LOGINS_TOTAL.labels(status="failure").inc()
        raise HTTPException(status_code=400, detail="Compte inactif")

    USER_LOGINS_TOTAL.labels(status="success").inc()

    allowed_ids = [int(x) for x in user.allowed_category_ids.split(",") if x] if user.allowed_category_ids else []
    token_data = {"sub": user.username, "allowed_category_ids": allowed_ids, "role": user.role}
    access_token = create_access_token(data=token_data)
    refresh_token = create_refresh_token(data={"sub": user.username})

    _set_auth_cookies(request, response, access_token, refresh_token)

    return TokenResponse(access_token=access_token, token_type="bearer", username=user.username, role=user.role)

@auth_router.post("/refresh", response_model=TokenResponse)
async def refresh_token_route(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    refresh_token_cookie = request.cookies.get("refresh_token")
    if not refresh_token_cookie:
        raise HTTPException(status_code=401, detail="Refresh token manquant")

    try:
        payload = jwt.decode(refresh_token_cookie, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Token de type invalide")
        username: str = payload.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="Token invalide")
    except JWTError:
        raise HTTPException(status_code=401, detail="Refresh token expiré ou invalide")

    user = (await db.execute(select(User).filter(User.username == username))).scalars().first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Compte inactif ou introuvable")

    allowed_ids = [int(x) for x in user.allowed_category_ids.split(",") if x] if user.allowed_category_ids else []

    token_data = {"sub": user.username, "allowed_category_ids": allowed_ids, "role": user.role}
    new_access = create_access_token(data=token_data)
    new_refresh = create_refresh_token(data={"sub": user.username})

    _set_auth_cookies(request, response, new_access, new_refresh)

    return TokenResponse(access_token=new_access, token_type="bearer", username=user.username, role=user.role)

@auth_router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return {"message": "Déconnexion réussie"}

@auth_router.post("/service-account/login", response_model=TokenResponse)
async def service_account_login(req: ServiceAccountLoginRequest, db: AsyncSession = Depends(get_db)):
    try:
        request_obj = google_requests.Request()
        id_info = id_token.verify_oauth2_token(req.id_token, request_obj)

        email = id_info.get("email")
        if not email:
            raise HTTPException(status_code=403, detail="Un email est requis dans l'ID Token")

        if not email.endswith(".iam.gserviceaccount.com"):
             raise HTTPException(status_code=403, detail="Ce token n'appartient pas à un Service Account autorisé")

        sa_token_ttl = int(os.getenv("SA_TOKEN_TTL_MINUTES", "120"))
        access_token = create_access_token(
            data={"sub": email, "role": "service_account", "allowed_category_ids": []},
            expires_delta=timedelta(minutes=sa_token_ttl)
        )

        return TokenResponse(access_token=access_token, token_type="bearer", username=email, role="service_account")
    except ValueError as e:
        raise HTTPException(status_code=401, detail=f"Token invalide: {e}")

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_SECRET_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_SECRET_KEY", "")

@auth_router.get("/google/config")
async def get_google_config():
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Google Client ID not configured")
    return {"client_id": GOOGLE_CLIENT_ID}

@auth_router.get("/google/login")
async def google_login(request: Request):
    scheme = request.headers.get("x-forwarded-proto", "http")
    host = request.headers.get("host", "localhost")
    redirect_uri = f"{scheme}://{host}/auth/google/callback"

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent"
    }
    url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    return RedirectResponse(url)

@auth_router.get("/google/callback")
async def google_callback(request: Request, code: str, response: Response, db: AsyncSession = Depends(get_db)):
    scheme = request.headers.get("x-forwarded-proto", "http")
    host = request.headers.get("host", "localhost")
    redirect_uri = f"{scheme}://{host}/auth/google/callback"

    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Google Client ID or Secret not configured")

    token_url = "https://oauth2.googleapis.com/token"
    token_data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code"
    }
    token_res = requests.post(token_url, data=token_data)
    if not token_res.ok:
        raise HTTPException(status_code=400, detail="Failed to get token from Google")
    
    access_token_google = token_res.json().get("access_token")
    
    userinfo_url = "https://openidconnect.googleapis.com/v1/userinfo"
    userinfo_res = requests.get(userinfo_url, headers={"Authorization": f"Bearer {access_token_google}"})
    if not userinfo_res.ok:
        raise HTTPException(status_code=400, detail="Failed to get user info from Google")
        
    user_info = userinfo_res.json()
    email = user_info.get("email")
    if not email or not email.endswith("@zenika.com"):
        raise HTTPException(status_code=403, detail="Uniquement les e-mails @zenika.com sont autorisés")
        
    user = (await db.execute(select(User).filter(User.email == email))).scalars().first()
    
    if not user:
        dummy_password = ''.join(pysecrets.choice(string.ascii_letters + string.digits) for _ in range(32))
        db_user = User(
            username=email.split("@")[0],
            email=email,
            first_name=user_info.get("given_name", ""),
            last_name=user_info.get("family_name", ""),
            full_name=user_info.get("name", email.split("@")[0]),
            hashed_password=get_password_hash(dummy_password),
            picture_url=user_info.get("picture", ""),
            google_id=user_info.get("sub", ""),
            allowed_category_ids=""
        )
        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)
        user = db_user
        USER_CREATIONS_TOTAL.inc()
    else:
        user.picture_url = user_info.get("picture", user.picture_url)
        user.google_id = user_info.get("sub", user.google_id)
        await db.commit()
        await db.refresh(user)
    
    USER_LOGINS_TOTAL.labels(status="success").inc()

    allowed_ids = [int(x) for x in user.allowed_category_ids.split(",") if x] if user.allowed_category_ids else []
    access_token = create_access_token(data={
        "sub": user.username,
        "allowed_category_ids": allowed_ids,
        "role": user.role
    })
    refresh_token = create_refresh_token(data={"sub": user.username})
    
    frontend_url = f"{scheme}://{host}/"
    redirect_response = RedirectResponse(frontend_url)
    _set_auth_cookies(request, redirect_response, access_token, refresh_token)
    return redirect_response

@auth_router.get("/health")
async def router_health():
    return {"status": "healthy"}

@auth_router.post("/internal/service-token", response_model=TokenResponse)
async def create_service_token(request: Request, db: AsyncSession = Depends(get_db), token_payload: dict = Depends(verify_jwt)):
    if token_payload.get("role") not in ["admin", "service_account"]:
        raise HTTPException(status_code=403, detail="Privilèges administrateur (ou compte de service) requis pour générer un service token.")

    username = token_payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Claim 'sub' manquant dans le token appelant.")

    allowed_ids = []
    role = token_payload.get("role")
    
    if role != "service_account":
        user = (await db.execute(select(User).filter(User.username == username))).scalars().first()
        if not user or not user.is_active:
            raise HTTPException(status_code=403, detail="Compte inactif ou introuvable.")
        allowed_ids = [int(x) for x in user.allowed_category_ids.split(",") if x] if user.allowed_category_ids else []
        role = user.role

    ttl_minutes = int(os.getenv("SERVICE_TOKEN_TTL_MINUTES", "90"))
    service_token_data = {"sub": username, "allowed_category_ids": allowed_ids, "role": role}
    access_token = create_access_token(data=service_token_data, expires_delta=timedelta(minutes=ttl_minutes))

    _log.info(f"[service-token] Token de service généré pour '{username}' (TTL={ttl_minutes}min)")
    return TokenResponse(access_token=access_token, token_type="bearer", username=username, role=role)

@auth_router.post("/suspend/{email}")
async def suspend_user(email: str, db: AsyncSession = Depends(get_db), token_payload: dict = Depends(verify_jwt)):
    if token_payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Privilèges administrateur requis pour suspendre un compte.")

    result = await db.execute(select(User).where(User.username == email))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur inexistant.")

    user.is_active = False
    audit_log = UserAuditLog(
        user_id=user.id, admin_username=token_payload.get("sub", "system"),
        action="SUSPEND", field_changed="is_active", old_value="True", new_value="False"
    )
    db.add(audit_log)
    await db.commit()

    from cache import client as redis_client
    BLACKLIST_KEY = f"jwt:blacklist:user:{user.username}"
    redis_client.setex(BLACKLIST_KEY, 15 * 60, "suspended")

    delete_cache(f"users:{user.id}")
    delete_cache_pattern("users:me:*")
    delete_cache_pattern("users:list:*")

    return {"status": "suspended", "email": email}
