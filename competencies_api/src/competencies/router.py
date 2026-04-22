import json
import os
import httpx
import logging

logger = logging.getLogger(__name__)
from opentelemetry.propagate import inject
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, Request
from sqlalchemy import update, func, desc, asc
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from datetime import datetime
from google import genai
from google.genai import types

import database
from database import get_db
from cache import get_cache, set_cache, delete_cache, delete_cache_pattern
from src.competencies.models import Competency, user_competency, CompetencyEvaluation, CompetencySuggestion
from src.competencies.schemas import (
    CompetencyCreate, CompetencyUpdate, CompetencyResponse,
    PaginationResponse, UserInfo, TreeImportRequest,
    StatsRequest, CompetencyCount, CompetencyStatsResponse,
    CompetencyEvaluationResponse, UserScoreRequest, AiScoreAllResponse,
    AgencyCompetencyItem, AgencyCompetencyCoverage,
    SkillGapItem, SkillGapResult,
    SimilarConsultant, SimilarConsultantsResult,
    CompetencySuggestionCreate, CompetencySuggestionResponse, SuggestionReviewRequest,
)

from src.auth import verify_jwt

router = APIRouter(prefix="", tags=["competencies"], dependencies=[Depends(verify_jwt)])

USERS_API_URL = os.getenv("USERS_API_URL", "http://users_api:8000")
CV_API_URL = os.getenv("CV_API_URL", "http://cv_api:8000")
CV_API_URL = os.getenv("CV_API_URL", "http://cv_api:8000")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
CACHE_TTL = 60

async def _generate_aliases_for_competency(name: str) -> str | None:
    """Génère 3-5 alias pour une compétence via Gemini Flash."""
    try:
        client = genai.Client()
        prompt = (
            f"Tu es un expert technique. Génère 3 à 5 aliases très courts (abréviations, "
            f"variantes de nommage) pour la technologie suivante : '{name}'.\n"
            f"Exemple pour 'Kubernetes' : 'K8s, kube, k8s, Kube, kubernetes'.\n"
            f"Retourne UNIQUEMENT une liste séparée par des virgules, sans aucun texte additionnel."
        )
        res = await client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        if res.text:
            aliases = res.text.strip().strip("'").strip('"')
            logger.info(f"Alias générés pour '{name}' : {aliases}")
            return aliases
    except Exception as e:
        logger.warning(f"Échec de génération d'alias pour '{name}': {e}")
    return None

