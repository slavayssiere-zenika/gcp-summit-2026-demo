import logging
import os
import re
import secrets as pysecrets
import string
import unicodedata
from datetime import timedelta
from typing import List
from urllib.parse import urlencode

import requests
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from jose import jwt, JWTError
from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import Session

import httpx
from opentelemetry.propagate import inject

from cache import get_cache, set_cache, delete_cache, delete_cache_pattern
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
from src.users.schemas import (
    UserCreate,
    UserUpdate,
    UserResponse,
    PaginationResponse,
    UserStatsResponse,
    LoginRequest,
    TokenResponse,
    MergeRequest,
    DuplicateCandidate,
    ServiceAccountLoginRequest,
)
from .pubsub import publish_user_event

_log = logging.getLogger(__name__)


router = APIRouter(prefix="", tags=["users"], dependencies=[Depends(verify_jwt)])
auth_router = APIRouter(prefix="", tags=["auth"])

CACHE_TTL = 60


def _set_auth_cookies(request: Request, response: Response, access_token: str, refresh_token: str) -> None:
    """Pose les cookies access_token et refresh_token en respectant le contexte HTTPS.

    Sur GCP Cloud Run, le Load Balancer ajoute X-Forwarded-Proto=https.
    Les navigateurs modernes (Chrome 80+) refusent les cookies SameSite=Lax
    sans l'attribut Secure sur les connexions HTTPS — d'où la détection dynamique.

    SameSite=Strict est intentionnellement évité : il bloque l'envoi du cookie
    lors des requêtes POST cross-origin (ex: /auth/refresh depuis le frontend
    servi par le LB GCP), ce qui casse silencieusement le refresh flow.
    """
    is_https = request.headers.get("x-forwarded-proto", "http").lower() == "https"

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=15 * 60,  # 15 minutes
        samesite="lax",
        secure=is_https,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        max_age=3600 * 24 * 7,  # 7 jours
        samesite="lax",
        secure=is_https,
    )


@router.get("/stats", response_model=UserStatsResponse)
async def get_user_stats(db: AsyncSession = Depends(get_db)):
    cache_key = "users:stats"
    cached = get_cache(cache_key)
    if cached:
        return UserStatsResponse(**cached)

    total = (await db.execute(select(func.count()).select_from(User))).scalar()
    active = (await db.execute(select(func.count()).select_from(User).filter(User.is_active == True))).scalar()
    inactive = total - active
    
    # Simple prefix stats for the demonstration
    prefixes = {}
    users = (await db.execute(select(User.username))).all()
    for (username,) in users:
        if username:
            p = username[0].upper()
            prefixes[p] = prefixes.get(p, 0) + 1

    result = UserStatsResponse(
        total=total,
        active=active,
        inactive=inactive,
        by_username_prefix=prefixes
    )
    set_cache(cache_key, result.model_dump(), CACHE_TTL)
    return result


def map_user_to_response(user: User) -> dict:
    allowed_ids = []
    if user.allowed_category_ids:
        try:
            allowed_ids = [int(x) for x in user.allowed_category_ids.split(",") if x]
        except (ValueError, TypeError):
            allowed_ids = []
    
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "full_name": user.full_name,
        "is_active": user.is_active,
        "is_anonymous": user.is_anonymous,
        "role": user.role,
        "allowed_category_ids": allowed_ids,
        "picture_url": user.picture_url,
        "unavailability_periods": user.unavailability_periods or [],
        "created_at": user.created_at.isoformat() if user.created_at else None
    }


@router.get("/")
async def list_users(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of records to return"),
    db: AsyncSession = Depends(get_db)
):
    cache_key = f"users:list:{skip}:{limit}"
    cached = get_cache(cache_key)
    if cached:
        return PaginationResponse(**cached)

    total = (await db.execute(select(func.count()).select_from(User))).scalar()
    users = (await db.execute(select(User).offset(skip).limit(limit))).scalars().all()
    result = PaginationResponse(
        items=[map_user_to_response(u) for u in users],
        total=total,
        skip=skip,
        limit=limit
    )
    set_cache(cache_key, result.model_dump(), CACHE_TTL)
    return result


