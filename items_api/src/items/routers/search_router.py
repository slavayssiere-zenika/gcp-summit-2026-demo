"""search_router.py — Items recherche et filtrage par utilisateur."""
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
from typing import List
import httpx
from opentelemetry.propagate import inject
import os

from database import get_db
from cache import get_cache, set_cache, delete_cache_pattern
from src.items.models import Item, Category
from src.items.schemas import (
    ItemCreate, ItemUpdate, ItemResponse, UserInfo, PaginationResponse, ItemStatsResponse,
    CategoryCreate, CategoryResponse, BulkItemCreate
)
from src.auth import verify_jwt

USERS_API_URL = os.getenv("USERS_API_URL", "http://users_api:8000")
CACHE_TTL = 60

def get_trace_context_headers() -> dict:
    headers = {}
    inject(headers)
    return headers

async def get_user_from_api(user_id: int, request: Request) -> UserInfo:
    headers = get_trace_context_headers()
    auth_header = request.headers.get("Authorization")
    if auth_header:
        headers["Authorization"] = auth_header
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{USERS_API_URL.rstrip('/')}/users/{user_id}", headers=headers)
            if response.status_code == 404:
                raise HTTPException(status_code=400, detail=f"User with id {user_id} not found")
            response.raise_for_status()
            return UserInfo(**response.json())
        except httpx.HTTPError as e:
            raise HTTPException(status_code=503, detail=f"Unable to verify user: {e}")

async def enrich_item(item: Item, request: Request) -> ItemResponse:
    try:
        user = await get_user_from_api(item.user_id, request)
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
    db: AsyncSession = Depends(get_db),
    auth_payload: dict = Depends(verify_jwt)
):
    allowed_ids = auth_payload.get("allowed_category_ids", [])
    allowed_ids_str = ",".join(map(str, sorted(allowed_ids)))
    cache_key = f"items:search:{query}:{limit}:auth_{allowed_ids_str}"
    
    cached = get_cache(cache_key)
    if cached:
        return PaginationResponse(**cached)

    if not allowed_ids:
        return PaginationResponse(items=[], total=0, skip=0, limit=limit)

    from sqlalchemy import func, or_
    base_query = select(Item).options(selectinload(Item.categories)).join(Item.categories).filter(
        Category.id.in_(allowed_ids),
        or_(Item.name.ilike(f"%{query}%"), Item.description.ilike(f"%{query}%"))
    ).distinct()
    
    total = (await db.execute(select(func.count()).select_from(base_query.subquery()))).scalar()
    items = (await db.execute(base_query.limit(limit))).scalars().all()
    enriched_items = [await enrich_item(item, request) for item in items]
    
    result = PaginationResponse(items=[i.model_dump() for i in enriched_items], total=total, skip=0, limit=limit)
    set_cache(cache_key, result.model_dump(), CACHE_TTL)
    return result

@router.get("/user/{user_id}", response_model=PaginationResponse[ItemResponse])
async def list_user_items(
    user_id: int,
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    auth_payload: dict = Depends(verify_jwt)
):
    allowed_ids = auth_payload.get("allowed_category_ids", [])
    allowed_ids_str = ",".join(map(str, sorted(allowed_ids)))
    cache_key = f"items:user:{user_id}:{skip}:{limit}:auth_{allowed_ids_str}"
    
    cached = get_cache(cache_key)
    if cached:
        return PaginationResponse(**cached)

    if not allowed_ids:
        return PaginationResponse(items=[], total=0, skip=skip, limit=limit)

    from sqlalchemy.future import select
    from sqlalchemy import func
    base_query = select(Item).options(selectinload(Item.categories)).join(Item.categories).filter(
        Item.user_id == user_id,
        Category.id.in_(allowed_ids)
    ).distinct()

    total = (await db.execute(select(func.count()).select_from(base_query.subquery()))).scalar()
    items = (await db.execute(base_query.offset(skip).limit(limit))).scalars().all()
    enriched_items = [await enrich_item(item, request) for item in items]
    result = PaginationResponse(items=[i.model_dump() for i in enriched_items], total=total, skip=skip, limit=limit)
    set_cache(cache_key, result.model_dump(), CACHE_TTL)
    return result