"""categories_router.py — Items categories et statistiques."""
import os

from shared.cache import get_cache, set_cache
from shared.database import get_db
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from shared.auth.jwt import verify_jwt
from src.items.models import Category, Item
from src.items.schemas import (CategoryCreate, CategoryResponse,
                               ItemStatsResponse, PaginationResponse)
from sqlalchemy import func

USERS_API_URL = os.getenv("USERS_API_URL", "http://users_api:8000")
CACHE_TTL = 60


router = APIRouter(prefix="", tags=["items_categories"], dependencies=[Depends(verify_jwt)])


@router.get("/categories", response_model=PaginationResponse[CategoryResponse])
async def list_categories(
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0, le=2_147_483_647),
    limit: int = Query(50, ge=1, le=500),
):
    total = (await db.execute(select(func.count()).select_from(Category))).scalar()
    categories = (await db.execute(select(Category).offset(skip).limit(limit))).scalars().all()
    return {"items": categories, "total": total, "skip": skip, "limit": limit}


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
    cached = await get_cache(cache_key)
    if cached:
        return ItemStatsResponse(**cached)

    total = (await db.execute(select(func.count()).select_from(Item))).scalar()

    by_user_raw = (await db.execute(select(Item.user_id, func.count(Item.id)).group_by(Item.user_id))).all()
    by_user = {user_id: count for user_id, count in by_user_raw}

    result = ItemStatsResponse(total=total, by_user=by_user)
    await set_cache(cache_key, result.model_dump(), CACHE_TTL)
    return result
