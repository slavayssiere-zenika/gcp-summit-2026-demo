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

from shared.cache import clear_namespace, delete_cache, get_cache, set_cache
from shared.database import get_db
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select
import re

from sqlalchemy.orm import aliased
from shared.auth.jwt import verify_jwt
from src.competencies.helpers import (
    _generate_aliases_for_competency,
    check_grammatical_conflict,
    serialize_competency,
    trigger_taxonomy_cache_invalidation,
)
from src.competencies.models import Competency, CompetencySuggestion, user_competency
from sqlalchemy import or_
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
    cached = await get_cache(cache_key)
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
    await set_cache(cache_key, result.model_dump(), CACHE_TTL)
    return result


@router.get("/to-acquire", response_model=List[dict])
async def list_competencies_to_acquire(
    db: AsyncSession = Depends(get_db),
):
    """Étape dédiée RH : liste toutes les compétences marquées is_to_acquire=True.

    Enrichit chaque compétence avec son data-lineage : suggestions ACCEPTED
    de source 'mission' ayant généré cette création, avec le contexte (titre
    de la mission) et le nombre d'occurrences cumulées (signal marché).
    """
    cache_key = "competencies:to-acquire:list"
    cached = await get_cache(cache_key)
    if cached:
        return cached

    comps = (
        await db.execute(select(Competency).where(Competency.is_to_acquire.is_(True)))
    ).scalars().all()

    result = []
    for comp in comps:
        # Récupère toutes les suggestions ACCEPTED associées à ce nom de compétence
        suggestions = (
            await db.execute(
                select(CompetencySuggestion).where(
                    CompetencySuggestion.name.ilike(comp.name),
                    CompetencySuggestion.status == "ACCEPTED",
                    CompetencySuggestion.source == "mission",
                )
            )
        ).scalars().all()

        total_occurrences = sum(s.occurrence_count for s in suggestions)
        lineage_contexts = [
            {
                "context": s.context,
                "occurrence_count": s.occurrence_count,
                "accepted_at": s.updated_at.isoformat() if s.updated_at else None,
            }
            for s in suggestions
        ]

        result.append({
            "id": comp.id,
            "name": comp.name,
            "description": comp.description,
            "aliases": comp.aliases,
            "parent_id": comp.parent_id,
            "created_at": comp.created_at.isoformat() if comp.created_at else None,
            "is_to_acquire": comp.is_to_acquire,
            "total_occurrences": total_occurrences,
            "lineage": lineage_contexts,
        })

    result.sort(key=lambda x: x["total_occurrences"], reverse=True)
    await set_cache(cache_key, result, CACHE_TTL)
    return result


@router.put("/{competency_id}/to-acquire", response_model=dict)
async def set_competency_to_acquire(
    competency_id: int,
    to_acquire: bool,
    db: AsyncSession = Depends(get_db),
    jwt_payload: dict = Depends(verify_jwt),
):
    """(Admin/RH) Force ou désactive manuellement le flag is_to_acquire d'une compétence."""
    if jwt_payload.get("role") not in ("admin", "rh"):
        raise HTTPException(status_code=403, detail="Accès refusé : rôles admin/rh requis.")
    comp = (
        (await db.execute(select(Competency).where(Competency.id == competency_id)))
        .scalars()
        .first()
    )
    if not comp:
        raise HTTPException(status_code=404, detail="Compétence introuvable.")
    comp.is_to_acquire = to_acquire
    await db.commit()
    await delete_cache(f"competencies:{competency_id}")
    await clear_namespace("competencies:to-acquire:")
    return {"id": comp.id, "name": comp.name, "is_to_acquire": comp.is_to_acquire}


