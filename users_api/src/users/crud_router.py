import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from cache import get_cache, set_cache, delete_cache, delete_cache_pattern
from database import get_db
from metrics import USER_CREATIONS_TOTAL
from src.auth import verify_jwt, get_password_hash
from src.users.models import User, UserAuditLog
from src.users.schemas import UserCreate, UserUpdate, UserResponse, PaginationResponse

_log = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["users_crud"], dependencies=[Depends(verify_jwt)])

CACHE_TTL = 60

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
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    is_anonymous: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_jwt),
):
    caller_role = payload.get("role", "user")
    cache_key = f"users:list:{skip}:{limit}:{str(is_anonymous).lower()}"
    cached = get_cache(cache_key)
    if cached:
        return PaginationResponse(**cached)

    base_query = select(User)
    count_query = select(func.count()).select_from(User)
    
    if is_anonymous is not None:
        base_query = base_query.filter(User.is_anonymous == is_anonymous)
        count_query = count_query.filter(User.is_anonymous == is_anonymous)

    total = (await db.execute(count_query)).scalar()
    users = (await db.execute(base_query.offset(skip).limit(limit))).scalars().all()
    
    items = [map_user_to_response(u) for u in users]
    if caller_role not in ("admin", "rh", "service_account"):
        for item in items:
            item["email"] = None

    result = PaginationResponse(items=items, total=total, skip=skip, limit=limit)
    set_cache(cache_key, result.model_dump(), CACHE_TTL)
    return result

@router.get("/search")
async def search_users(
    query: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    cache_key = f"users:search:{query}:{limit}"
    cached = get_cache(cache_key)
    if cached:
        return PaginationResponse(**cached)

    search_filter = or_(
        User.first_name.ilike(f"%{query}%"),
        User.last_name.ilike(f"%{query}%"),
        User.email.ilike(f"%{query}%"),
        User.full_name.ilike(f"%{query}%"),
        User.username.ilike(f"%{query}%")
    )
    
    total = (await db.execute(select(func.count()).select_from(User).filter(search_filter))).scalar()
    users = (await db.execute(select(User).filter(search_filter).limit(limit))).scalars().all()
    
    result = PaginationResponse(items=[map_user_to_response(u) for u in users], total=total, skip=0, limit=limit)
    set_cache(cache_key, result.model_dump(), CACHE_TTL)
    return result

@router.post("/bulk", response_model=List[UserResponse])
async def get_users_bulk(user_ids: List[int], db: AsyncSession = Depends(get_db)):
    if not user_ids:
        return []
    users = (await db.execute(select(User).filter(User.id.in_(user_ids)))).scalars().all()
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
    
    auth_header = request.headers.get("Authorization")
    token = auth_header.split(" ")[1] if auth_header and " " in auth_header else request.cookies.get("access_token")
    result["access_token"] = token
    
    set_cache(cache_key, result, 300)
    return result

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)):
    cache_key = f"users:{user_id}"
    cached = get_cache(cache_key)
    if cached:
        return UserResponse(**cached)

    user = (await db.execute(select(User).filter(User.id == user_id))).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail=f"Collaborateur #{user_id} introuvable.")

    result = map_user_to_response(user)
    set_cache(cache_key, result, CACHE_TTL)
    return result

@router.post("/", response_model=UserResponse, status_code=201)
async def create_user(user: UserCreate, db: AsyncSession = Depends(get_db), payload: dict = Depends(verify_jwt)):
    if payload.get("role") not in ("admin", "service_account"):
        raise HTTPException(status_code=403, detail="Privilèges administrateur requis.")
    
    allowed_ids_str = ",".join(map(str, user.allowed_category_ids))
    needs_auto_email = not user.email
    if needs_auto_email:
        import uuid
        user.email = f"temp-{uuid.uuid4()}@zenika.com"

    db_user = User(
        username=user.username, email=user.email, first_name=user.first_name, last_name=user.last_name,
        full_name=user.full_name or f"{user.first_name} {user.last_name}" if user.first_name and user.last_name else user.full_name,
        hashed_password=get_password_hash(user.password), allowed_category_ids=allowed_ids_str, is_anonymous=user.is_anonymous
    )
    db.add(db_user)
    
    from sqlalchemy.exc import IntegrityError
    try:
        await db.commit()
        await db.refresh(db_user)
    except IntegrityError:
        await db.rollback()
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

    if db_user.email == "admin@zenika.com":
        seb_check = await db.execute(select(User).filter(User.email == "sebastien.lavayssiere@zenika.com"))
        if not seb_check.scalars().first():
            seb_user = User(
                username="slavayssiere", email="sebastien.lavayssiere@zenika.com",
                first_name="Sébastien", last_name="Lavayssière", full_name="Sébastien Lavayssière",
                hashed_password=db_user.hashed_password, role="admin", is_active=True
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
        raise HTTPException(status_code=403, detail="Privilèges administrateur requis.")

    user = (await db.execute(select(User).filter(User.id == user_id))).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    update_data = user_update.model_dump(exclude_unset=True)
    admin_username = payload.get("sub", "system")
    audit_logs = []
    
    for field, value in update_data.items():
        if field == "email" and value is None:
            continue
            
        old_val = getattr(user, field, None)
        if field == "allowed_category_ids" and value is not None:
            new_val = ",".join(map(str, value))
            setattr(user, field, new_val)
        else:
            new_val = value
            setattr(user, field, new_val)
            
        if field in ["is_active", "role", "seniority"] and str(old_val) != str(new_val):
            audit_logs.append(UserAuditLog(
                user_id=user.id, admin_username=admin_username, action="UPDATE",
                field_changed=field, old_value=str(old_val), new_value=str(new_val)
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
        raise HTTPException(status_code=403, detail="Privilèges administrateur requis.")

    user = (await db.execute(select(User).filter(User.id == user_id))).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await db.delete(user)
    await db.commit()

    delete_cache(f"users:{user_id}")
    delete_cache_pattern("users:list:*")
    delete_cache_pattern("users:search:*")
    delete_cache_pattern("users:me:*")
