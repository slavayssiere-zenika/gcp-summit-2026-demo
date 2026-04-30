"""categories_router.py — Items categories et statistiques."""
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

router = APIRouter(prefix="", tags=["items_categories"], dependencies=[Depends(verify_jwt)])

@router.get("/categories", response_model=List[CategoryResponse])
async def list_categories(db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(Category))).scalars().all()

@router.post("/categories", response_model=CategoryResponse, status_code=201)
async def create_category(category: CategoryCreate, db: AsyncSession = Depends(get_db)):
    db_category = Category(name=category.name, description=category.description)
    db.add(db_category)
    try:
        await db.commit()
        await db.refresh(db_category)
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Category name already exists")
    return db_category

@router.get("/stats", response_model=ItemStatsResponse)
async def get_item_stats(db: AsyncSession = Depends(get_db)):
    cache_key = "items:stats"
    cached = get_cache(cache_key)
    if cached:
        return ItemStatsResponse(**cached)

    from sqlalchemy import func
    total = (await db.execute(select(func.count()).select_from(Item))).scalar()
    
    by_user_raw = (await db.execute(select(Item.user_id, func.count(Item.id)).group_by(Item.user_id))).all()
    by_user = {user_id: count for user_id, count in by_user_raw}

    result = ItemStatsResponse(total=total, by_user=by_user)
    set_cache(cache_key, result.model_dump(), CACHE_TTL)
    return result