@router.get("/search", response_model=PaginationResponse[CompetencyResponse])
async def search_competencies(
    query: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Recherche full-text sur le nom et les aliases de compétences."""

    cache_key = f"competencies:search:{query}:{limit}"
    cached = await get_cache(cache_key)
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
    await set_cache(cache_key, response.model_dump(), CACHE_TTL)
    return response


@router.get("/{competency_id}", response_model=CompetencyResponse)
async def get_competency(competency_id: int, db: AsyncSession = Depends(get_db)):
    """Retourne une compétence par son ID."""
    cache_key = f"competencies:{competency_id}"
    cached = await get_cache(cache_key)
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
    await set_cache(cache_key, result.model_dump(), CACHE_TTL)
    return result


@router.get("/{competency_id}/users", response_model=List[int])
async def list_competency_users(competency_id: int, db: AsyncSession = Depends(get_db)):
    """Retourne les user_ids associés à cette compétence et ses descendants (CTE récursif)."""
    cache_key = f"competencies:{competency_id}:users"
    cached = await get_cache(cache_key)
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
    await set_cache(cache_key, user_ids, CACHE_TTL)
    return user_ids


def clean_generic_suffixes(text: str) -> str:
    """Nettoie les suffixes technologiques très fréquents pour améliorer la déduplication."""
    t = text.lower().strip()
    for suffix in [" framework", " library", " api", " container", " cloud", " system", " tool", " js", " ts"]:
        if t.endswith(suffix):
            t = t[:-len(suffix)].strip()
    return t


@router.post("/", response_model=CompetencyResponse, status_code=201)
async def create_competency(
    competency: CompetencyCreate,
    bg_tasks: BackgroundTasks,
    request: Request,
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

    name_clean = competency.name.strip()

    # 1. Déduplication floue contre les compétences existantes et leurs aliases
    comp_result = await db.execute(select(Competency))
    existing_competencies = comp_result.scalars().all()

    import difflib
    cleaned_name = clean_generic_suffixes(name_clean)
    FUZZY_THRESHOLD = 0.6
    # Longueur minimale du nom canonique pour le check de containment :
    # évite les faux positifs sur des mots trop courts ("Cloud", "Data", "Java").
    CONTAINMENT_MIN_LEN = 6

    def _auto_alias(comp, new_name: str) -> None:
        """Ajoute new_name aux aliases de comp s'il n'y est pas déjà."""
        existing = [a.strip().lower() for a in (comp.aliases or "").split(",") if a.strip()]
        if new_name.lower() not in existing:
            comp.aliases = f"{comp.aliases}, {new_name}" if comp.aliases else new_name

    for comp in existing_competencies:
        cleaned_comp = clean_generic_suffixes(comp.name)

        # ── Check 1 : containment mot-entier (RC2 fix) ───────────────────────
        # Détecte les expansions de nom de marque :
        #   "Google Kubernetes Engine" contient "Kubernetes" (mot entier)
        #   "Docker Swarm Orchestration Tool" contient "Docker" (mot entier)
        # Conditions :
        #   - longueur minimale CONTAINMENT_MIN_LEN (6) sur le nom canonique
        #     → écarte les mots courts génériques (Cloud=5, Agile=5...)
        #   - le nom proposé est PLUS LONG que le canonique (c'est une expansion)
        #     → empêche 'Cloud Run' de matcher 'Cloud' même si Cloud avait 6 chars
        if len(cleaned_comp) >= CONTAINMENT_MIN_LEN and len(cleaned_name) > len(cleaned_comp):
            pattern = r'\b' + re.escape(cleaned_comp) + r'\b'
            if re.search(pattern, cleaned_name, re.IGNORECASE):
                logger.info(
                    "[Create] Containment word-match : '%s' contient '%s' — résolution vers id=%d.",
                    name_clean, comp.name, comp.id
                )
                _auto_alias(comp, name_clean)
                await db.commit()
                await delete_cache(f"competencies:{comp.id}")
                await clear_namespace("competencies:tree:")
                trigger_taxonomy_cache_invalidation(bg_tasks, request)
                return CompetencyResponse(**serialize_competency(comp))

        # ── Check 2 : correspondance floue sur le nom canonique ───────────────
        ratio = difflib.SequenceMatcher(None, cleaned_name, cleaned_comp).ratio()
        if ratio >= FUZZY_THRESHOLD:
            logger.info(
                "[Create] Déduplication floue : '%s' est très proche de la compétence '%s' (ratio=%.2f).",
                name_clean, comp.name, ratio
            )
            _auto_alias(comp, name_clean)
            await db.commit()
            await delete_cache(f"competencies:{comp.id}")
            await clear_namespace("competencies:tree:")
            trigger_taxonomy_cache_invalidation(bg_tasks, request)
            return CompetencyResponse(**serialize_competency(comp))

        # ── Check 3 : correspondance floue sur les aliases ────────────────────
        if comp.aliases:
            for alias in comp.aliases.split(','):
                alias_clean = alias.strip()
                if alias_clean:
                    cleaned_alias = clean_generic_suffixes(alias_clean)
                    ratio_alias = difflib.SequenceMatcher(None, cleaned_name, cleaned_alias).ratio()
                    if ratio_alias >= FUZZY_THRESHOLD:
                        logger.info(
                            "[Create] Déduplication floue : '%s' est très proche de l'alias '%s' de '%s' (ratio=%.2f).",
                            name_clean, alias_clean, comp.name, ratio_alias
                        )
                        return CompetencyResponse(**serialize_competency(comp))

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
    await clear_namespace("competencies:tree:")
    return CompetencyResponse(**serialize_competency(db_comp))


@router.put("/{competency_id}", response_model=CompetencyResponse)
async def update_competency(
    competency_id: int,
    competency_update: CompetencyUpdate,
    db: AsyncSession = Depends(get_db),
    jwt_payload: dict = Depends(verify_jwt),
):
    """Met à jour une compétence (détection de conflits grammaticaux)."""
    if jwt_payload.get("role") not in ("admin", "rh", "service_account"):
        raise HTTPException(
            status_code=403,
            detail="Accès refusé : privilèges admin/rh/service_account requis.",
        )
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
    await delete_cache(f"competencies:{competency_id}")
    await clear_namespace("competencies:tree:")
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
    await delete_cache(f"competencies:{competency_id}")
    await clear_namespace("competencies:tree:")
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
