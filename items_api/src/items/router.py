from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.orm import Session
from typing import List
import httpx
from opentelemetry import trace
from opentelemetry.propagate import inject

from database import get_db
from cache import get_cache, set_cache, delete_cache, delete_cache_pattern
from src.items.models import Item, Category
from src.items.schemas import (
    ItemCreate, ItemResponse, UserInfo, PaginationResponse, ItemStatsResponse,
    CategoryCreate, CategoryResponse
)

from src.auth import verify_jwt

router = APIRouter(prefix="/items", tags=["items"], dependencies=[Depends(verify_jwt)])

USERS_API_URL = "http://users_api:8000"
CACHE_TTL = 60


@router.get("/categories", response_model=List[CategoryResponse])
async def list_categories(db: Session = Depends(get_db)):
    return db.query(Category).all()


@router.post("/categories", response_model=CategoryResponse, status_code=201)
async def create_category(category: CategoryCreate, db: Session = Depends(get_db)):
    db_category = Category(name=category.name, description=category.description)
    db.add(db_category)
    try:
        db.commit()
        db.refresh(db_category)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=400, detail="Category name already exists")
    return db_category


@router.get("/stats", response_model=ItemStatsResponse)
async def get_item_stats(db: Session = Depends(get_db)):
    cache_key = "items:stats"
    cached = get_cache(cache_key)
    if cached:
        return ItemStatsResponse(**cached)

    total = db.query(Item).count()
    
    # Group by user_id
    from sqlalchemy import func
    by_user_raw = db.query(Item.user_id, func.count(Item.id)).group_by(Item.user_id).all()
    by_user = {user_id: count for user_id, count in by_user_raw}

    result = ItemStatsResponse(
        total=total,
        by_user=by_user
    )
    set_cache(cache_key, result.model_dump(), CACHE_TTL)
    return result


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
            response = await client.get(f"{USERS_API_URL}/users/{user_id}", headers=headers)
            if response.status_code == 404:
                raise HTTPException(status_code=400, detail=f"User with id {user_id} not found")
            response.raise_for_status()
            return UserInfo(**response.json())
        except httpx.HTTPError as e:
            raise HTTPException(status_code=503, detail=f"Unable to verify user: {str(e)}")


async def enrich_item(item: Item, request: Request) -> ItemResponse:
    try:
        user = await get_user_from_api(item.user_id, request)
    except HTTPException:
        user = None
    
    return ItemResponse(
        id=item.id,
        name=item.name,
        description=item.description,
        user_id=item.user_id,
        created_at=item.created_at,
        user=user,
        categories=[CategoryResponse.model_validate(c) for c in item.categories]
    )


@router.get("/", response_model=PaginationResponse[ItemResponse])
async def list_items(
    request: Request,
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of records to return"),
    db: Session = Depends(get_db),
    auth_payload: dict = Depends(verify_jwt)
):
    cache_key = f"items:list:{skip}:{limit}"
    cached = get_cache(cache_key)
    if cached:
        return PaginationResponse(**cached)

    allowed_ids = auth_payload.get("allowed_category_ids", [])
    if not allowed_ids:
        # If no rights, return empty early
        return PaginationResponse(items=[], total=0, skip=skip, limit=limit)

    query = db.query(Item).join(Item.categories).filter(Category.id.in_(allowed_ids)).distinct()
    
    total = query.count()
    items = query.offset(skip).limit(limit).all()
    enriched_items = [await enrich_item(item, request) for item in items]
    result = PaginationResponse(
        items=[i.model_dump() for i in enriched_items],
        total=total,
        skip=skip,
        limit=limit
    )
    set_cache(cache_key, result.model_dump(), CACHE_TTL)
    return result


@router.get("/{item_id}", response_model=ItemResponse)
async def get_item(
    item_id: int, 
    request: Request,
    db: Session = Depends(get_db), 
    auth_payload: dict = Depends(verify_jwt)
):
    cache_key = f"items:{item_id}"
    cached = get_cache(cache_key)
    if cached:
        return ItemResponse(**cached)

    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    # Authorization Check
    allowed_ids = set(auth_payload.get("allowed_category_ids", []))
    item_categories = {c.id for c in item.categories}
    
    if not item_categories.intersection(allowed_ids):
        raise HTTPException(status_code=403, detail="Not authorized to view this item")

    result = await enrich_item(item, request)
    set_cache(cache_key, result.model_dump(), CACHE_TTL)
    return result


@router.post("/", response_model=ItemResponse, status_code=201)
async def create_item(
    request: Request,
    item: ItemCreate, 
    db: Session = Depends(get_db), 
    auth_payload: dict = Depends(verify_jwt)
):
    # Validate categories (at least one required)
    if not item.category_ids:
        raise HTTPException(status_code=400, detail="Item must have at least one category")
    
    categories = db.query(Category).filter(Category.id.in_(item.category_ids)).all()
    if len(categories) != len(set(item.category_ids)):
        raise HTTPException(status_code=400, detail="One or more category IDs are invalid")

    # Check if user has permission for ALL requested categories using JWT payload
    allowed_ids = auth_payload.get("allowed_category_ids", [])
    forbidden_ids = [cid for cid in item.category_ids if cid not in allowed_ids]
    if forbidden_ids:
        raise HTTPException(
            status_code=403, 
            detail=f"User does not have rights for categories: {forbidden_ids}"
        )

    db_item = Item(
        name=item.name,
        description=item.description,
        user_id=item.user_id,
        categories=categories
    )
    db.add(db_item)
    db.commit()
    db.refresh(db_item)

    delete_cache_pattern("items:list:*")
    return await enrich_item(db_item, request)


@router.get("/user/{user_id}", response_model=PaginationResponse[ItemResponse])
async def list_user_items(
    user_id: int,
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    auth_payload: dict = Depends(verify_jwt)
):
    cache_key = f"items:user:{user_id}:{skip}:{limit}"
    cached = get_cache(cache_key)
    if cached:
        return PaginationResponse(**cached)

    # The visible items for this user_id should be restricted by the CALLER's allowed categories
    allowed_ids = auth_payload.get("allowed_category_ids", [])
    
    if not allowed_ids:
        # If the caller has no rights, they see nothing
        return PaginationResponse(items=[], total=0, skip=skip, limit=limit)

    # Query items owned by user AND belonging to at least one allowed category
    query = db.query(Item).join(Item.categories).filter(
        Item.user_id == user_id,
        Category.id.in_(allowed_ids)
    ).distinct()

    total = query.count()
    items = query.offset(skip).limit(limit).all()
    enriched_items = [await enrich_item(item, request) for item in items]
    result = PaginationResponse(
        items=[i.model_dump() for i in enriched_items],
        total=total,
        skip=skip,
        limit=limit
    )
    set_cache(cache_key, result.model_dump(), CACHE_TTL)
    return result