@router.get("/search")
async def search_users(
    query: str = Query(..., min_length=1, description="Search term"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of records to return"),
    db: AsyncSession = Depends(get_db)
):
    cache_key = f"users:search:{query}:{limit}"
    cached = get_cache(cache_key)
    if cached:
        return PaginationResponse(**cached)

    from sqlalchemy import or_
    
    # Search in first_name, last_name, email, full_name, username
    search_filter = or_(
        User.first_name.ilike(f"%{query}%"),
        User.last_name.ilike(f"%{query}%"),
        User.email.ilike(f"%{query}%"),
        User.full_name.ilike(f"%{query}%"),
        User.username.ilike(f"%{query}%")
    )
    
    total = (await db.execute(select(func.count()).select_from(User).filter(search_filter))).scalar()
    users = (await db.execute(select(User).filter(search_filter).limit(limit))).scalars().all()
    
    result = PaginationResponse(
        items=[map_user_to_response(u) for u in users],
        total=total,
        skip=0,
        limit=limit
    )
    set_cache(cache_key, result.model_dump(), CACHE_TTL)
    return result


@router.post("/bulk", response_model=List[UserResponse])
async def get_users_bulk(
    user_ids: List[int],
    db: AsyncSession = Depends(get_db)
):
    if not user_ids:
        return []
    
    users = (await db.execute(select(User).filter(User.id.in_(user_ids)))).scalars().all()
    # Cache shouldn't be too heavy, we'll map them directly
    return [map_user_to_response(u) for u in users]


@router.get("/me")
async def get_me(request: Request, db: AsyncSession = Depends(get_db), payload: dict = Depends(verify_jwt)):
    username: str = payload.get("sub")
    if username is None:
        raise HTTPException(status_code=401, detail="Token invalide")
    
    cache_key = f"users:me:{username}"
    cached = get_cache(cache_key)
    if cached:
        return cached

    user = (await db.execute(select(User).filter(User.username == username))).scalars().first()
    if user is None:
        raise HTTPException(status_code=401, detail="Utilisateur non répertorié ou compte inactif dans l'annuaire Zenika.")
        
    result = map_user_to_response(user)
    
    # Return the token in the response so the frontend can update localStorage
    auth_header = request.headers.get("Authorization")
    token = auth_header.split(" ")[1] if auth_header and " " in auth_header else request.cookies.get("access_token")
    result["access_token"] = token
    
    set_cache(cache_key, result, 300) # Fast 5m UI Poll Burst
    return result


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

    # Include allowed categories as a list of integers in the JWT payload
    allowed_ids = [int(x) for x in user.allowed_category_ids.split(",") if x]
    token_data = {
        "sub": user.username,
        "allowed_category_ids": allowed_ids,
        "role": user.role
    }
    access_token = create_access_token(data=token_data)
    refresh_token = create_refresh_token(data={"sub": user.username})

    _set_auth_cookies(request, response, access_token, refresh_token)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        username=user.username,
        role=user.role
    )

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

    token_data = {
        "sub": user.username,
        "allowed_category_ids": allowed_ids,
        "role": user.role
    }
    new_access = create_access_token(data=token_data)
    new_refresh = create_refresh_token(data={"sub": user.username})

    _set_auth_cookies(request, response, new_access, new_refresh)

    return TokenResponse(
        access_token=new_access,
        token_type="bearer",
        username=user.username,
        role=user.role
    )


@auth_router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return {"message": "Déconnexion réussie"}


from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from src.users.schemas import ServiceAccountLoginRequest

