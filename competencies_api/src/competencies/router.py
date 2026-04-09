import os
import httpx
from opentelemetry.propagate import inject
from fastapi import APIRouter, Depends, HTTPException, Query, Response, Request
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from datetime import datetime

from database import get_db
from cache import get_cache, set_cache, delete_cache, delete_cache_pattern
from src.competencies.models import Competency, user_competency
from src.competencies.schemas import (
    CompetencyCreate, CompetencyUpdate, CompetencyResponse, 
    PaginationResponse, UserInfo, TreeImportRequest
)

from src.auth import verify_jwt

router = APIRouter(prefix="", tags=["competencies"], dependencies=[Depends(verify_jwt)])

USERS_API_URL = os.getenv("USERS_API_URL", "http://users_api:8000")
CACHE_TTL = 60


def serialize_competency(c: Competency) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "description": c.description,
        "parent_id": c.parent_id,
        "created_at": c.created_at,
        "sub_competencies": []
    }


async def get_user_from_api(user_id: int, request: Request) -> UserInfo:
    """Helper to verify user exists in users_api by propagating the original JWT."""
    auth_header = request.headers.get("Authorization")
    headers = {"Authorization": auth_header} if auth_header else {}
    
    inject(headers)

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{USERS_API_URL.rstrip('/')}/{user_id}", headers=headers)
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
    db: AsyncSession = Depends(get_db)
):
    cache_key = f"competencies:tree:list:{skip}:{limit}"
    cached = get_cache(cache_key)
    if cached:
        return PaginationResponse(**cached)

    # Fetch all competencies to build the tree in memory without lazy-loading issues
    all_comps = (await db.execute(select(Competency))).scalars().all()
    
    nodes = {}
    for c in all_comps:
        nodes[c.id] = {
            "id": c.id,
            "name": c.name,
            "description": c.description,
            "parent_id": c.parent_id,
            "created_at": c.created_at,
            "sub_competencies": []
        }
        
    roots = []
    for c in all_comps:
        if c.parent_id is None:
            roots.append(nodes[c.id])
        else:
            if c.parent_id in nodes:
                nodes[c.parent_id]["sub_competencies"].append(nodes[c.id])
                
    roots.sort(key=lambda x: x["id"])
    total = len(roots)
    paged_roots = roots[skip:skip+limit]
    
    result = PaginationResponse(
        items=paged_roots,
        total=total,
        skip=skip,
        limit=limit
    )
    set_cache(cache_key, result.model_dump(), CACHE_TTL)
    return result


@router.get("/{competency_id}", response_model=CompetencyResponse)
async def get_competency(competency_id: int, db: AsyncSession = Depends(get_db)):
    cache_key = f"competencies:{competency_id}"
    cached = get_cache(cache_key)
    if cached:
        return CompetencyResponse(**cached)

    competency = (await db.execute(select(Competency).filter(Competency.id == competency_id))).scalars().first()
    if not competency:
        raise HTTPException(status_code=404, detail="Competency not found")

    result = CompetencyResponse(**serialize_competency(competency))
    set_cache(cache_key, result.model_dump(), CACHE_TTL)
    return result


@router.post("/bulk_tree", status_code=200)
async def bulk_import_tree(
    payload: TreeImportRequest,
    db: AsyncSession = Depends(get_db),
    jwt_payload: dict = Depends(verify_jwt)
):
    if jwt_payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Privilèges administrateur requis.")
        
    async def upsert_level(nodes_dict: dict, parent_id: Optional[int] = None):
        if not isinstance(nodes_dict, dict):
            return
            
        for name, data in nodes_dict.items():
            desc = data.get("description", "Généré par Model IA") if isinstance(data, dict) else "Catégorie"
            
            existing = (await db.execute(select(Competency).filter(Competency.name.ilike(name)))).scalars().first()
            if existing:
                existing.parent_id = parent_id
                node_id = existing.id
            else:
                new_comp = Competency(name=name, description=desc, parent_id=parent_id)
                db.add(new_comp)
                await db.flush()
                node_id = new_comp.id
            
            if isinstance(data, dict):
                sub = data.get("sub")
                if isinstance(sub, dict):
                    await upsert_level(sub, node_id)
                elif isinstance(sub, list):
                    for item in sub:
                        if isinstance(item, list) and len(item) > 0:
                            sub_name = str(item[0])
                            sub_desc = str(item[1]) if len(item) > 1 else "Compétence"
                        else:
                            sub_name = str(item)
                            sub_desc = "Compétence"
                            
                        leaf = (await db.execute(select(Competency).filter(Competency.name.ilike(sub_name)))).scalars().first()
                        if leaf:
                            leaf.parent_id = node_id
                        else:
                            db.add(Competency(name=sub_name, description=sub_desc, parent_id=node_id))
                            await db.flush()

    try:
        await upsert_level(payload.tree, None)
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
        
    delete_cache_pattern("competencies:*")
    return {"message": "Taxonomie fusionnée avec succès sans corrompre les ids !"}


