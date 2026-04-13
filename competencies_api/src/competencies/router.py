import os
import httpx
import logging

logger = logging.getLogger(__name__)
from opentelemetry.propagate import inject
from fastapi import APIRouter, Depends, HTTPException, Query, Response, Request
from sqlalchemy import update, func, desc, asc
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
    PaginationResponse, UserInfo, TreeImportRequest,
    StatsRequest, CompetencyCount, CompetencyStatsResponse
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
        "aliases": c.aliases,
        "parent_id": c.parent_id,
        "created_at": c.created_at,
        "sub_competencies": []
    }


def get_grammatical_variants(name: str) -> List[str]:
    """Generates potential singular/plural variants for a given name."""
    name = name.strip()
    variants = {name.lower()}
    
    # Plural to Singular (basic rules)
    if name.lower().endswith('s'):
        variants.add(name[:-1].lower())
    if name.lower().endswith('es'):
        variants.add(name[:-2].lower())
    if name.lower().endswith('x'):
        variants.add(name[:-1].lower())
        
    # Singular to Plural (common suffixes)
    variants.add(name.lower() + 's')
    variants.add(name.lower() + 'es')
    variants.add(name.lower() + 'x')
    
    return list(variants)


async def check_grammatical_conflict(db: AsyncSession, name: str, exclude_id: Optional[int] = None) -> Optional[Competency]:
    """Checks if any grammatical variant of the name already exists in the database."""
    variants = get_grammatical_variants(name)
    stmt = select(Competency).filter(func.lower(Competency.name).in_(variants))
    if exclude_id:
        stmt = stmt.filter(Competency.id != exclude_id)
    result = (await db.execute(stmt)).scalars().first()
    return result


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


