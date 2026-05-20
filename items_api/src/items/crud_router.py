"""crud_router.py — Items CRUD (list, get, create, bulk, update, delete)."""
import asyncio
import os
from typing import List

import httpx
from shared.cache import clear_namespace, get_cache, set_cache
from shared.database import get_db
from shared.semaphore_utils import acquire_shielded
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Path
from opentelemetry.propagate import inject
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from shared.auth.jwt import verify_jwt
from src.items.models import Category, Item, item_category
from src.items.schemas import (BulkItemCreate, CategoryResponse,
                               ItemCreate, ItemResponse, ItemUpdate,
                               PaginationResponse, UserInfo)
from sqlalchemy import func, delete as sa_delete
from sqlalchemy.orm import selectinload as _sil
import logging as _log

# Semaphore limitant les appels HTTP concurrents vers users_api depuis asyncio.gather.
# Sans ce plafond : 50 users Locust x limit=10 items = 500 connexions DB simultanees
# -> QueuePool(size=10, overflow=20) explose en TimeoutError.
# Valeur : DB_POOL_SIZE * 0.75 = ~15 appels concurrents max par process.
# ⚠️ GLOBAL PERSISTANT : utiliser acquire_shielded(_ENRICH_SEM) (shared.semaphore_utils).
_ENRICH_SEM = asyncio.Semaphore(int(os.getenv("DB_POOL_SIZE", 20)) * 3 // 4)

USERS_API_URL = os.getenv("USERS_API_URL", "http://users_api:8000")

# Guard 429 — protège le pool AlloyDB contre les appels bulk massifs (post-mortem 2026-05-13)
# Valeur configurable via BULK_ENDPOINT_SEMAPHORE sans redéploiement.
_BULK_SEM: asyncio.Semaphore | None = None


def _get_bulk_sem() -> asyncio.Semaphore:
    global _BULK_SEM
    if _BULK_SEM is None:
        _BULK_SEM = asyncio.Semaphore(int(os.getenv("BULK_ENDPOINT_SEMAPHORE", "5")))
    return _BULK_SEM


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
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=3.0)) as client:
        try:
            response = await client.get(f"{USERS_API_URL.rstrip('/')}/{user_id}", headers=headers, timeout=10.0)
            if response.status_code == 404:
                raise HTTPException(status_code=400, detail=f"User with id {user_id} not found")
            response.raise_for_status()
            return UserInfo(**response.json())
        except httpx.HTTPError as e:
            raise HTTPException(status_code=503, detail=f"Unable to verify user: {e}")


async def enrich_item(item: Item, request: Request) -> ItemResponse:
    """Enrichit un item avec les infos user.

    Optimisation N+1 : le UserInfo est cache en Redis (TTL=120s) pour eviter
    un appel HTTP vers users_api par item lors des GET /items/ avec pagination.
    _ENRICH_SEM limite les appels concurrents pour eviter l epuisement du pool DB.
    """
    async with acquire_shielded(_ENRICH_SEM):
        user_cache_key = f"items:user_info:{item.user_id}"
        cached_user = await get_cache(user_cache_key)
        if cached_user:
            user = UserInfo(**cached_user)
        else:
            try:
                user = await get_user_from_api(item.user_id, request)
                await set_cache(user_cache_key, user.model_dump(), 120)  # TTL 120s
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

router = APIRouter(prefix="", tags=["items_crud"], dependencies=[Depends(verify_jwt)])


