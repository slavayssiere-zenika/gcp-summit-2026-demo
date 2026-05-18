"""search_router.py — Items recherche et filtrage par utilisateur."""
import asyncio
import os

import httpx
from cache import get_cache, set_cache
from shared.database import get_db
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Path
from opentelemetry.propagate import inject
from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from shared.auth.jwt import verify_jwt
from src.items.models import Category, Item
from src.items.schemas import (CategoryResponse, ItemResponse,
                               PaginationResponse, UserInfo)

USERS_API_URL = os.getenv("USERS_API_URL", "http://users_api:8000")
CACHE_TTL = 60

# Semaphore identique a crud_router : evite la saturation du pool DB/HTTP
# sous forte concurrence. Partage la meme valeur env DB_POOL_SIZE.
_ENRICH_SEM = asyncio.Semaphore(int(os.getenv("DB_POOL_SIZE", 20)) * 3 // 4)


def get_trace_context_headers() -> dict:
    headers = {}
    inject(headers)
    return headers


async def get_user_from_api(user_id: int, request: Request) -> UserInfo:
    headers = get_trace_context_headers()
    auth_header = request.headers.get("Authorization")
    if auth_header:
        headers["Authorization"] = auth_header
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=3.0)) as client:
        try:
            response = await client.get(
                f"{USERS_API_URL.rstrip('/')}/users/{user_id}", headers=headers
            )
            if response.status_code == 404:
                raise HTTPException(status_code=400, detail=f"User with id {user_id} not found")
            response.raise_for_status()
            return UserInfo(**response.json())
        except httpx.HTTPError as e:
            raise HTTPException(status_code=503, detail=f"Unable to verify user: {e}")


async def enrich_item(item: Item, request: Request) -> ItemResponse:
    """Enrichit un item avec les infos user via cache Redis (TTL=120s).

    Meme pattern que crud_router.enrich_item : semaphore + cache Redis
    pour eviter N appels HTTP sequentiels vers users_api.
    """
    async with _ENRICH_SEM:
        user_cache_key = f"items:user_info:{item.user_id}"
        cached_user = get_cache(user_cache_key)
        if cached_user:
            user = UserInfo(**cached_user)
        else:
            try:
                user = await get_user_from_api(item.user_id, request)
                set_cache(user_cache_key, user.model_dump(), 120)  # TTL 120s
            except HTTPException:
                user = None
    return ItemResponse(
        id=item.id,
        name=item.name,
        description=item.description,
        metadata_json=item.metadata_json,
        user_id=item.user_id,
        created_at=item.created_at,
        user=user,
        categories=[CategoryResponse.model_validate(c) for c in item.categories]
    )


router = APIRouter(prefix="", tags=["items_search"], dependencies=[Depends(verify_jwt)])


@router.get("/search/query", response_model=PaginationResponse[ItemResponse])
async def search_items(
    request: Request,
    query: str = Query(..., min_length=1, description="Search term"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of records to return"),
    include_user: bool = Query(False, description="Enrichit avec infos user via users_api (N appels HTTP)."),
    db: AsyncSession = Depends(get_db),
    auth_payload: dict = Depends(verify_jwt)
):
    allowed_ids = auth_payload.get("allowed_category_ids", [])
    allowed_ids_str = ",".join(map(str, sorted(allowed_ids)))
    cache_key = f"items:search:{query}:{limit}:auth_{allowed_ids_str}:enrich_{include_user}"

    cached = get_cache(cache_key)
    if cached:
        return PaginationResponse(**cached)

    if not allowed_ids:
        return PaginationResponse(items=[], total=0, skip=0, limit=limit)

    # Requete count optimisee : evite le double-wrap subquery
    count_q = (
        select(func.count(Item.id.distinct()))
        .join(Item.categories)
        .filter(
            Category.id.in_(allowed_ids),
            or_(Item.name.ilike(f"%{query}%"), Item.description.ilike(f"%{query}%"))
        )
    )
    items_q = (
        select(Item).options(selectinload(Item.categories))
        .join(Item.categories)
        .filter(
            Category.id.in_(allowed_ids),
            or_(Item.name.ilike(f"%{query}%"), Item.description.ilike(f"%{query}%"))
        )
        .distinct()
        .limit(limit)
    )

    # Sequentiel obligatoire : AsyncSession ne supporte pas 2 db.execute() en gather
    total = (await db.execute(count_q)).scalar()
    items = (await db.execute(items_q)).scalars().all()

    if include_user:
        # Parallelisation asyncio.gather uniquement sur les appels HTTP (enrich = users_api)
        enriched_items = await asyncio.gather(*[enrich_item(item, request) for item in items])
    else:
        enriched_items = [ItemResponse.model_validate(item, from_attributes=True) for item in items]

    result = PaginationResponse(items=[i.model_dump() for i in enriched_items], total=total, skip=0, limit=limit)
    set_cache(cache_key, result.model_dump(), CACHE_TTL)
    return result


@router.get("/user/{user_id}", response_model=PaginationResponse[ItemResponse])
async def list_user_items(
    request: Request,
    user_id: int = Path(..., gt=0, le=2_147_483_647),
    skip: int = Query(0, ge=0, le=2_147_483_647),
    limit: int = Query(10, ge=1, le=100),
    include_user: bool = Query(False, description="Enrichit avec infos user via users_api (N appels HTTP)."),
    db: AsyncSession = Depends(get_db),
    auth_payload: dict = Depends(verify_jwt)
):
    allowed_ids = auth_payload.get("allowed_category_ids", [])
    allowed_ids_str = ",".join(map(str, sorted(allowed_ids)))
    cache_key = f"items:user:{user_id}:{skip}:{limit}:auth_{allowed_ids_str}:enrich_{include_user}"

    cached = get_cache(cache_key)
    if cached:
        return PaginationResponse(**cached)

    if not allowed_ids:
        return PaginationResponse(items=[], total=0, skip=skip, limit=limit)

    # Requete count optimisee (evite le subquery wrapper)
    count_q = (
        select(func.count(Item.id.distinct()))
        .join(Item.categories)
        .filter(Item.user_id == user_id, Category.id.in_(allowed_ids))
    )
    items_q = (
        select(Item).options(selectinload(Item.categories))
        .join(Item.categories)
        .filter(Item.user_id == user_id, Category.id.in_(allowed_ids))
        .distinct()
        .offset(skip)
        .limit(limit)
    )

    # Sequentiel obligatoire : AsyncSession ne supporte pas 2 db.execute() en gather
    total = (await db.execute(count_q)).scalar()
    items = (await db.execute(items_q)).scalars().all()

    if include_user:
        # Parallelisation asyncio.gather uniquement sur les appels HTTP (enrich = users_api)
        enriched_items = await asyncio.gather(*[enrich_item(item, request) for item in items])
    else:
        enriched_items = [ItemResponse.model_validate(item, from_attributes=True) for item in items]

    result = PaginationResponse(items=[i.model_dump() for i in enriched_items], total=total, skip=skip, limit=limit)
    set_cache(cache_key, result.model_dump(), CACHE_TTL)
    return result