@router.get("/search", response_model=PaginationResponse)
async def search_competencies(
    query: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    cache_key = f"competencies:search:{query}:{limit}"
    cached = get_cache(cache_key)
    if cached:
        return PaginationResponse(**cached)

    from sqlalchemy import or_
    results = (await db.execute(
        select(Competency)
        .filter(
            or_(
                Competency.name.ilike(f"%{query}%"),
                Competency.aliases.ilike(f"%{query}%")
            )
        )
        .limit(limit)
    )).scalars().all()

    response = PaginationResponse(
        items=[serialize_competency(c) for c in results],
        total=len(results),
        skip=0,
        limit=limit
    )
    set_cache(cache_key, response.model_dump(), CACHE_TTL)
    return response


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


@router.get("/{competency_id}/users", response_model=List[int])
async def list_competency_users(competency_id: int, db: AsyncSession = Depends(get_db)):
    cache_key = f"competencies:{competency_id}:users"
    cached = get_cache(cache_key)
    if cached:
        return cached

    # Fetch user ids associated with this competency and all its children
    hierarchy = select(Competency.id).where(Competency.id == competency_id).cte(name='hierarchy', recursive=True)
    comps_alias = select(Competency.id, Competency.parent_id).cte('comps_alias')
    
    # Alternatively a simpler approach since it's an Async API:
    # Build recursive CTE to find all descendant IDs
    from sqlalchemy.orm import aliased
    comp_a = aliased(Competency)
    hierarchy = select(Competency.id).where(Competency.id == competency_id).cte(name='hierarchy', recursive=True)
    hierarchy = hierarchy.union_all(
        select(comp_a.id).where(comp_a.parent_id == hierarchy.c.id)
    )
    
    results = (await db.execute(
        select(user_competency.c.user_id)
        .where(user_competency.c.competency_id.in_(select(hierarchy.c.id)))
    )).all()
    
    user_ids = list(set([r[0] for r in results]))
    set_cache(cache_key, user_ids, CACHE_TTL)
    return user_ids


@router.post("/bulk_tree", status_code=200)
async def bulk_import_tree(
    payload: TreeImportRequest,
    db: AsyncSession = Depends(get_db),
    jwt_payload: dict = Depends(verify_jwt)
):
    if jwt_payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Privilèges administrateur requis.")
        
    # --- RESET CHAINING ---
    await db.execute(update(Competency).values(parent_id=None))
    await db.flush()
    
    touched_ids = set()
        
    async def upsert_level(nodes_dict: dict, parent_id: Optional[int] = None):
        if not isinstance(nodes_dict, dict):
            return
            
        for name, data in nodes_dict.items():
            name = name.strip()
            aliases = data.get("aliases") if isinstance(data, dict) else None
            desc = data.get("description", "Généré par Model IA") if isinstance(data, dict) else "Catégorie"
            
            existing = (await db.execute(select(Competency).filter(Competency.name.ilike(name)))).scalars().first()
            if existing:
                existing.parent_id = parent_id
                if aliases:
                    existing.aliases = aliases
                node_id = existing.id
                touched_ids.add(node_id)
            else:
                is_category = False
                if isinstance(data, dict):
                    sub = data.get("sub") or data.get("sub_competencies")
                    if sub:
                        is_category = True
                
                if is_category:
                    new_comp = Competency(name=name, description=desc, aliases=aliases, parent_id=parent_id)
                    db.add(new_comp)
                    await db.flush()
                    node_id = new_comp.id
                    touched_ids.add(node_id)
                else:
                    # Check for grammatical variant in bulk import - if found, use it instead of skipping
                    conflict = await check_grammatical_conflict(db, name)
                    if conflict:
                        conflict.parent_id = parent_id
                        node_id = conflict.id
                        touched_ids.add(node_id)
                        logger.info(f"Bulk Import: Matched '{name}' with existing variant '{conflict.name}'")
                    else:
                        logger.warning(f"Skipping creation of unknown leaf competency from tree: {name}")
                        continue
            
            if isinstance(data, dict):
                sub = data.get("sub") or data.get("sub_competencies")
                if isinstance(sub, dict):
                    await upsert_level(sub, node_id)
                elif isinstance(sub, list):
                    for item in sub:
                        if isinstance(item, list) and len(item) > 0:
                            sub_name = str(item[0])
                        elif isinstance(item, dict):
                            sub_name = item.get("name", str(item))
                        else:
                            sub_name = str(item)
                        
                        sub_name = sub_name.strip()
                            
                        # Use ilike or grammatical check
                        leaf = (await db.execute(select(Competency).filter(Competency.name.ilike(sub_name)))).scalars().first()
                        if not leaf:
                            leaf = await check_grammatical_conflict(db, sub_name)

                        if leaf:
                            leaf.parent_id = node_id
                            touched_ids.add(leaf.id)
                        else:
                            logger.warning(f"Skipping creation of unknown leaf competency from list: {sub_name}")

    try:
        await upsert_level(payload.tree, None)
        
        # --- ORPHAN HANDLING ---
        # Any root competency that was not touched is moved to Archives
        archive_name = "Compétences Archives / Non classées"
        archives = (await db.execute(select(Competency).filter(Competency.name == archive_name))).scalars().first()
        if not archives:
            archives = Competency(name=archive_name, description="Compétences conservées mais absentes de la dernière taxonomie calculée.")
            db.add(archives)
            await db.flush()
        
        archives_id = archives.id
        touched_ids.add(archives_id)
        
        # Update all roots (parent_id IS NULL) that were NOT touched
        await db.execute(
            update(Competency)
            .where(Competency.parent_id.is_(None))
            .where(Competency.id.not_in(touched_ids))
            .values(parent_id=archives_id)
        )
        
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'import: {str(e)}")
        
    delete_cache_pattern("competencies:*")
    return {"message": "Taxonomie fusionnée avec succès et orphelins archivés !"}


@router.post("/", response_model=CompetencyResponse, status_code=201)
async def create_competency(competency: CompetencyCreate, db: AsyncSession = Depends(get_db)):
    # Force normalization to prevent duplicates
    competency.name = competency.name.strip()
    
    if competency.parent_id is not None:
        parent = (await db.execute(select(Competency).filter(Competency.id == competency.parent_id))).scalars().first()
        if not parent:
            raise HTTPException(status_code=400, detail="Parent competency not found")
            
    # Check for direct existence explicitly to prevent ID drops on race conditions
    # This also checks for plural/singular variants
    conflict = await check_grammatical_conflict(db, competency.name)
    if conflict:
        if conflict.name.lower() == competency.name.lower():
            # Exact match (case insensitive) -> return existing
            return CompetencyResponse(**serialize_competency(conflict))
        else:
            # Grammatical variant (singular/plural) -> Conflict 409 per user request
            raise HTTPException(
                status_code=409, 
                detail=f"Une variante grammaticale de '{competency.name}' existe déjà : '{conflict.name}'."
            )
        
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
        if key == "name" and value is not None:
            value = value.strip()
            if value != db_comp.name:
                # Check if name already exists for another record (grammatical variant check)
                conflict = await check_grammatical_conflict(db, value, exclude_id=competency_id)
                if conflict:
                    raise HTTPException(
                        status_code=409, 
                        detail=f"Une compétence nommée '{value}' ou une variante ('{conflict.name}') existe déjà."
                    )
        setattr(db_comp, key, value)
        
    try:
        await db.commit()
        await db.refresh(db_comp)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Conflit de données : le nom est probablement déjà utilisé.")
    
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


@router.post("/stats/counts", response_model=CompetencyStatsResponse)
async def get_competency_stats(
    req: StatsRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Calcule les statistiques de compétences (comptage par utilisateur).
    Permet de filtrer sur une cohorte d'utilisateurs spécifique.
    """
    # Base query for counting users per competency
    stmt = (
        select(
            Competency.id,
            Competency.name,
            func.count(user_competency.c.user_id).label("count")
        )
        .join(user_competency, Competency.id == user_competency.c.competency_id)
    )
    
    # Filter by user_ids if provided
    if req.user_ids is not None:
        if not req.user_ids:
            return CompetencyStatsResponse(items=[])
        stmt = stmt.where(user_competency.c.user_id.in_(req.user_ids))
    
    # Group by competency
    stmt = stmt.group_by(Competency.id, Competency.name)
    
    # Sorting
    if req.sort_order.lower() == "asc":
        stmt = stmt.order_by(func.count(user_competency.c.user_id).asc())
    else:
        stmt = stmt.order_by(func.count(user_competency.c.user_id).desc())
        
    # Limit
    stmt = stmt.limit(req.limit)
    
    results = (await db.execute(stmt)).all()
    
    items = [
        CompetencyCount(id=r[0], name=r[1], count=r[2])
        for r in results
    ]
    
    return CompetencyStatsResponse(items=items)


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

from pydantic import BaseModel

class UserMergeRequest(BaseModel):
    source_id: int
    target_id: int

@router.post("/internal/users/merge")
async def merge_users(req: UserMergeRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """
    Internal endpoint to merge user data.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing authorization via competencies merge")
        
    # Get source user competencies
    stmt = select(user_competency.c.competency_id).where(user_competency.c.user_id == req.source_id)
    source_comps = (await db.execute(stmt)).scalars().all()
    
    # Get target user competencies
    stmt_t = select(user_competency.c.competency_id).where(user_competency.c.user_id == req.target_id)
    target_comps = (await db.execute(stmt_t)).scalars().all()
    
    new_comps = set(source_comps) - set(target_comps)
    
    if new_comps:
        from datetime import datetime
        for cid in new_comps:
            await db.execute(
                user_competency.insert().values(
                    user_id=req.target_id,
                    competency_id=cid,
                    created_at=datetime.utcnow()
                )
            )
            
    # delete source comps
    await db.execute(user_competency.delete().where(user_competency.c.user_id == req.source_id))
    await db.commit()
    
    delete_cache_pattern(f"competencies:user:{req.source_id}:*")
    delete_cache_pattern(f"competencies:user:{req.target_id}:*")
    
    return {"message": f"Successfully migrated competencies from user {req.source_id} to {req.target_id}"}


@router.delete("/user/{user_id}/clear", status_code=204)
async def clear_user_competencies(
    user_id: int, 
    db: AsyncSession = Depends(get_db),
    jwt_payload: dict = Depends(verify_jwt)
):
    """
    (Admin Only) Supprime toutes les assignations de compétences pour un utilisateur.
    """
    if jwt_payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Privilèges administrateur requis.")
        
    await db.execute(
        user_competency.delete().where(user_competency.c.user_id == user_id)
    )
    await db.commit()
    
    delete_cache_pattern(f"competencies:user:{user_id}:*")
    return Response(status_code=204)