@router.post("/", response_model=CompetencyResponse, status_code=201)
async def create_competency(competency: CompetencyCreate, db: AsyncSession = Depends(get_db)):
    if competency.parent_id is not None:
        parent = (await db.execute(select(Competency).filter(Competency.id == competency.parent_id))).scalars().first()
        if not parent:
            raise HTTPException(status_code=400, detail="Parent competency not found")
            
    # Check for direct existence explicitly to prevent ID drops on race conditions
    existing = (await db.execute(select(Competency).filter(Competency.name.ilike(competency.name)))).scalars().first()
    if existing:
        return CompetencyResponse(**serialize_competency(existing))
        
    db_comp = Competency(**competency.model_dump())
    db.add(db_comp)
    try:
        await db.commit()
        await db.refresh(db_comp)
    except IntegrityError:
        await db.rollback()
        # Fallback safeguard
        existing = (await db.execute(select(Competency).filter(Competency.name.ilike(competency.name)))).scalars().first()
        if existing:
            return CompetencyResponse(**serialize_competency(existing))
        raise HTTPException(status_code=409, detail="Competency naming conflict unresolved")
    
    delete_cache_pattern("competencies:tree:*")
    return CompetencyResponse(**serialize_competency(db_comp))


@router.put("/{competency_id}", response_model=CompetencyResponse)
async def update_competency(
    competency_id: int, 
    competency_update: CompetencyUpdate, 
    db: AsyncSession = Depends(get_db)
):
    db_comp = (await db.execute(select(Competency).filter(Competency.id == competency_id))).scalars().first()
    if not db_comp:
        raise HTTPException(status_code=404, detail="Competency not found")
        
    # Prevent circular recursion if an ID attempts to parent itself (or logic mapping)
    if hasattr(competency_update, "parent_id") and competency_update.parent_id == competency_id:
        raise HTTPException(status_code=400, detail="A competency cannot be its own parent")
        
    for key, value in competency_update.model_dump(exclude_unset=True).items():
        setattr(db_comp, key, value)
        
    await db.commit()
    await db.refresh(db_comp)
    
    delete_cache(f"competencies:{competency_id}")
    delete_cache_pattern("competencies:tree:*")
    return CompetencyResponse(**serialize_competency(db_comp))


@router.delete("/{competency_id}", status_code=204)
async def delete_competency(competency_id: int, db: AsyncSession = Depends(get_db)):
    db_comp = (await db.execute(select(Competency).filter(Competency.id == competency_id))).scalars().first()
    if not db_comp:
        raise HTTPException(status_code=404, detail="Competency not found")
        
    await db.delete(db_comp)
    await db.commit()
    
    delete_cache(f"competencies:{competency_id}")
    delete_cache_pattern("competencies:tree:*")
    return Response(status_code=204)


# --- User Associations ---

@router.post("/user/{user_id}/assign/{competency_id}", status_code=201)
async def assign_competency_to_user(
    user_id: int, 
    competency_id: int, 
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    await get_user_from_api(user_id, request)
    competency = (await db.execute(select(Competency).filter(Competency.id == competency_id))).scalars().first()
    if not competency:
        raise HTTPException(status_code=404, detail="Competency not found")
        
    # Check if already assigned
    existing = (await db.execute(
        select(user_competency).where(
            user_competency.c.user_id == user_id,
            user_competency.c.competency_id == competency_id
        )
    )).first()
    
    if existing:
        return {"message": "Competency already assigned to user"}
        
    # Assign
    await db.execute(
        user_competency.insert().values(
            user_id=user_id,
            competency_id=competency_id,
            created_at=datetime.utcnow()
        )
    )
    await db.commit()
    
    delete_cache_pattern(f"competencies:user:{user_id}:*")
    return {"message": f"Competency {competency.name} assigned to user {user_id}"}


@router.delete("/user/{user_id}/remove/{competency_id}", status_code=204)
async def remove_competency_from_user(
    user_id: int, 
    competency_id: int, 
    db: AsyncSession = Depends(get_db)
):
    await db.execute(
        user_competency.delete().where(
            user_competency.c.user_id == user_id,
            user_competency.c.competency_id == competency_id
        )
    )
    await db.commit()
    
    delete_cache_pattern(f"competencies:user:{user_id}:*")
    return Response(status_code=204)


@router.get("/user/{user_id}", response_model=List[CompetencyResponse])
async def list_user_competencies(user_id: int, db: AsyncSession = Depends(get_db)):
    cache_key = f"competencies:user:{user_id}:list"
    cached = get_cache(cache_key)
    if cached:
        return [CompetencyResponse(**c) for c in cached]

    # Join competencies with association table
    results = (await db.execute(select(Competency).join(
        user_competency, 
        Competency.id == user_competency.c.competency_id
    ).filter(user_competency.c.user_id == user_id))).scalars().all()
    
    items = [CompetencyResponse(**serialize_competency(c)) for c in results]
    set_cache(cache_key, [i.model_dump() for i in items], CACHE_TTL)
    return items