@router.get("/", response_model=PaginationResponse[ItemResponse])
async def list_items(
    request: Request,
    skip: int = Query(0, ge=0, le=2_147_483_647, description="Number of records to skip"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of records to return"),
    search: str = Query(None, description="Search term"),
    include_user: bool = Query(
        False,
        description=(
            "Enrichit chaque item avec les infos user (nom, email) via users_api. "
            "False par defaut : evite N appels HTTP sous charge (N=taille de la page). "
            "Mettre True uniquement si le client a besoin des details utilisateur."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    auth_payload: dict = Depends(verify_jwt)
):
    allowed_ids = auth_payload.get("allowed_category_ids", [])
    allowed_ids_str = ",".join(map(str, sorted(allowed_ids)))
    search_str = search or "none"
    cache_key = f"items:list:{skip}:{limit}:search_{search_str}:auth_{allowed_ids_str}:enrich_{include_user}"

    cached = await get_cache(cache_key)
    if cached:
        return PaginationResponse(**cached)

    if not allowed_ids:
        return PaginationResponse(items=[], total=0, skip=skip, limit=limit)

    # Count optimise : evite le double-wrap subquery
    count_q = (
        select(func.count(Item.id.distinct()))
        .join(Item.categories)
        .filter(Category.id.in_(allowed_ids))
    )
    base_query = (
        select(Item).options(selectinload(Item.categories))
        .join(Item.categories)
        .filter(Category.id.in_(allowed_ids))
        .distinct()
    )

    # Sequentiel obligatoire : AsyncSession n'accepte pas 2 db.execute() en gather simultane
    total = (await db.execute(count_q)).scalar()
    items = (await db.execute(base_query.offset(skip).limit(limit))).scalars().all()

    if include_user:
        # Parallelisation asyncio.gather uniquement sur les appels HTTP (enrich = users_api)
        enriched_items = await asyncio.gather(*[enrich_item(item, request) for item in items])
    else:
        # Mode rapide : aucun appel HTTP vers users_api, user=null dans la reponse
        enriched_items = [ItemResponse.model_validate(item, from_attributes=True) for item in items]

    result = PaginationResponse(
        items=[i.model_dump() for i in enriched_items],
        total=total,
        skip=skip,
        limit=limit
    )
    await set_cache(cache_key, result.model_dump(), CACHE_TTL)
    return result


@router.get("/{item_id}", response_model=ItemResponse)
async def get_item(
    request: Request,
    item_id: int = Path(..., gt=0, le=2_147_483_647),
    include_user: bool = Query(
        True,
        description=(
            "Enrichit l item avec les infos user via users_api. "
            "True par defaut sur /items/{id} car c est un endpoint de detail. "
            "Mettre False pour une lecture rapide sans user info."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    auth_payload: dict = Depends(verify_jwt)
):
    cache_key = f"items:{item_id}:enrich_{include_user}"
    cached = await get_cache(cache_key)
    if cached:
        return ItemResponse(**cached)

    item = (
        await db.execute(
            select(Item).options(selectinload(Item.categories)).filter(Item.id == item_id)
        )
    ).scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    user_role = auth_payload.get("role", "")
    if user_role not in ("admin", "rh", "service_account"):
        allowed_ids = set(auth_payload.get("allowed_category_ids", []))
        item_categories = {c.id for c in item.categories}
        if not item_categories.intersection(allowed_ids):
            raise HTTPException(status_code=403, detail="Not authorized to view this item")

    if include_user:
        result = await enrich_item(item, request)
    else:
        result = ItemResponse.model_validate(item, from_attributes=True)
    await set_cache(cache_key, result.model_dump(), CACHE_TTL)
    return result


@router.post("/", response_model=ItemResponse, status_code=201)
async def create_item(
    request: Request,
    item: ItemCreate,
    db: AsyncSession = Depends(get_db),
    auth_payload: dict = Depends(verify_jwt)
):
    if not item.category_ids:
        raise HTTPException(status_code=400, detail="Item must have at least one category")

    categories = (await db.execute(select(Category).filter(Category.id.in_(item.category_ids)))).scalars().all()
    if len(categories) != len(set(item.category_ids)):
        raise HTTPException(status_code=400, detail="One or more category IDs are invalid")

    user_role = auth_payload.get("role", "")
    if user_role not in ("admin", "rh", "service_account"):
        allowed_ids = auth_payload.get("allowed_category_ids", [])
        forbidden_ids = [cid for cid in item.category_ids if cid not in allowed_ids]
        if forbidden_ids:
            raise HTTPException(status_code=403, detail=f"User does not have rights for categories: {forbidden_ids}")

    existing = (await db.execute(
        select(Item).options(_sil(Item.categories))
        .filter(Item.user_id == item.user_id, Item.name == item.name)
    )).scalars().first()

    if existing:
        _log.getLogger(__name__).info(
            f"[create_item] Item '{item.name}' (user_id={item.user_id}) déjà existant — retour idempotent.")
        return await enrich_item(existing, request)

    db_item = Item(
        name=item.name,
        description=item.description,
        metadata_json=item.metadata_json,
        user_id=item.user_id,
        categories=categories
    )
    db.add(db_item)
    try:
        await db.commit()
        await db.refresh(db_item)
    except Exception:
        await db.rollback()
        existing = (await db.execute(
            select(Item).options(selectinload(Item.categories))
            .filter(Item.user_id == item.user_id, Item.name == item.name)
        )).scalars().first()
        if existing:
            return await enrich_item(existing, request)
        raise HTTPException(status_code=500, detail="Erreur inattendue lors de la création de l'item")

    await clear_namespace("items:list:")
    await clear_namespace("items:search:")

    db_item = (await db.execute(select(Item).options(selectinload(Item.categories)).filter(Item.id == db_item.id))).scalars().first()  # noqa: E501
    return await enrich_item(db_item, request)


@router.post("/bulk", response_model=List[ItemResponse], status_code=201)
async def create_items_bulk(
    request: Request,
    payload: BulkItemCreate,
    db: AsyncSession = Depends(get_db),
    auth_payload: dict = Depends(verify_jwt)
):
    sem = _get_bulk_sem()
    if sem.locked():
        raise HTTPException(
            status_code=429,
            detail="Service sous charge — réessayer dans quelques secondes."
        )
    async with acquire_shielded(sem):
        return await _create_items_bulk_inner(request, payload, db, auth_payload)


async def _create_items_bulk_inner(
    request: Request,
    payload: BulkItemCreate,
    db: AsyncSession,
    auth_payload: dict,
):
    user_role = auth_payload.get("role", "")
    allowed_ids = auth_payload.get("allowed_category_ids", [])

    all_category_ids = set()
    for item in payload.items:
        all_category_ids.update(item.category_ids)

    if not all_category_ids:
        return []

    categories = (await db.execute(select(Category).filter(Category.id.in_(all_category_ids)))).scalars().all()
    cat_map = {c.id: c for c in categories}

    if len(categories) != len(all_category_ids):
        raise HTTPException(status_code=400, detail="One or more category IDs are invalid")

    if user_role not in ("admin", "rh", "service_account"):
        forbidden_ids = [cid for cid in all_category_ids if cid not in allowed_ids]
        if forbidden_ids:
            raise HTTPException(status_code=403, detail=f"User does not have rights for categories: {forbidden_ids}")

    user_ids = {item.user_id for item in payload.items}
    names = {item.name for item in payload.items}

    existing_items = (await db.execute(
        select(Item).options(_sil(Item.categories))
        .filter(Item.user_id.in_(user_ids), Item.name.in_(names))
    )).scalars().all()

    existing_map = {(i.user_id, i.name): i for i in existing_items}

    new_items = []
    result_item_ids = []

    for item in payload.items:
        key = (item.user_id, item.name)
        if key in existing_map:
            result_item_ids.append(existing_map[key].id)
        else:
            db_item = Item(
                name=item.name,
                description=item.description,
                metadata_json=item.metadata_json,
                user_id=item.user_id,
                categories=[cat_map[cid] for cid in item.category_ids]
            )
            db.add(db_item)
            new_items.append(db_item)

    if new_items:
        try:
            await db.commit()
            for db_item in new_items:
                await db.refresh(db_item)
                result_item_ids.append(db_item.id)

            await clear_namespace("items:list:")
            await clear_namespace("items:search:")
        except IntegrityError as e:
            await db.rollback()
            _log.getLogger(__name__).warning(
                f"Conflit d'intégrité (Bulk), fallback séquentiel idempotent. Details: {e.orig}")

            result_item_ids = []
            for item in payload.items:
                existing = (await db.execute(
                    select(Item).filter(Item.user_id == item.user_id, Item.name == item.name)
                )).scalars().first()

                if existing:
                    result_item_ids.append(existing.id)
                else:
                    db_item = Item(
                        name=item.name,
                        description=item.description,
                        metadata_json=item.metadata_json,
                        user_id=item.user_id,
                        categories=[cat_map[cid] for cid in item.category_ids]
                    )
                    db.add(db_item)
                    try:
                        await db.commit()
                        await db.refresh(db_item)
                        result_item_ids.append(db_item.id)
                    except IntegrityError:
                        await db.rollback()
                        existing = (await db.execute(
                            select(Item).filter(Item.user_id == item.user_id, Item.name == item.name)
                        )).scalars().first()
                        if existing:
                            result_item_ids.append(existing.id)

            await clear_namespace("items:list:")
            await clear_namespace("items:search:")
        except Exception:
            await db.rollback()
            raise HTTPException(status_code=500, detail="Erreur inattendue lors de la création en masse")

    final_items = (
        await db.execute(
            select(Item).options(selectinload(Item.categories))
            .filter(Item.id.in_(result_item_ids))
        )
    ).scalars().all()  # noqa: E501
    # Parallelisation asyncio.gather — evite N awaits sequentiels pour 5 items
    return list(await asyncio.gather(*[enrich_item(db_item, request) for db_item in final_items]))


@router.put("/{item_id}", response_model=ItemResponse)
async def update_item(
    item_update: ItemUpdate,
    request: Request,
    item_id: int = Path(..., gt=0, le=2_147_483_647),
    db: AsyncSession = Depends(get_db),
    auth_payload: dict = Depends(verify_jwt)
):
    item = (await db.execute(select(Item).options(selectinload(Item.categories)).filter(Item.id == item_id))).scalars().first()  # noqa: E501
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    user_role = auth_payload.get("role", "")
    allowed_ids = set(auth_payload.get("allowed_category_ids", []))
    if user_role not in ("admin", "rh", "service_account"):
        item_categories = {c.id for c in item.categories}
        if not item_categories.intersection(allowed_ids):
            raise HTTPException(status_code=403, detail="Not authorized to update this item")

    update_data = item_update.model_dump(exclude_unset=True)
    if "category_ids" in update_data:
        forbidden_ids = [cid for cid in update_data["category_ids"] if cid not in allowed_ids]
        if user_role not in ("admin", "rh", "service_account") and forbidden_ids:
            raise HTTPException(status_code=403, detail=f"User does not have rights for categories: {forbidden_ids}")
        cats = (await db.execute(select(Category).filter(Category.id.in_(update_data["category_ids"])))).scalars().all()
        item.categories = cats
        del update_data["category_ids"]

    for field, value in update_data.items():
        setattr(item, field, value)

    await db.commit()
    await db.refresh(item)
    await clear_namespace(f"items:{item_id}")
    await clear_namespace("items:list:")
    await clear_namespace("items:search:")
    await clear_namespace("items:user:")

    item = (await db.execute(select(Item).options(selectinload(Item.categories)).filter(Item.id == item_id))).scalars().first()  # noqa: E501
    return await enrich_item(item, request)


@router.delete("/{item_id}", status_code=204)
async def delete_item(
    item_id: int = Path(..., gt=0, le=2_147_483_647),
    db: AsyncSession = Depends(get_db),
    auth_payload: dict = Depends(verify_jwt)
):
    item = (await db.execute(select(Item).options(selectinload(Item.categories)).filter(Item.id == item_id))).scalars().first()  # noqa: E501
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    user_role = auth_payload.get("role", "")
    if user_role not in ("admin", "rh", "service_account"):
        allowed_ids = set(auth_payload.get("allowed_category_ids", []))
        item_categories = {c.id for c in item.categories}
        if not item_categories.intersection(allowed_ids):
            raise HTTPException(status_code=403, detail="Not authorized to delete this item")

    # Suppression des relations dans la table d'association
    await db.execute(sa_delete(item_category).where(item_category.c.item_id == item_id))

    await db.delete(item)
    await db.commit()
    await clear_namespace(f"items:{item_id}")
    await clear_namespace("items:list:")
    await clear_namespace("items:search:")
    await clear_namespace("items:user:")
    return
