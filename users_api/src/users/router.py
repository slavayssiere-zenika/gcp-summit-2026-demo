from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from cache import get_cache, set_cache, delete_cache, delete_cache_pattern
from src.users.models import User
from src.users.schemas import UserCreate, UserUpdate, UserResponse, PaginationResponse, UserStatsResponse, LoginRequest, TokenResponse
from src.auth import get_password_hash, verify_password, create_access_token, SECRET_KEY, ALGORITHM, verify_jwt
from jose import jwt, JWTError
from fastapi import Response

router = APIRouter(prefix="/users", tags=["users"])

CACHE_TTL = 60


@router.get("/stats", response_model=UserStatsResponse, dependencies=[Depends(verify_jwt)])
async def get_user_stats(db: Session = Depends(get_db)):
    cache_key = "users:stats"
    cached = get_cache(cache_key)
    if cached:
        return UserStatsResponse(**cached)

    total = db.query(User).count()
    active = db.query(User).filter(User.is_active == True).count()
    inactive = total - active
    
    # Simple prefix stats for the demonstration
    prefixes = {}
    users = db.query(User.username).all()
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
        "created_at": user.created_at.isoformat() if user.created_at else None
    }


@router.get("/", dependencies=[Depends(verify_jwt)])
async def list_users(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of records to return"),
    db: Session = Depends(get_db)
):
    cache_key = f"users:list:{skip}:{limit}"
    cached = get_cache(cache_key)
    if cached:
        return PaginationResponse(**cached)

    total = db.query(User).count()
    users = db.query(User).offset(skip).limit(limit).all()
    result = PaginationResponse(
        items=[map_user_to_response(u) for u in users],
        total=total,
        skip=skip,
        limit=limit
    )
    set_cache(cache_key, result.model_dump(), CACHE_TTL)
    return result


@router.get("/search", dependencies=[Depends(verify_jwt)])
async def search_users(
    query: str = Query(..., min_length=1, description="Search term"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of records to return"),
    db: Session = Depends(get_db)
):
    from sqlalchemy import or_
    
    # Search in first_name, last_name, email, full_name, username
    search_filter = or_(
        User.first_name.ilike(f"%{query}%"),
        User.last_name.ilike(f"%{query}%"),
        User.email.ilike(f"%{query}%"),
        User.full_name.ilike(f"%{query}%"),
        User.username.ilike(f"%{query}%")
    )
    
    total = db.query(User).filter(search_filter).count()
    users = db.query(User).filter(search_filter).limit(limit).all()
    
    return PaginationResponse(
        items=[map_user_to_response(u) for u in users],
        total=total,
        skip=0,
        limit=limit
    )


@router.get("/me", dependencies=[Depends(verify_jwt)])
async def get_me(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Non authentifié")
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Token invalide")
        
        user = db.query(User).filter(User.username == username).first()
        if user is None:
            raise HTTPException(status_code=401, detail="Utilisateur non trouvé")
            
        return map_user_to_response(user)
    except JWTError:
        raise HTTPException(status_code=401, detail="Token invalide")


@router.post("/login", response_model=TokenResponse)
async def login(login_data: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == login_data.email).first()
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


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token")
    return {"message": "Déconnexion réussie"}


@router.get("/health")
async def router_health():
    return {"status": "healthy"}


@router.get("/{user_id}", response_model=UserResponse, dependencies=[Depends(verify_jwt)])
def get_user(user_id: int, db: Session = Depends(get_db)):
    cache_key = f"users:{user_id}"
    cached = get_cache(cache_key)
    if cached:
        return UserResponse(**cached)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    result = map_user_to_response(user)
    set_cache(cache_key, result, CACHE_TTL)
    return result


@router.post("/", response_model=UserResponse, status_code=201, dependencies=[Depends(verify_jwt)])
def create_user(user: UserCreate, db: Session = Depends(get_db)):
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
    db.commit()
    db.refresh(db_user)

    delete_cache_pattern("users:list:*")
    return map_user_to_response(db_user)



@router.put("/{user_id}", response_model=UserResponse, dependencies=[Depends(verify_jwt)])
def update_user(user_id: int, user_update: UserUpdate, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    update_data = user_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "allowed_category_ids" and value is not None:
            setattr(user, field, ",".join(map(str, value)))
        else:
            setattr(user, field, value)

    db.commit()
    db.refresh(user)

    delete_cache(f"users:{user_id}")
    delete_cache_pattern("users:list:*")
    return map_user_to_response(user)


@router.delete("/{user_id}", status_code=204, dependencies=[Depends(verify_jwt)])
def delete_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    db.delete(user)
    db.commit()

    delete_cache(f"users:{user_id}")
    delete_cache_pattern("users:list:*")