@auth_router.post("/service-account/login", response_model=TokenResponse)
async def service_account_login(req: ServiceAccountLoginRequest, db: AsyncSession = Depends(get_db)):
    try:
        # Verify Identity Token with Google public certificates
        # We don't verify audience strictly here because it could be dynamic from Cloud Run,
        # but in production we should check `audience` matches the users_api URL or Client ID.
        request_obj = google_requests.Request()
        id_info = id_token.verify_oauth2_token(req.id_token, request_obj)

        email = id_info.get("email")
        if not email:
            raise HTTPException(status_code=403, detail="Un email est requis dans l'ID Token")

        # In a real environment, you'd check whether this email belongs to a known internal service account pattern
        if not email.endswith(".iam.gserviceaccount.com"):
             raise HTTPException(status_code=403, detail="Ce token n'appartient pas à un Service Account autorisé")

        # Give it a service account role in our system
        # TTL étendu à 120 min pour les service accounts Pub/Sub :
        # le backoff max de Pub/Sub est ~17 min (somme des 5 retries), et avec DLQ
        # on peut avoir des messages qui attendent encore plus longtemps.
        # Le fix long terme est le token OIDC Google (1h, échangé au moment du traitement).
        sa_token_ttl = int(os.getenv("SA_TOKEN_TTL_MINUTES", "120"))
        access_token = create_access_token(
            data={
                "sub": email,
                "role": "service_account",
                "allowed_category_ids": []
            },
            expires_delta=timedelta(minutes=sa_token_ttl)
        )
        refresh_token = create_refresh_token(data={"sub": email})

        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            username=email,
            role="service_account"
        )
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
        # Create the user
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
        # Link / update the user
        user.picture_url = user_info.get("picture", user.picture_url)
        user.google_id = user_info.get("sub", user.google_id)
        await db.commit()
        await db.refresh(user)
    
    USER_LOGINS_TOTAL.labels(status="success").inc()

    # Generate JWT
    allowed_ids = [int(x) for x in user.allowed_category_ids.split(",") if x] if user.allowed_category_ids else []
    access_token = create_access_token(data={
        "sub": user.username,
        "allowed_category_ids": allowed_ids,
        "role": user.role
    })
    refresh_token = create_refresh_token(data={"sub": user.username})
    
    scheme = request.headers.get("x-forwarded-proto", "http")
    host = request.headers.get("host", "localhost")
    frontend_url = f"{scheme}://{host}/"
    redirect_response = RedirectResponse(frontend_url)

    _set_auth_cookies(request, redirect_response, access_token, refresh_token)

    return redirect_response


@auth_router.get("/health")
async def router_health():
    return {"status": "healthy"}


@auth_router.post("/internal/service-token", response_model=TokenResponse)
async def create_service_token(
    request: Request,
    db: AsyncSession = Depends(get_db),
    token_payload: dict = Depends(verify_jwt)
):
    """Génère un access token de longue durée pour les tâches de fond (bulk reanalyse, etc.).

    Accessible uniquement aux admins. Le TTL est configurable via SERVICE_TOKEN_TTL_MINUTES
    (défaut: 90 min) pour couvrir les traitements batch dépassant la durée standard de 15 min.
    Ce token inclut le même payload que l'appelant (sub, role, allowed_category_ids).
    """
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

    service_token_data = {
        "sub": username,
        "allowed_category_ids": allowed_ids,
        "role": role,
    }
    access_token = create_access_token(data=service_token_data, expires_delta=timedelta(minutes=ttl_minutes))

    _log.info(f"[service-token] Token de service généré pour '{username}' (TTL={ttl_minutes}min)")

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        username=username,
        role=role
    )


@auth_router.post("/suspend/{email}")
async def suspend_user(email: str, db: AsyncSession = Depends(get_db), token_payload: dict = Depends(verify_jwt)):
    result = await db.execute(select(User).where(User.username == email))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur inexistant.")

    user.is_active = False
    
    audit_log = UserAuditLog(
        user_id=user.id,
        admin_username=token_payload.get("sub", "system"),
        action="SUSPEND",
        field_changed="is_active",
        old_value="True",
        new_value="False"
    )
    db.add(audit_log)
    
    await db.commit()

    # Blacklist JWT : invalider immédiatement tous les tokens actifs du compte (F-05)
    # On stocke le username dans un set Redis avec un TTL = durée max d'un access token (15 min)
    # verify_jwt vérifie ce flag avant d'autoriser la requête (voir auth.py)
    from cache import client as redis_client
    BLACKLIST_KEY = f"jwt:blacklist:user:{user.username}"
    redis_client.setex(BLACKLIST_KEY, 15 * 60, "suspended")  # TTL = ACCESS_TOKEN_EXPIRE_MINUTES

    # Purge du cache utilisateur
    delete_cache(f"users:{user.id}")
    delete_cache_pattern("users:me:*")
    delete_cache_pattern("users:list:*")

    return {"status": "suspended", "email": email}

