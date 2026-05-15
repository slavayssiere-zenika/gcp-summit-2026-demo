"""
competencies_router.py — CRUD compétences, suggestions et import bulk_tree.

Routes :
  GET    /
  GET    /search
  POST   /suggestions
  GET    /suggestions
  PATCH  /suggestions/{suggestion_id}/review
  GET    /{competency_id}
  GET    /{competency_id}/users
  POST   /bulk_tree
  POST   /
  PUT    /{competency_id}
  DELETE /{competency_id}
  POST   /stats/counts

NOTE: l'ordre des includes dans main.py est critique.
Les routes statiques (search, suggestions, stats, bulk_tree) DOIVENT être
enregistrées AVANT les routes wildcard (/{competency_id}).
"""

import logging
from typing import List

from cache import delete_cache, delete_cache_pattern, get_cache, set_cache
from database import get_db
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Response,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select
from sqlalchemy.orm import aliased
from src.auth import verify_jwt
from src.competencies.helpers import (
    _generate_aliases_for_competency,
    check_grammatical_conflict,
    serialize_competency,
)
from src.competencies.models import Competency, user_competency
from src.competencies.schemas import (
    CompetencyCount,
    CompetencyCreate,
    CompetencyResponse,
    CompetencyStatsResponse,
    CompetencyUpdate,
    PaginationResponse,
    StatsRequest,
)

logger = logging.getLogger(__name__)
CACHE_TTL = 60

router = APIRouter(prefix="", tags=["competencies"], dependencies=[Depends(verify_jwt)])


@router.get("/", response_model=PaginationResponse[CompetencyResponse])
async def list_competencies(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=2000),
    db: AsyncSession = Depends(get_db),
):
    """Retourne l'arbre complet de compétences (structure hiérarchique paginée sur les racines)."""
    cache_key = f"competencies:tree:list:{skip}:{limit}"
    cached = get_cache(cache_key)
    if cached:
        return PaginationResponse(**cached)

    all_comps = (await db.execute(select(Competency))).scalars().all()
    nodes = {
        c.id: {
            "id": c.id,
            "name": c.name,
            "description": c.description,
            "aliases": c.aliases,
            "parent_id": c.parent_id,
            "created_at": c.created_at,
            "sub_competencies": [],
        }
        for c in all_comps
    }
    roots = []
    for c in all_comps:
        if c.parent_id is None:
            roots.append(nodes[c.id])
        elif c.parent_id in nodes:
            nodes[c.parent_id]["sub_competencies"].append(nodes[c.id])

    roots.sort(key=lambda x: x["id"])
    result = PaginationResponse(
        items=roots[skip: skip + limit], total=len(roots), skip=skip, limit=limit
    )
    set_cache(cache_key, result.model_dump(), CACHE_TTL)
    return result