def trigger_taxonomy_cache_invalidation(bg_tasks: BackgroundTasks):
    """Déclenche de manière asynchrone l'invalidation du cache de la taxonomie dans cv_api."""
    async def invalidate():
        try:
            async with httpx.AsyncClient() as http_client:
                await http_client.post(f"{CV_API_URL.rstrip('/')}/cache/invalidate-taxonomy", timeout=3.0)
                logger.info("[Cache Sync] Ordre d'invalidation de la taxonomie envoyé à cv_api.")
        except Exception as e:
            logger.warning(f"[Cache Sync] Échec d'invalidation de cv_api: {e}")
    bg_tasks.add_task(invalidate)



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
        
    async def upsert_level(nodes_dict, parent_id: Optional[int] = None):
        if isinstance(nodes_dict, list):
            for item in nodes_dict:
                if isinstance(item, dict):
                    name = item.get("name")
                    if name:
                        await upsert_level({name: item}, parent_id)
                    else:
                        await upsert_level(item, parent_id)
            return

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
async def create_competency(competency: CompetencyCreate, bg_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
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
            
    # Auto-génération d'alias
    if not competency.aliases:
        gen_aliases = await _generate_aliases_for_competency(competency.name)
        if gen_aliases:
            competency.aliases = gen_aliases

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


# ============================================================
# Competency Evaluations
# ============================================================

async def _get_or_create_evaluation(
    db: AsyncSession, user_id: int, competency_id: int
) -> CompetencyEvaluation:
    """Retourne l'evaluation existante ou en cree une vide."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    stmt = select(CompetencyEvaluation).where(
        CompetencyEvaluation.user_id == user_id,
        CompetencyEvaluation.competency_id == competency_id
    )
    ev = (await db.execute(stmt)).scalars().first()
    if not ev:
        ev = CompetencyEvaluation(user_id=user_id, competency_id=competency_id)
        db.add(ev)
        await db.flush()
    return ev


def _serialize_evaluation(ev: CompetencyEvaluation, competency_name: str = "") -> dict:
    """Serialise une evaluation en dict.

    Le parametre competency_name DOIT etre fourni explicitement depuis la requete
    (via JOIN ou chargement eager) — ne jamais acceder a ev.competency.name ici
    car cela declencherait un lazy load synchrone incompatible avec AsyncSession
    (sqlalchemy.exc.MissingGreenlet).
    """
    return {
        "id": ev.id,
        "user_id": ev.user_id,
        "competency_id": ev.competency_id,
        "competency_name": competency_name,
        "ai_score": ev.ai_score,
        "ai_justification": ev.ai_justification,
        "ai_scored_at": ev.ai_scored_at,
        "user_score": ev.user_score,
        "user_comment": ev.user_comment,
        "user_scored_at": ev.user_scored_at,
    }


@router.get("/evaluations/user/{user_id}", response_model=List[CompetencyEvaluationResponse])
async def list_user_evaluations(
    user_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Liste toutes les evaluations (feuilles uniquement) pour un utilisateur."""
    # Feuilles uniquement : competences sans enfants
    leaf_ids_stmt = (
        select(user_competency.c.competency_id)
        .where(user_competency.c.user_id == user_id)
        .where(
            ~select(Competency.id)
            .where(Competency.parent_id == user_competency.c.competency_id)
            .correlate(user_competency)
            .exists()
        )
    )
    leaf_ids = (await db.execute(leaf_ids_stmt)).scalars().all()

    if not leaf_ids:
        return []

    # JOIN explicite sur Competency pour eviter le lazy load (MissingGreenlet en AsyncSession)
    stmt = (
        select(CompetencyEvaluation, Competency.name.label("comp_name"))
        .join(Competency, CompetencyEvaluation.competency_id == Competency.id)
        .where(
            CompetencyEvaluation.user_id == user_id,
            CompetencyEvaluation.competency_id.in_(leaf_ids)
        )
    )
    rows = (await db.execute(stmt)).all()
    evaluations = [(row[0], row[1]) for row in rows]  # (CompetencyEvaluation, comp_name)

    # Aussi retourner les feuilles sans evaluation (score null)
    evaluated_ids = {ev.competency_id for ev, _ in evaluations}
    missing_ids = [cid for cid in leaf_ids if cid not in evaluated_ids]

    result = [_serialize_evaluation(ev, comp_name) for ev, comp_name in evaluations]

    if missing_ids:
        comps = (await db.execute(
            select(Competency).where(Competency.id.in_(missing_ids))
        )).scalars().all()
        for c in comps:
            result.append({
                "id": 0,
                "user_id": user_id,
                "competency_id": c.id,
                "competency_name": c.name,
                "ai_score": None,
                "ai_justification": None,
                "ai_scored_at": None,
                "user_score": None,
                "user_comment": None,
                "user_scored_at": None,
            })

    return result


@router.get(
    "/evaluations/user/{user_id}/competency/{competency_id}",
    response_model=CompetencyEvaluationResponse
)
async def get_user_competency_evaluation(
    user_id: int,
    competency_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Evaluation d'une competence specifique pour un utilisateur."""
    comp = (await db.execute(
        select(Competency).where(Competency.id == competency_id)
    )).scalars().first()
    if not comp:
        raise HTTPException(status_code=404, detail="Competency not found")

    stmt = select(CompetencyEvaluation).where(
        CompetencyEvaluation.user_id == user_id,
        CompetencyEvaluation.competency_id == competency_id
    )
    ev = (await db.execute(stmt)).scalars().first()
    if not ev:
        return CompetencyEvaluationResponse(
            id=0, user_id=user_id, competency_id=competency_id,
            competency_name=comp.name
        )
    return CompetencyEvaluationResponse(**_serialize_evaluation(ev, comp.name))


@router.post(
    "/evaluations/user/{user_id}/competency/{competency_id}/user-score",
    response_model=CompetencyEvaluationResponse
)
async def set_user_competency_score(
    user_id: int,
    competency_id: int,
    body: UserScoreRequest,
    db: AsyncSession = Depends(get_db)
):
    """Saisie de la note manuelle du consultant pour une competence."""
    comp = (await db.execute(
        select(Competency).where(Competency.id == competency_id)
    )).scalars().first()
    if not comp:
        raise HTTPException(status_code=404, detail="Competency not found")

    ev = await _get_or_create_evaluation(db, user_id, competency_id)
    ev.user_score = body.score
    ev.user_comment = body.comment
    ev.user_scored_at = datetime.utcnow()
    ev.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(ev)

    delete_cache_pattern(f"competencies:evaluations:user:{user_id}:*")
    return CompetencyEvaluationResponse(**_serialize_evaluation(ev, comp.name))


@router.post(
    "/evaluations/user/{user_id}/competency/{competency_id}/ai-score",
    response_model=CompetencyEvaluationResponse
)
async def trigger_ai_score_single(
    user_id: int,
    competency_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Declenche le calcul IA pour une competence specifique."""
    comp = (await db.execute(
        select(Competency).where(Competency.id == competency_id)
    )).scalars().first()
    if not comp:
        raise HTTPException(status_code=404, detail="Competency not found")

    auth_header = request.headers.get("Authorization", "")
    headers = {"Authorization": auth_header}
    inject(headers)

    score, justification = await _compute_ai_score(user_id, comp.name, headers)

    ev = await _get_or_create_evaluation(db, user_id, competency_id)
    ev.ai_score = score
    ev.ai_justification = justification
    ev.ai_scored_at = datetime.utcnow()
    ev.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(ev)

    delete_cache_pattern(f"competencies:evaluations:user:{user_id}:*")
    return CompetencyEvaluationResponse(**_serialize_evaluation(ev, comp.name))


@router.post(
    "/evaluations/user/{user_id}/ai-score-all",
    response_model=AiScoreAllResponse
)
async def trigger_ai_score_all(
    user_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Declenche le calcul IA pour toutes les competences feuilles d'un utilisateur (BackgroundTask).

    Conformément à la règle absolue AGENTS.md §4 : on obtient un service token à longue
    durée de vie via /auth/internal/service-token AVANT de lancer la tâche. Cela garantit
    que le token ne expire pas en cours de traitement et que l'identité du service
    (et non du compte admin) est tracée dans les logs FinOps.
    """
    auth_header = request.headers.get("Authorization", "")

    # Feuilles uniquement
    leaf_ids_stmt = (
        select(user_competency.c.competency_id)
        .where(user_competency.c.user_id == user_id)
        .where(
            ~select(Competency.id)
            .where(Competency.parent_id == user_competency.c.competency_id)
            .correlate(user_competency)
            .exists()
        )
    )
    leaf_ids = (await db.execute(leaf_ids_stmt)).scalars().all()

    comps_raw = (await db.execute(
        select(Competency.id, Competency.name).where(Competency.id.in_(leaf_ids))
    )).all()
    # Sérialisation en tuples simples (id, name) pour éviter les erreurs cross-session SQLAlchemy
    comp_tuples = [(row[0], row[1]) for row in comps_raw]

    # RÈGLE ABSOLUE AGENTS.md §4 : obtenir un service token avant la background task.
    # Ne jamais passer le bearer utilisateur directement — il peut expirer en mid-flight.
    bg_auth_header = auth_header
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            svc_res = await client.post(
                f"{USERS_API_URL.rstrip('/')}/auth/internal/service-token",
                headers={"Authorization": auth_header},
            )
            if svc_res.status_code == 200:
                service_token = svc_res.json().get("access_token")
                if service_token:
                    bg_auth_header = f"Bearer {service_token}"
                    logger.info(f"[ai-score-all] Service token obtenu pour user={user_id}")
                else:
                    logger.warning("[ai-score-all] Service token vide — fallback sur JWT utilisateur")
            else:
                logger.warning(
                    f"[ai-score-all] /auth/internal/service-token status={svc_res.status_code} "
                    f"— fallback sur JWT utilisateur (tâche risque d'expirer en mid-flight)"
                )
    except Exception as e:
        logger.warning(f"[ai-score-all] Impossible d'obtenir un service token: {e} — fallback JWT utilisateur")

    headers = {"Authorization": bg_auth_header}
    inject(headers)

    background_tasks.add_task(_score_all_bg, user_id, comp_tuples, dict(headers))

    return AiScoreAllResponse(
        user_id=user_id,
        triggered=len(comp_tuples),
        message=f"Scoring IA lance en arriere-plan pour {len(comp_tuples)} competences."
    )


async def _compute_ai_score(
    user_id: int, competency_name: str, headers: dict
) -> tuple[Optional[float], Optional[str]]:
    """Appelle cv_api pour obtenir les missions puis demande a Gemini de noter la competence.

    Retourne (score: float 0.0-5.0, justification: str) ou (None, message_erreur).
    Le score est arrondi au pas de 0.5 le plus proche.
    """
    try:
        import google.generativeai as genai
        api_key = os.environ.get("GOOGLE_API_KEY", "")
        if not api_key:
            return None, "GOOGLE_API_KEY non configurée — scoring IA désactivé."
        genai.configure(api_key=api_key)
    except Exception as e:
        logger.error(f"[AI Score] google-generativeai non disponible: {e}")
        return None, "Librairie Gemini non disponible."

    # 1. Récupération des missions depuis cv_api
    missions = []
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(
                f"{CV_API_URL.rstrip('/')}/user/{user_id}/missions",
                headers=headers
            )
            if res.status_code == 200:
                missions = res.json().get("missions", [])
    except Exception as e:
        logger.warning(f"[AI Score] Failed to fetch missions for user {user_id}: {e}")
        return None, "Missions non disponibles (erreur réseau)."

    if not missions:
        return 1.0, "Aucune mission trouvée dans le CV — score minimal attribué."

    # 2. Filtrage des missions pertinentes (contenant la compétence)
    comp_norm = competency_name.lower()
    relevant_missions = [
        m for m in missions
        if any(comp_norm in c.lower() or c.lower() in comp_norm
               for c in m.get("competencies", []))
    ]
    # Si aucune mission n'est directement liée, utiliser les 5 premières comme contexte général
    context_missions = relevant_missions if relevant_missions else missions[:5]

    # 3. Construction du contexte enrichi : titre + entreprise + durée + description + compétences
    def _format_mission(m: dict) -> str:
        parts = []
        title = m.get('title', 'Mission sans titre')
        company = m.get('company', '?')
        parts.append(f"Mission : {title} chez {company}")
        if m.get('duration'):
            parts.append(f"  Durée : {m['duration']}")
        if m.get('description'):
            # Limiter à 300 chars pour ne pas dépasser la fenêtre de contexte
            desc_text = str(m['description'])[:300]
            parts.append(f"  Description : {desc_text}")
        comps = m.get("competencies", [])
        if comps:
            parts.append(f"  Compétences utilisées : {', '.join(comps)}")
        return "\n".join(parts)

    missions_text = "\n\n".join([_format_mission(m) for m in context_missions])
    context_label = "directement liées à cette compétence" if relevant_missions else "générales du consultant"

    # 4. Prompt enrichi — exige score + justification factuelle basée sur les missions réelles
    prompt = (
        f"Tu es un évaluateur expert de consultants IT et tech."
        f" Tu dois noter objectivement la maîtrise de la compétence '{competency_name}' "
        f"pour ce consultant, de 0.0 à 5.0 (par pas de 0.5)."
        f" Niveaux de référence :\n"
        f"  - 0.0 : Aucune trace dans le CV\n"
        f"  - 1.0 : Notions de base, mentionné une fois\n"
        f"  - 2.0 : Utilisation ponctuelle, 1 mission\n"
        f"  - 3.0 : Maîtrise confirmée, plusieurs missions\n"
        f"  - 4.0 : Expert, utilisation intense et répétée\n"
        f"  - 5.0 : Référence / Lead reconnu\n\n"
        f"Missions {context_label} (extrait du CV) :\n"
        f"{missions_text}\n\n"
        f"Réponds UNIQUEMENT en JSON valide avec exactement deux champs :\n"
        f"- score : float entre 0.0 et 5.0, arrondi au pas de 0.5\n"
        f"- justification : string factuelle de 50 à 200 caractères en français,"
        f" citant les missions concrètes qui justifient le score\n\n"
        f'Exemple : {{"score": 3.5, "justification": "Utilisé intensivement sur 2 missions chez Airbus et Thales, rôle de lead technique."}}'  # noqa
    )

    # 5. Appel Gemini avec JSON forcé
    try:
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json", "temperature": 0.1}
        )
        raw = response.text.strip()
        # Nettoyage robuste : extraire le bloc JSON si le modèle ajoute du texte autour
        if not raw.startswith("{"):
            import re
            json_match = re.search(r'\{.*\}', raw, re.DOTALL)
            raw = json_match.group(0) if json_match else raw
        data = json.loads(raw)
        score = max(0.0, min(5.0, float(data.get("score", 0.0))))
        # Arrondir au pas de 0.5
        score = round(score * 2) / 2
        justification = str(data.get("justification", ""))[:500]
        logger.info(f"[AI Score] user={user_id} comp='{competency_name}' score={score} (missions_contexte={len(context_missions)})")
        return score, justification
    except json.JSONDecodeError as e:
        logger.error(f"[AI Score] JSON parse error for '{competency_name}': {e} — raw='{raw[:200]}'")
        return None, "Réponse Gemini non parseable en JSON."
    except Exception as e:
        logger.error(f"[AI Score] Gemini call failed for '{competency_name}': {e}")

    return None, "Calcul IA échoué."


async def _score_all_bg(user_id: int, comp_tuples: list[tuple[int, str]], headers: dict):
    """BackgroundTask : score toutes les competences feuilles d'un utilisateur.

    Recoit des tuples (competency_id, competency_name) pour eviter toute
    contamination cross-session SQLAlchemy (les objets ORM de la requete HTTP
    ne peuvent pas etre utilises dans une nouvelle session AsyncSession).
    """
    async with database.SessionLocal() as db:
        for comp_id, comp_name in comp_tuples:
            try:
                score, justification = await _compute_ai_score(user_id, comp_name, headers)
                ev = await _get_or_create_evaluation(db, user_id, comp_id)
                ev.ai_score = score
                ev.ai_justification = justification
                ev.ai_scored_at = datetime.utcnow()
                ev.updated_at = datetime.utcnow()
                # Pas d'assignation ev.competency = <objet ORM externe> — charger
                # via db.refresh() uniquement si necessaire pour la serialisation.
                await db.commit()
                if score is not None:
                    logger.info(
                        f"[AI Score BG] user={user_id} competency='{comp_name}' "
                        f"comp_id={comp_id} score={score}"
                    )
                else:
                    logger.warning(
                        f"[AI Score BG] score=None user={user_id} competency='{comp_name}' "
                        f"comp_id={comp_id} — raison: {justification}"
                    )
            except Exception as e:
                logger.error(
                    f"[AI Score BG] Failed for user={user_id} comp='{comp_name}': {e}"
                )
                await db.rollback()
    delete_cache_pattern(f"competencies:evaluations:user:{user_id}:*")
    logger.info(f"[AI Score BG] Scoring terminé pour user={user_id} — {len(comp_tuples)} compétences traitées.")


# ============================================================
# Analytics Endpoints (Knowledge Graph Pragmatique)
# ============================================================

@router.get("/analytics/agency-coverage", response_model=AgencyCompetencyCoverage)
async def get_agency_competency_coverage(
    min_count: int = Query(1, ge=1, description="Nombre minimum de consultants possédant la compétence pour apparaitre"),
    limit: int = Query(50, ge=1, le=200),
    request: Request = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Heatmap compétences x agences.

    Pour chaque paire (agence, compétence feuille), retourne le nombre de consultants
    et le score IA moyen. Permet de comparer les agences sur leurs pool de compétences.

    Stratégie :
    1. Récupère les utilisateurs et leur agence depuis users_api (tag category)
    2. Fait un GROUP BY (agence, competency_id) sur user_competency + evaluations
    """
    cache_key = f"competencies:analytics:agency-coverage:{min_count}:{limit}"
    cached = get_cache(cache_key)
    if cached:
        return AgencyCompetencyCoverage(**cached)

    # 1. Récupérer les utilisateurs avec leur agence depuis users_api
    auth_header = request.headers.get("Authorization") if request else None
    headers = {"Authorization": auth_header} if auth_header else {}
    inject(headers)

    agency_map: dict[int, str] = {}  # user_id -> agency_name
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(
                f"{USERS_API_URL.rstrip('/')}/users",
                params={"limit": 500},
                headers=headers
            )
            if res.status_code == 200:
                data = res.json()
                users = data.get("items", data) if isinstance(data, dict) else data
                for u in users:
                    uid = u.get("id")
                    # Chercher le tag d'agence dans les catégories
                    agency = None
                    for tag in (u.get("tags") or []):
                        if isinstance(tag, dict) and tag.get("category") in ("agence", "agency", "Agence"):
                            agency = tag.get("name", tag.get("value"))
                            break
                    if uid and agency:
                        agency_map[uid] = agency
    except Exception as e:
        logger.warning(f"[analytics/agency-coverage] users_api indisponible: {e}")

    if not agency_map:
        return AgencyCompetencyCoverage(items=[], total_consultants=0, total_agencies=0)

    # 2. Jointure SQL : user_competency x competencies x evaluations
    #    Filtre sur les feuilles (pas de sous-compétences) + utilisateurs connus
    from sqlalchemy import case as sa_case

    leaf_subq = (
        select(Competency.id)
        .where(~select(Competency.id).where(Competency.parent_id == Competency.id).correlate().exists())
    ).scalar_subquery()

    stmt = (
        select(
            user_competency.c.user_id,
            user_competency.c.competency_id,
            Competency.name.label("competency_name"),
            CompetencyEvaluation.ai_score,
        )
        .join(Competency, user_competency.c.competency_id == Competency.id)
        .outerjoin(
            CompetencyEvaluation,
            (CompetencyEvaluation.user_id == user_competency.c.user_id)
            & (CompetencyEvaluation.competency_id == user_competency.c.competency_id)
        )
        .where(user_competency.c.user_id.in_(list(agency_map.keys())))
        .where(~Competency.id.in_(
            select(Competency.parent_id).where(Competency.parent_id.isnot(None)).distinct()
        ))
    )
    rows = (await db.execute(stmt)).all()

    # 3. Agrégation Python : (agency, competency) -> {count, scores}
    from collections import defaultdict
    agg: dict[tuple[str, str], dict] = defaultdict(lambda: {"count": 0, "scores": []})
    for row in rows:
        agency = agency_map.get(row.user_id)
        if not agency:
            continue
        key = (agency, row.competency_name)
        agg[key]["count"] += 1
        if row.ai_score is not None:
            agg[key]["scores"].append(row.ai_score)

    items = []
    for (agency, competency), vals in agg.items():
        if vals["count"] < min_count:
            continue
        avg_score = round(sum(vals["scores"]) / len(vals["scores"]), 2) if vals["scores"] else None
        items.append(AgencyCompetencyItem(
            agency=agency,
            competency=competency,
            count=vals["count"],
            avg_ai_score=avg_score
        ))

    items.sort(key=lambda x: (-x.count, x.agency, x.competency))
    items = items[:limit]

    result = AgencyCompetencyCoverage(
        items=items,
        total_consultants=len(agency_map),
        total_agencies=len(set(agency_map.values()))
    )
    set_cache(cache_key, result.model_dump(), 300)  # Cache 5 min
    return result


@router.get("/analytics/skill-gaps", response_model=SkillGapResult)
async def get_skill_gaps(
    user_ids: List[int] = Query(..., description="Liste des user_ids du pool à analyser"),
    competency_ids: Optional[List[int]] = Query(None, description="Liste de compétences cibles (toutes si omis)"),
    min_coverage: float = Query(0.0, ge=0.0, le=1.0, description="Seuil: compétences en-dessous de ce taux de couverture"),
    db: AsyncSession = Depends(get_db)
):
    """
    Gap de compétences dans un pool d'utilisateurs.

    Pour chaque compétence cible, calcule le pourcentage de consultants du pool
    qui la possèdent. Les compétences sous le seuil sont les 'gaps'.

    Cas d'usage :
    - Identifier les compétences manquantes dans une agence spécifique
    - Détecter les lacunes avant un AO (pass user_ids d'une agence)
    """
    if not user_ids:
        return SkillGapResult(gaps=[], pool_size=0)

    pool_size = len(user_ids)

    # Base : compétences cibles (toutes les feuilles, ou celles demandées)
    if competency_ids:
        comps_stmt = select(Competency).where(Competency.id.in_(competency_ids))
    else:
        # Toutes les feuilles
        comps_stmt = select(Competency).where(
            ~Competency.id.in_(
                select(Competency.parent_id).where(Competency.parent_id.isnot(None)).distinct()
            )
        )
    target_comps = (await db.execute(comps_stmt)).scalars().all()

    if not target_comps:
        return SkillGapResult(gaps=[], pool_size=pool_size)

    # Compter les consultants du pool ayant chaque compétence
    count_stmt = (
        select(
            user_competency.c.competency_id,
            func.count(user_competency.c.user_id).label("n")
        )
        .where(user_competency.c.user_id.in_(user_ids))
        .where(user_competency.c.competency_id.in_([c.id for c in target_comps]))
        .group_by(user_competency.c.competency_id)
    )
    count_rows = {r.competency_id: r.n for r in (await db.execute(count_stmt)).all()}

    gaps = []
    for comp in target_comps:
        n = count_rows.get(comp.id, 0)
        coverage = n / pool_size
        if coverage <= min_coverage:
            gaps.append(SkillGapItem(
                competency_id=comp.id,
                competency_name=comp.name,
                consultants_with_skill=n,
                consultants_in_pool=pool_size,
                coverage_pct=round(coverage * 100, 1)
            ))

    gaps.sort(key=lambda x: x.coverage_pct)
    return SkillGapResult(gaps=gaps, pool_size=pool_size)


@router.get("/analytics/similar-consultants/{user_id}", response_model=SimilarConsultantsResult)
async def get_similar_consultants(
    user_id: int,
    top_n: int = Query(5, ge=1, le=20, description="Nombre de consultants similaires à retourner"),
    db: AsyncSession = Depends(get_db)
):
    """
    Trouve les consultants les plus similaires à un consultant de référence.

    Utilise la similarité de Jaccard sur le set de compétences feuilles assignées.
    Jaccard = |A ∩ B| / |A ∪ B|

    Cas d'usage :
    - Trouver un remplaçant sur une mission
    - Identifier un mentor ou pair pour le coaching
    - Staffing de secours (backup consultant)
    """
    # Compétences du consultant de référence (feuilles uniquement)
    leaf_filter = ~Competency.id.in_(
        select(Competency.parent_id).where(Competency.parent_id.isnot(None)).distinct()
    )

    ref_stmt = (
        select(user_competency.c.competency_id, Competency.name)
        .join(Competency, user_competency.c.competency_id == Competency.id)
        .where(user_competency.c.user_id == user_id)
        .where(leaf_filter)
    )
    ref_rows = (await db.execute(ref_stmt)).all()
    ref_set: set[int] = {r.competency_id for r in ref_rows}
    ref_names: dict[int, str] = {r.competency_id: r.name for r in ref_rows}

    if not ref_set:
        return SimilarConsultantsResult(
            reference_user_id=user_id,
            reference_competency_count=0,
            similar_consultants=[]
        )

    # Tous les autres utilisateurs qui ont au moins une compétence commune
    other_stmt = (
        select(user_competency.c.user_id, user_competency.c.competency_id, Competency.name)
        .join(Competency, user_competency.c.competency_id == Competency.id)
        .where(user_competency.c.user_id != user_id)
        .where(user_competency.c.competency_id.in_(ref_set))
        .where(leaf_filter)
    )
    other_rows = (await db.execute(other_stmt)).all()

    # Grouper par user_id
    from collections import defaultdict
    user_comp_sets: dict[int, set[int]] = defaultdict(set)
    user_comp_names: dict[int, dict[int, str]] = defaultdict(dict)
    for row in other_rows:
        user_comp_sets[row.user_id].add(row.competency_id)
        user_comp_names[row.user_id][row.competency_id] = row.name

    # Calcul Jaccard pour chaque candidat
    results: list[SimilarConsultant] = []
    for other_uid, other_set in user_comp_sets.items():
        intersection = ref_set & other_set
        union = ref_set | other_set
        jaccard = len(intersection) / len(union) if union else 0.0
        shared_names = [ref_names.get(cid, user_comp_names[other_uid].get(cid, "")) for cid in intersection]
        results.append(SimilarConsultant(
            user_id=other_uid,
            common_competencies=len(intersection),
            jaccard_score=round(jaccard, 3),
            shared_competency_names=sorted(shared_names)
        ))

    results.sort(key=lambda x: -x.jaccard_score)
    results = results[:top_n]

    return SimilarConsultantsResult(
        reference_user_id=user_id,
        reference_competency_count=len(ref_set),
        similar_consultants=results
    )


# ============================================================
# Axe 4 : Suggestions de compétences issu du signal marché
# ============================================================

@router.post("/suggestions", response_model=CompetencySuggestionResponse, status_code=201)
async def create_competency_suggestion(
    payload: CompetencySuggestionCreate,
    db: AsyncSession = Depends(get_db),
) -> CompetencySuggestionResponse:
    """Soumet une suggestion de compétence pour révision admin.

    Idempotent : si une suggestion avec le même nom (insensible à la casse)
    existe déjà en statut PENDING_REVIEW, on incrémente son compteur
    d'occurrence plutôt que de créer un doublon.

    Une compétence déjà présente dans la taxonomie officielle ne doit pas
    être soumise (vérification upstream dans missions_api / cv_api).
    """
    name_clean = payload.name.strip()
    if not name_clean:
        raise HTTPException(status_code=422, detail="Le nom de la suggestion ne peut pas être vide.")

    # Idempotence : chercher une suggestion PENDING existante pour ce nom
    existing = (
        await db.execute(
            select(CompetencySuggestion)
            .where(func.lower(CompetencySuggestion.name) == name_clean.lower())
            .where(CompetencySuggestion.status == "PENDING_REVIEW")
        )
    ).scalars().first()

    if existing:
        existing.occurrence_count += 1
        existing.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(existing)
        return CompetencySuggestionResponse.model_validate(existing)

    new_suggestion = CompetencySuggestion(
        name=name_clean,
        source=payload.source,
        context=payload.context,
        status="PENDING_REVIEW",
        occurrence_count=1,
    )
    db.add(new_suggestion)
    await db.commit()
    await db.refresh(new_suggestion)
    logger.info(f"[Suggestions] Nouvelle suggestion créée : '{name_clean}' (source={payload.source})")
    return CompetencySuggestionResponse.model_validate(new_suggestion)


@router.get("/suggestions", response_model=list[CompetencySuggestionResponse])
async def list_competency_suggestions(
    status: str = Query("PENDING_REVIEW", description="Filtre par statut : PENDING_REVIEW | ACCEPTED | REJECTED"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[CompetencySuggestionResponse]:
    """Liste les suggestions de compétences, triées par occurrence décroissante.

    Le classement par `occurrence_count` permet d'identifier en premier les
    compétences les plus fréquemment demandées par les missions client (signal marché).
    """
    rows = (
        await db.execute(
            select(CompetencySuggestion)
            .where(CompetencySuggestion.status == status)
            .order_by(CompetencySuggestion.occurrence_count.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [CompetencySuggestionResponse.model_validate(r) for r in rows]


@router.patch("/suggestions/{suggestion_id}/review", response_model=CompetencySuggestionResponse)
async def review_competency_suggestion(
    suggestion_id: int,
    payload: SuggestionReviewRequest,
    bg_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    jwt_payload: dict = Depends(verify_jwt),
) -> CompetencySuggestionResponse:
    """(Admin) Accepte ou rejette une suggestion de compétence.

    Si action='ACCEPT' : crée la compétence dans la taxonomie officielle
    (via create_competency) et marque la suggestion comme ACCEPTED.
    Si action='REJECT' : marque simplement la suggestion comme REJECTED.
    """
    if jwt_payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Privilèges administrateur requis.")

    if payload.action not in ("ACCEPT", "REJECT"):
        raise HTTPException(status_code=422, detail="action doit être 'ACCEPT' ou 'REJECT'.")

    suggestion = (
        await db.execute(select(CompetencySuggestion).where(CompetencySuggestion.id == suggestion_id))
    ).scalars().first()
    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggestion introuvable.")

    if suggestion.status != "PENDING_REVIEW":
        raise HTTPException(
            status_code=409,
            detail=f"La suggestion est déjà en statut '{suggestion.status}' et ne peut plus être traitée.",
        )

    if payload.action == "ACCEPT":
        # Vérifier qu'elle n'existe pas déjà dans la taxonomie
        existing_comp = (
            await db.execute(
                select(Competency).where(func.lower(Competency.name) == suggestion.name.lower())
            )
        ).scalars().first()

        if not existing_comp:
            new_comp = Competency(
                name=suggestion.name,
                description=payload.description or f"Importé depuis les suggestions (source: {suggestion.source})",
                parent_id=payload.parent_id,
            )
            # Auto-génération d'alias
            gen_aliases = await _generate_aliases_for_competency(suggestion.name)
            if gen_aliases:
                new_comp.aliases = gen_aliases
                
            db.add(new_comp)
            await db.flush()
            logger.info(
                f"[Suggestions] Compétence acceptée et créée : '{suggestion.name}' (id={new_comp.id})"
            )
            delete_cache_pattern("competencies:*")
            trigger_taxonomy_cache_invalidation(bg_tasks)
        else:
            logger.info(
                f"[Suggestions] '{suggestion.name}' déjà présente dans la taxonomie (id={existing_comp.id}), suggestion acceptée sans création."
            )

        suggestion.status = "ACCEPTED"
    else:
        suggestion.status = "REJECTED"
        logger.info(f"[Suggestions] Suggestion rejetée : '{suggestion.name}'")

    suggestion.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(suggestion)
    return CompetencySuggestionResponse.model_validate(suggestion)
