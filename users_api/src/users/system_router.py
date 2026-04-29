import logging
import re
import unicodedata
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from cache import get_cache, set_cache, delete_cache_pattern
from database import get_db
from src.auth import verify_jwt
from src.users.models import User, UserAuditLog
from src.users.schemas import UserStatsResponse, DuplicateCandidate, MergeRequest
from .pubsub import publish_user_event

_log = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["users_system"], dependencies=[Depends(verify_jwt)])

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
    
    prefixes = {}
    users = (await db.execute(select(User.username))).all()
    for (username,) in users:
        if username:
            p = username[0].upper()
            prefixes[p] = prefixes.get(p, 0) + 1

    result = UserStatsResponse(total=total, active=active, inactive=inactive, by_username_prefix=prefixes)
    set_cache(cache_key, result.model_dump(), CACHE_TTL)
    return result

def normalize_for_matching(text: str) -> str:
    if not text:
        return ""
    nfd_form = unicodedata.normalize('NFD', text)
    only_base = "".join([c for c in nfd_form if unicodedata.category(c) != 'Mn'])
    return re.sub(r'[^a-z0-9]', '', only_base.lower())

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

@router.get("/duplicates", response_model=List[DuplicateCandidate])
async def get_duplicates(request: Request, db: AsyncSession = Depends(get_db), payload: dict = Depends(verify_jwt)):
    if payload.get("role") not in ["admin", "rh"]:
        raise HTTPException(status_code=403, detail="Privilèges requis (Admin ou RH).")

    users = (await db.execute(select(User).filter(User.is_active == True))).scalars().all()
    grouped = {}
    for u in users:
        if u.first_name and u.last_name:
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
        
    await publish_user_event("user.merged", {"source_id": req.source_id, "target_id": req.target_id})
            
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