@router.get("/search", response_model=PaginationResponse[CompetencyResponse])
async def search_competencies(
    query: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Recherche full-text sur le nom et les aliases de compétences."""
    from sqlalchemy import or_

    cache_key = f"competencies:search:{query}:{limit}"
    cached = get_cache(cache_key)
    if cached:
        return PaginationResponse(**cached)
    results = (
        (
            await db.execute(
                select(Competency)
                .filter(
                    or_(
                        Competency.name.ilike(f"%{query}%"),
                        Competency.aliases.ilike(f"%{query}%"),
                    )
                )
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    response = PaginationResponse(
        items=[serialize_competency(c) for c in results],
        total=len(results),
        skip=0,
        limit=limit,
    )
    set_cache(cache_key, response.model_dump(), CACHE_TTL)
    return response


@router.get("/{competency_id}", response_model=CompetencyResponse)
async def get_competency(competency_id: int, db: AsyncSession = Depends(get_db)):
    """Retourne une compétence par son ID."""
    cache_key = f"competencies:{competency_id}"
    cached = get_cache(cache_key)
    if cached:
        return CompetencyResponse(**cached)
    competency = (
        (await db.execute(select(Competency).filter(Competency.id == competency_id)))
        .scalars()
        .first()
    )
    if not competency:
        raise HTTPException(status_code=404, detail="Competency not found")
    result = CompetencyResponse(**serialize_competency(competency))
    set_cache(cache_key, result.model_dump(), CACHE_TTL)
    return result


@router.get("/{competency_id}/users", response_model=List[int])
async def list_competency_users(competency_id: int, db: AsyncSession = Depends(get_db)):
    """Retourne les user_ids associés à cette compétence et ses descendants (CTE récursif)."""
    cache_key = f"competencies:{competency_id}:users"
    cached = get_cache(cache_key)
    if cached:
        return cached
    comp_a = aliased(Competency)
    hierarchy = (
        select(Competency.id)
        .where(Competency.id == competency_id)
        .cte(name="hierarchy", recursive=True)
    )
    hierarchy = hierarchy.union_all(
        select(comp_a.id).where(comp_a.parent_id == hierarchy.c.id)
    )
    results = (
        await db.execute(
            select(user_competency.c.user_id).where(
                user_competency.c.competency_id.in_(select(hierarchy.c.id))
            )
        )
    ).all()
    user_ids = list(set([r[0] for r in results]))
    set_cache(cache_key, user_ids, CACHE_TTL)
    return user_ids


@router.post("/", response_model=CompetencyResponse, status_code=201)
async def create_competency(
    competency: CompetencyCreate,
    bg_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    jwt_payload: dict = Depends(verify_jwt),
):
    """Crée une nouvelle compétence (rôles : admin, rh, service_account)."""
    if jwt_payload.get("role") not in ("admin", "rh", "service_account"):
        raise HTTPException(
            status_code=403,
            detail="Accès refusé : rôles admin/rh/service_account requis.",
        )
    competency.name = competency.name.strip()
    if competency.parent_id is not None:
        if (
            not (
                await db.execute(
                    select(Competency).filter(Competency.id == competency.parent_id)
                )
            )
            .scalars()
            .first()
        ):
            raise HTTPException(status_code=400, detail="Parent competency not found")
    conflict = await check_grammatical_conflict(db, competency.name)
    if conflict:
        if conflict.name.lower() == competency.name.lower():
            return CompetencyResponse(**serialize_competency(conflict))
        raise HTTPException(
            status_code=409,
            detail=f"Une variante grammaticale de '{competency.name}' existe déjà : '{conflict.name}'.",
        )
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
        existing = (
            (
                await db.execute(
                    select(Competency).filter(Competency.name.ilike(competency.name))
                )
            )
            .scalars()
            .first()
        )
        if existing:
            return CompetencyResponse(**serialize_competency(existing))
        raise HTTPException(
            status_code=409, detail="Competency naming conflict unresolved"
        )
    delete_cache_pattern("competencies:tree:*")
    return CompetencyResponse(**serialize_competency(db_comp))


@router.put("/{competency_id}", response_model=CompetencyResponse)
async def update_competency(
    competency_id: int,
    competency_update: CompetencyUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Met à jour une compétence (détection de conflits grammaticaux)."""
    db_comp = (
        (await db.execute(select(Competency).filter(Competency.id == competency_id)))
        .scalars()
        .first()
    )
    if not db_comp:
        raise HTTPException(status_code=404, detail="Competency not found")
    if (
        hasattr(competency_update, "parent_id")
        and competency_update.parent_id == competency_id
    ):
        raise HTTPException(
            status_code=400, detail="A competency cannot be its own parent"
        )
    for key, value in competency_update.model_dump(exclude_unset=True).items():
        if key == "name" and value and value.strip() != db_comp.name:
            value = value.strip()
            conflict = await check_grammatical_conflict(
                db, value, exclude_id=competency_id
            )
            if conflict:
                raise HTTPException(
                    status_code=409,
                    detail=f"Une compétence '{conflict.name}' existe déjà.",
                )
        setattr(db_comp, key, value)
    try:
        await db.commit()
        await db.refresh(db_comp)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Conflit de données.")
    delete_cache(f"competencies:{competency_id}")
    delete_cache_pattern("competencies:tree:*")
    return CompetencyResponse(**serialize_competency(db_comp))


@router.delete("/{competency_id}", status_code=204)
async def delete_competency(
    competency_id: int,
    db: AsyncSession = Depends(get_db),
    jwt_payload: dict = Depends(verify_jwt),
):
    """(Admin) Supprime une compétence."""
    if jwt_payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Privilèges administrateur requis.")
    db_comp = (
        (await db.execute(select(Competency).filter(Competency.id == competency_id)))
        .scalars()
        .first()
    )
    if not db_comp:
        raise HTTPException(status_code=404, detail="Competency not found")
    await db.delete(db_comp)
    await db.commit()
    delete_cache(f"competencies:{competency_id}")
    delete_cache_pattern("competencies:tree:*")
    return Response(status_code=204)


@router.post("/stats/counts", response_model=CompetencyStatsResponse)
async def get_competency_stats(req: StatsRequest, db: AsyncSession = Depends(get_db)):
    """Statistiques de compétences (comptage par utilisateur, filtrable sur une cohorte)."""
    stmt = select(
        Competency.id,
        Competency.name,
        func.count(user_competency.c.user_id).label("count"),
    ).join(user_competency, Competency.id == user_competency.c.competency_id)
    if req.user_ids is not None:
        if not req.user_ids:
            return CompetencyStatsResponse(items=[])
        stmt = stmt.where(user_competency.c.user_id.in_(req.user_ids))
    stmt = stmt.group_by(Competency.id, Competency.name)
    stmt = stmt.order_by(
        func.count(user_competency.c.user_id).asc()
        if req.sort_order.lower() == "asc"
        else func.count(user_competency.c.user_id).desc()
    ).limit(req.limit)
    results = (await db.execute(stmt)).all()
    return CompetencyStatsResponse(
        items=[CompetencyCount(id=r[0], name=r[1], count=r[2]) for r in results]
    )
