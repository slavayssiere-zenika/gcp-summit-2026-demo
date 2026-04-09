from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from typing import List

from database import get_db
from cache import get_cache, set_cache, delete_cache, delete_cache_pattern
from src.users.models import User
from src.users.schemas import UserCreate, UserUpdate, UserResponse, PaginationResponse, UserStatsResponse, LoginRequest, TokenResponse
from src.auth import get_password_hash, verify_password, create_access_token, SECRET_KEY, ALGORITHM, verify_jwt
from jose import jwt, JWTError
from fastapi import Response

router = APIRouter(prefix="", tags=["users"], dependencies=[Depends(verify_jwt)])
auth_router = APIRouter(prefix="", tags=["auth"])

CACHE_TTL = 60


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
        "role": user.role,
        "allowed_category_ids": allowed_ids,
        "picture_url": user.picture_url,
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


@router.get("/me")
async def get_me(request: Request, db: AsyncSession = Depends(get_db)):
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Non authentifié")
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Token invalide")
        
        cache_key = f"users:me:{username}"
        cached = get_cache(cache_key)
        if cached:
            return cached

        user = (await db.execute(select(User).filter(User.username == username))).scalars().first()
        if user is None:
            raise HTTPException(status_code=401, detail="Utilisateur non trouvé")
            
        result = map_user_to_response(user)
        result["access_token"] = token
        
        set_cache(cache_key, result, 300) # Fast 5m UI Poll Burst
        return result
    except JWTError:
        raise HTTPException(status_code=401, detail="Token invalide")


@auth_router.post("/login", response_model=TokenResponse)
async def login(login_data: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).filter(User.email == login_data.email))).scalars().first()
    if not user or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Identifiants invalides")
    
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Compte inactif")

    # Include allowed categories as a list of integers in the JWT payload
    allowed_ids = [int(x) for x in user.allowed_category_ids.split(",") if x]
    access_token = create_access_token(data={
        "sub": user.username,
        "allowed_category_ids": allowed_ids,
        "role": user.role
    })
    
    # Set HTTP-Only cookie for the token
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=3600 * 24, # 24h
        samesite="lax",
        secure=False # Set to True in production with HTTPS
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        username=user.username,
        role=user.role
    )


@auth_router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token")
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
        access_token = create_access_token(data={
            "sub": email,
            "role": "service_account",
            "allowed_category_ids": []
        })

        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            username=email,
            role="service_account"
        )
    except ValueError as e:
        raise HTTPException(status_code=401, detail=f"Token invalide: {e}")



import os
import requests
from urllib.parse import urlencode
from fastapi.responses import RedirectResponse
import string
import secrets as pysecrets

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
    else:
        # Link / update the user
        user.picture_url = user_info.get("picture", user.picture_url)
        user.google_id = user_info.get("sub", user.google_id)
        await db.commit()
        await db.refresh(user)

    # Generate JWT
    allowed_ids = [int(x) for x in user.allowed_category_ids.split(",") if x] if user.allowed_category_ids else []
    access_token = create_access_token(data={
        "sub": user.username,
        "allowed_category_ids": allowed_ids,
        "role": user.role
    })
    
    frontend_url = os.getenv("FRONTEND_URL", "/")
    redirect_response = RedirectResponse(frontend_url)
    
    redirect_response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=3600 * 24, # 24h
        samesite="lax",
        secure=False # Set to True in production with HTTPS
    )
    
    return redirect_response


@auth_router.get("/health")
async def router_health():
    return {"status": "healthy"}


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)):
    cache_key = f"users:{user_id}"
    cached = get_cache(cache_key)
    if cached:
        return UserResponse(**cached)

    user = (await db.execute(select(User).filter(User.id == user_id))).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    result = map_user_to_response(user)
    set_cache(cache_key, result, CACHE_TTL)
    return result


@router.post("/", response_model=UserResponse, status_code=201)
async def create_user(user: UserCreate, db: AsyncSession = Depends(get_db)):
    allowed_ids_str = ",".join(map(str, user.allowed_category_ids))
    db_user = User(
        username=user.username,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        full_name=user.full_name or f"{user.first_name} {user.last_name}" if user.first_name and user.last_name else user.full_name,
        hashed_password=get_password_hash(user.password),
        allowed_category_ids=allowed_ids_str
    )
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)

    delete_cache_pattern("users:list:*")
    delete_cache_pattern("users:search:*")
    delete_cache_pattern("users:me:*")
    return map_user_to_response(db_user)



@router.put("/{user_id}", response_model=UserResponse)
async def update_user(user_id: int, user_update: UserUpdate, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).filter(User.id == user_id))).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    update_data = user_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "allowed_category_ids" and value is not None:
            setattr(user, field, ",".join(map(str, value)))
        else:
            setattr(user, field, value)

    await db.commit()
    await db.refresh(user)

    delete_cache(f"users:{user_id}")
    delete_cache_pattern("users:list:*")
    delete_cache_pattern("users:search:*")
    delete_cache_pattern("users:me:*")
    return map_user_to_response(user)


@router.delete("/{user_id}", status_code=204)
async def delete_user(user_id: int, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).filter(User.id == user_id))).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await db.delete(user)
    await db.commit()

    delete_cache(f"users:{user_id}")
    delete_cache_pattern("users:list:*")
    delete_cache_pattern("users:search:*")
    delete_cache_pattern("users:me:*")