def normalize_for_matching(text: str) -> str:
    if not text:
        return ""
    # Normalize Unicode (NFD decomposes characters into base + accent)
    nfd_form = unicodedata.normalize('NFD', text)
    # Filter out non-spacing marks (accents)
    only_base = "".join([c for c in nfd_form if unicodedata.category(c) != 'Mn'])
    # Lowercase and remove all non-alphanumeric characters (collapses spaces, hyphens, etc.)
    return re.sub(r'[^a-z0-9]', '', only_base.lower())

@router.get("/duplicates", response_model=List[DuplicateCandidate])
async def get_duplicates(request: Request, db: AsyncSession = Depends(get_db), payload: dict = Depends(verify_jwt)):
    if payload.get("role") not in ["admin", "rh"]:
        raise HTTPException(status_code=403, detail="Privilèges requis (Admin ou RH).")

    users = (await db.execute(select(User).filter(User.is_active == True))).scalars().all()
    grouped = {}
    for u in users:
        if u.first_name and u.last_name:
            # We normalize both names to create a robust matching key
            key = (normalize_for_matching(u.first_name), normalize_for_matching(u.last_name))
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(u)
            
    duplicates = []
    for key, group in grouped.items():
        if len(group) > 1:
            duplicates.append(DuplicateCandidate(users=[map_user_to_response(u) for u in group]))
            
    return duplicates

@router.post("/merge")
async def merge_users(req: MergeRequest, request: Request, db: AsyncSession = Depends(get_db), payload: dict = Depends(verify_jwt)):
    if payload.get("role") not in ["admin", "rh"]:
        raise HTTPException(status_code=403, detail="Privilèges requis (Admin ou RH).")

    source = (await db.execute(select(User).filter(User.id == req.source_id))).scalars().first()
    target = (await db.execute(select(User).filter(User.id == req.target_id))).scalars().first()
    if not source or not target:
        raise HTTPException(status_code=404, detail="Utilisateur(s) non trouvé(s)")
        
    # 3. Publish Asynchronous Event via GCP Pub/Sub (Phase 3)
    await publish_user_event("user.merged", {
        "source_id": req.source_id,
        "target_id": req.target_id
    })
            
    source.is_active = False
    source.merged_into_id = req.target_id
    
    audit_log = UserAuditLog(
        user_id=source.id,
        admin_username=payload.get("sub", "system"),
        action="MERGE_DISABLE",
        field_changed="is_active",
        old_value="True",
        new_value="False"
    )
    db.add(audit_log)
    
    await db.commit()
    
    delete_cache_pattern(f"users:{req.source_id}")
    delete_cache_pattern(f"users:{req.target_id}")
    delete_cache_pattern("users:list:*")
    delete_cache_pattern("users:search:*")
    delete_cache_pattern("users:me:*")
    
    return {"message": "Utilisateurs fusionnés avec succès."}


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)):
    cache_key = f"users:{user_id}"
    cached = get_cache(cache_key)
    if cached:
        return UserResponse(**cached)

    user = (await db.execute(select(User).filter(User.id == user_id))).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail=f"Collaborateur #{user_id} introuvable dans la base de données Zenika.")

    result = map_user_to_response(user)
    set_cache(cache_key, result, CACHE_TTL)
    return result


