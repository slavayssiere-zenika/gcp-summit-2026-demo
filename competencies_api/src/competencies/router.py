import os
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response, Request
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from datetime import datetime

from database import get_db
from cache import get_cache, set_cache, delete_cache, delete_cache_pattern
from src.competencies.models import Competency, user_competency
from src.competencies.schemas import (
    CompetencyCreate, CompetencyUpdate, CompetencyResponse, 
    PaginationResponse, UserInfo
)

from src.auth import verify_jwt

router = APIRouter(prefix="/competencies", tags=["competencies"], dependencies=[Depends(verify_jwt)])

USERS_API_URL = os.getenv("USERS_API_URL", "http://users_api:8000")
CACHE_TTL = 60


async def get_user_from_api(user_id: int, request: Request) -> UserInfo:
    """Helper to verify user exists in users_api by propagating the original JWT."""
    auth_header = request.headers.get("Authorization")
    headers = {"Authorization": auth_header} if auth_header else {}
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{USERS_API_URL}/users/{user_id}", headers=headers)
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail=f"User {user_id} not found")
            response.raise_for_status()
            return UserInfo(**response.json())
        except httpx.HTTPError as e:
            raise HTTPException(status_code=503, detail=f"Users API unavailable: {str(e)}")


@router.get("/", response_model=PaginationResponse)
async def list_competencies(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db)
):
    cache_key = f"competencies:tree:list:{skip}:{limit}"
    cached = get_cache(cache_key)
    if cached:
        return PaginationResponse(**cached)

    # Automatically restrict to Root elements to build a nested JSON tree without endless flat repetitions
    query = db.query(Competency).filter(Competency.parent_id == None)
    total = query.count()
    items = query.offset(skip).limit(limit).all()
    
    result = PaginationResponse(
        items=[CompetencyResponse.model_validate(c) for c in items],
        total=total,
        skip=skip,
        limit=limit
    )
    set_cache(cache_key, result.model_dump(), CACHE_TTL)
    return result


@router.get("/{competency_id}", response_model=CompetencyResponse)
async def get_competency(competency_id: int, db: Session = Depends(get_db)):
    cache_key = f"competencies:{competency_id}"
    cached = get_cache(cache_key)
    if cached:
        return CompetencyResponse(**cached)

    competency = db.query(Competency).filter(Competency.id == competency_id).first()
    if not competency:
        raise HTTPException(status_code=404, detail="Competency not found")

    result = CompetencyResponse.model_validate(competency)
    set_cache(cache_key, result.model_dump(), CACHE_TTL)
    return result


@router.post("/", response_model=CompetencyResponse, status_code=201)
async def create_competency(competency: CompetencyCreate, db: Session = Depends(get_db)):
    if competency.parent_id is not None:
        parent = db.query(Competency).filter(Competency.id == competency.parent_id).first()
        if not parent:
            raise HTTPException(status_code=400, detail="Parent competency not found")
            
    # Check for direct existence explicitly to prevent ID drops on race conditions
    existing = db.query(Competency).filter(Competency.name.ilike(competency.name)).first()
    if existing:
        return CompetencyResponse.model_validate(existing)
        
    db_comp = Competency(**competency.model_dump())
    db.add(db_comp)
    try:
        db.commit()
        db.refresh(db_comp)
    except IntegrityError:
        db.rollback()
        # Fallback safeguard
        existing = db.query(Competency).filter(Competency.name.ilike(competency.name)).first()
        if existing:
            return CompetencyResponse.model_validate(existing)
        raise HTTPException(status_code=409, detail="Competency naming conflict unresolved")
    
    delete_cache_pattern("competencies:list:*")
    return CompetencyResponse.model_validate(db_comp)


@router.put("/{competency_id}", response_model=CompetencyResponse)
async def update_competency(
    competency_id: int, 
    competency_update: CompetencyUpdate, 
    db: Session = Depends(get_db)
):
    db_comp = db.query(Competency).filter(Competency.id == competency_id).first()
    if not db_comp:
        raise HTTPException(status_code=404, detail="Competency not found")
        
    # Prevent circular recursion if an ID attempts to parent itself (or logic mapping)
    if hasattr(competency_update, "parent_id") and competency_update.parent_id == competency_id:
        raise HTTPException(status_code=400, detail="A competency cannot be its own parent")
        
    for key, value in competency_update.model_dump(exclude_unset=True).items():
        setattr(db_comp, key, value)
        
    db.commit()
    db.refresh(db_comp)
    
    delete_cache(f"competencies:{competency_id}")
    delete_cache_pattern("competencies:tree:*")
    return CompetencyResponse.model_validate(db_comp)


@router.delete("/{competency_id}", status_code=204)
async def delete_competency(competency_id: int, db: Session = Depends(get_db)):
    db_comp = db.query(Competency).filter(Competency.id == competency_id).first()
    if not db_comp:
        raise HTTPException(status_code=404, detail="Competency not found")
        
    db.delete(db_comp)
    db.commit()
    
    delete_cache(f"competencies:{competency_id}")
    delete_cache_pattern("competencies:list:*")
    return Response(status_code=204)


# --- User Associations ---

@router.post("/user/{user_id}/assign/{competency_id}", status_code=201)
async def assign_competency_to_user(
    user_id: int, 
    competency_id: int, 
    request: Request,
    db: Session = Depends(get_db)
):
    await get_user_from_api(user_id, request)
    competency = db.query(Competency).filter(Competency.id == competency_id).first()
    if not competency:
        raise HTTPException(status_code=404, detail="Competency not found")
        
    # Check if already assigned
    existing = db.execute(
        user_competency.select().where(
            user_competency.c.user_id == user_id,
            user_competency.c.competency_id == competency_id
        )
    ).first()
    
    if existing:
        return {"message": "Competency already assigned to user"}
        
    # Assign
    db.execute(
        user_competency.insert().values(
            user_id=user_id,
            competency_id=competency_id,
            created_at=datetime.utcnow()
        )
    )
    db.commit()
    
    delete_cache_pattern(f"competencies:user:{user_id}:*")
    return {"message": f"Competency {competency.name} assigned to user {user_id}"}


@router.delete("/user/{user_id}/remove/{competency_id}", status_code=204)
async def remove_competency_from_user(
    user_id: int, 
    competency_id: int, 
    db: Session = Depends(get_db)
):
    db.execute(
        user_competency.delete().where(
            user_competency.c.user_id == user_id,
            user_competency.c.competency_id == competency_id
        )
    )
    db.commit()
    
    delete_cache_pattern(f"competencies:user:{user_id}:*")
    return Response(status_code=204)


@router.get("/user/{user_id}", response_model=List[CompetencyResponse])
async def list_user_competencies(user_id: int, db: Session = Depends(get_db)):
    cache_key = f"competencies:user:{user_id}:list"
    cached = get_cache(cache_key)
    if cached:
        return [CompetencyResponse(**c) for c in cached]

    # Join competencies with association table
    results = db.query(Competency).join(
        user_competency, 
        Competency.id == user_competency.c.competency_id
    ).filter(user_competency.c.user_id == user_id).all()
    
    items = [CompetencyResponse.model_validate(c) for c in results]
    set_cache(cache_key, [i.model_dump() for i in items], CACHE_TTL)
    return items