@router.post("/", response_model=UserResponse, status_code=201)
async def create_user(user: UserCreate, db: AsyncSession = Depends(get_db)):
    allowed_ids_str = ",".join(map(str, user.allowed_category_ids))
    
    # Special Requirement: if email is missing, generate {id}@zenika.com
    # Since ID is generated by DB, we create user with a temporary unique email first
    needs_auto_email = not user.email
    if needs_auto_email:
        import uuid
        user.email = f"temp-{uuid.uuid4()}@zenika.com"

    db_user = User(
        username=user.username,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        full_name=user.full_name or f"{user.first_name} {user.last_name}" if user.first_name and user.last_name else user.full_name,
        hashed_password=get_password_hash(user.password),
        allowed_category_ids=allowed_ids_str,
        is_anonymous=user.is_anonymous
    )
    db.add(db_user)
    
    from sqlalchemy.exc import IntegrityError
    try:
        await db.commit()
        await db.refresh(db_user)
    except IntegrityError:
        await db.rollback()
        # En cas de retry (email déjà existant), on met à jour l'utilisateur existant
        existing = (await db.execute(select(User).filter(User.email == user.email))).scalars().first()
        if existing:
            existing.first_name = user.first_name
            existing.last_name = user.last_name
            existing.full_name = user.full_name or (f"{user.first_name} {user.last_name}" if user.first_name and user.last_name else existing.full_name)
            existing.hashed_password = get_password_hash(user.password)
            existing.allowed_category_ids = allowed_ids_str
            existing.is_anonymous = user.is_anonymous
            await db.commit()
            await db.refresh(existing)
            db_user = existing
        else:
            raise

    if needs_auto_email:
        db_user.email = f"{db_user.id}@zenika.com"
        await db.commit()
        await db.refresh(db_user)

    # Special rule: Adding admin@zenika.com also adds sebastien.lavayssiere@zenika.com as admin
    # (sebastien.lavayssiere@zenika.com will connect via Google identity, using dummy pass)
    if db_user.email == "admin@zenika.com":
        seb_check = await db.execute(select(User).filter(User.email == "sebastien.lavayssiere@zenika.com"))
        if not seb_check.scalars().first():
            seb_user = User(
                username="slavayssiere",
                email="sebastien.lavayssiere@zenika.com",
                first_name="Sébastien",
                last_name="Lavayssière",
                full_name="Sébastien Lavayssière",
                hashed_password=db_user.hashed_password,
                role="admin",
                is_active=True
            )
            db.add(seb_user)
            await db.commit()

    delete_cache_pattern("users:list:*")
    delete_cache_pattern("users:search:*")
    delete_cache_pattern("users:me:*")
    USER_CREATIONS_TOTAL.inc()
    return map_user_to_response(db_user)



@router.put("/{user_id}", response_model=UserResponse)
async def update_user(user_id: int, user_update: UserUpdate, db: AsyncSession = Depends(get_db), payload: dict = Depends(verify_jwt)):
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Privilèges administrateur requis pour modifier un utilisateur")

    user = (await db.execute(select(User).filter(User.id == user_id))).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    update_data = user_update.model_dump(exclude_unset=True)
    
    admin_username = payload.get("sub", "system")
    audit_logs = []
    
    for field, value in update_data.items():
        if field == "email" and value is None:
            continue # We don't allow setting email to null
            
        old_val = getattr(user, field, None)
        
        if field == "allowed_category_ids" and value is not None:
            new_val = ",".join(map(str, value))
            setattr(user, field, new_val)
        else:
            new_val = value
            setattr(user, field, new_val)
            
        if field in ["is_active", "role", "seniority"] and str(old_val) != str(new_val):
            audit_logs.append(UserAuditLog(
                user_id=user.id,
                admin_username=admin_username,
                action="UPDATE",
                field_changed=field,
                old_value=str(old_val),
                new_value=str(new_val)
            ))

    if audit_logs:
        db.add_all(audit_logs)

    await db.commit()
    await db.refresh(user)

    delete_cache(f"users:{user_id}")
    delete_cache_pattern("users:list:*")
    delete_cache_pattern("users:search:*")
    delete_cache_pattern("users:me:*")
    return map_user_to_response(user)


@router.delete("/{user_id}", status_code=204)
async def delete_user(user_id: int, db: AsyncSession = Depends(get_db), payload: dict = Depends(verify_jwt)):
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Privilèges administrateur requis pour supprimer un utilisateur")

    user = (await db.execute(select(User).filter(User.id == user_id))).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await db.delete(user)
    await db.commit()

    delete_cache(f"users:{user_id}")
    delete_cache_pattern("users:list:*")
    delete_cache_pattern("users:search:*")
    delete_cache_pattern("users:me:*")


