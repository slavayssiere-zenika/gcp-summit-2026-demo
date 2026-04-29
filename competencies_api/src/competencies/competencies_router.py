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
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import delete, func, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import aliased

from cache import delete_cache, delete_cache_pattern, get_cache, set_cache
from database import get_db
from src.auth import verify_jwt
from src.competencies.helpers import (
    _generate_aliases_for_competency, check_grammatical_conflict,
    serialize_competency, trigger_taxonomy_cache_invalidation,
)
from src.competencies.models import Competency, CompetencyEvaluation, CompetencySuggestion, user_competency
from src.competencies.schemas import (
    CompetencyCount, CompetencyCreate, CompetencyResponse, CompetencyStatsResponse,
    CompetencyUpdate, CompetencySuggestionCreate, CompetencySuggestionResponse,
    MergeInstruction, PaginationResponse, StatsRequest, SuggestionReviewRequest, TreeImportRequest,
)

logger = logging.getLogger(__name__)
CACHE_TTL = 60

router = APIRouter(prefix="", tags=["competencies"], dependencies=[Depends(verify_jwt)])


@router.get("/", response_model=PaginationResponse)
async def list_competencies(
    skip: int = Query(0, ge=0), limit: int = Query(10, ge=1, le=2000), db: AsyncSession = Depends(get_db)
):
    """Retourne l'arbre complet de compétences (structure hiérarchique paginée sur les racines)."""
    cache_key = f"competencies:tree:list:{skip}:{limit}"
    cached = get_cache(cache_key)
    if cached:
        return PaginationResponse(**cached)

    all_comps = (await db.execute(select(Competency))).scalars().all()
    nodes = {c.id: {"id": c.id, "name": c.name, "description": c.description, "aliases": c.aliases,
                    "parent_id": c.parent_id, "created_at": c.created_at, "sub_competencies": []}
             for c in all_comps}
    roots = []
    for c in all_comps:
        if c.parent_id is None:
            roots.append(nodes[c.id])
        elif c.parent_id in nodes:
            nodes[c.parent_id]["sub_competencies"].append(nodes[c.id])

    roots.sort(key=lambda x: x["id"])
    result = PaginationResponse(items=roots[skip:skip + limit], total=len(roots), skip=skip, limit=limit)
    set_cache(cache_key, result.model_dump(), CACHE_TTL)
    return result


@router.get("/search", response_model=PaginationResponse)
async def search_competencies(query: str = Query(..., min_length=1), limit: int = Query(10, ge=1, le=100), db: AsyncSession = Depends(get_db)):
    """Recherche full-text sur le nom et les aliases de compétences."""
    from sqlalchemy import or_
    cache_key = f"competencies:search:{query}:{limit}"
    cached = get_cache(cache_key)
    if cached:
        return PaginationResponse(**cached)
    results = (await db.execute(
        select(Competency).filter(or_(Competency.name.ilike(f"%{query}%"), Competency.aliases.ilike(f"%{query}%"))).limit(limit)
    )).scalars().all()
    response = PaginationResponse(items=[serialize_competency(c) for c in results], total=len(results), skip=0, limit=limit)
    set_cache(cache_key, response.model_dump(), CACHE_TTL)
    return response


@router.post("/suggestions", response_model=CompetencySuggestionResponse, status_code=201)
async def create_competency_suggestion(payload: CompetencySuggestionCreate, db: AsyncSession = Depends(get_db)):
    """Soumet une suggestion de compétence (idempotente — incrémente occurrence_count si PENDING_REVIEW existant)."""
    name_clean = payload.name.strip()
    if not name_clean:
        raise HTTPException(status_code=422, detail="Le nom de la suggestion ne peut pas être vide.")

    existing = (await db.execute(
        select(CompetencySuggestion)
        .where(func.lower(CompetencySuggestion.name) == name_clean.lower())
        .where(CompetencySuggestion.status == "PENDING_REVIEW")
    )).scalars().first()

    if existing:
        existing.occurrence_count += 1
        existing.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(existing)
        return CompetencySuggestionResponse.model_validate(existing)

    new_suggestion = CompetencySuggestion(
        name=name_clean, source=payload.source,
        context=payload.context[:2000] if payload.context else None,
        status="PENDING_REVIEW", occurrence_count=1,
    )
    db.add(new_suggestion)
    await db.commit()
    await db.refresh(new_suggestion)
    logger.info(f"[Suggestions] Nouvelle suggestion créée : '{name_clean}' (source={payload.source})")
    return CompetencySuggestionResponse.model_validate(new_suggestion)


@router.get("/suggestions", response_model=list[CompetencySuggestionResponse])
async def list_competency_suggestions(
    status: str = Query("PENDING_REVIEW"), limit: int = Query(50, ge=1, le=200), db: AsyncSession = Depends(get_db)
):
    """Liste les suggestions triées par occurrence décroissante (signal marché)."""
    rows = (await db.execute(
        select(CompetencySuggestion).where(CompetencySuggestion.status == status)
        .order_by(CompetencySuggestion.occurrence_count.desc()).limit(limit)
    )).scalars().all()
    return [CompetencySuggestionResponse.model_validate(r) for r in rows]


@router.patch("/suggestions/{suggestion_id}/review", response_model=CompetencySuggestionResponse)
async def review_competency_suggestion(
    suggestion_id: int, payload: SuggestionReviewRequest, bg_tasks: BackgroundTasks,
    request: Request, db: AsyncSession = Depends(get_db), jwt_payload: dict = Depends(verify_jwt),
):
    """(Admin) Accepte ou rejette une suggestion. Si ACCEPT : crée la compétence dans la taxonomie."""
    if jwt_payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Privilèges administrateur requis.")
    if payload.action not in ("ACCEPT", "REJECT"):
        raise HTTPException(status_code=422, detail="action doit être 'ACCEPT' ou 'REJECT'.")

    suggestion = (await db.execute(select(CompetencySuggestion).where(CompetencySuggestion.id == suggestion_id))).scalars().first()
    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggestion introuvable.")
    if suggestion.status != "PENDING_REVIEW":
        raise HTTPException(status_code=409, detail=f"La suggestion est déjà en statut '{suggestion.status}'.")

    if payload.action == "ACCEPT":
        existing_comp = (await db.execute(select(Competency).where(func.lower(Competency.name) == suggestion.name.lower()))).scalars().first()
        if not existing_comp:
            new_comp = Competency(name=suggestion.name,
                                  description=payload.description or f"Importé depuis les suggestions (source: {suggestion.source})",
                                  parent_id=payload.parent_id)
            gen_aliases = await _generate_aliases_for_competency(suggestion.name)
            if gen_aliases:
                new_comp.aliases = gen_aliases
            db.add(new_comp)
            await db.flush()
            delete_cache_pattern("competencies:*")
            trigger_taxonomy_cache_invalidation(bg_tasks, request.headers.get("Authorization"))
        suggestion.status = "ACCEPTED"
    else:
        suggestion.status = "REJECTED"

    suggestion.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(suggestion)
    return CompetencySuggestionResponse.model_validate(suggestion)


@router.get("/{competency_id}", response_model=CompetencyResponse)
async def get_competency(competency_id: int, db: AsyncSession = Depends(get_db)):
    """Retourne une compétence par son ID."""
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
    """Retourne les user_ids associés à cette compétence et ses descendants (CTE récursif)."""
    cache_key = f"competencies:{competency_id}:users"
    cached = get_cache(cache_key)
    if cached:
        return cached
    comp_a = aliased(Competency)
    hierarchy = select(Competency.id).where(Competency.id == competency_id).cte(name="hierarchy", recursive=True)
    hierarchy = hierarchy.union_all(select(comp_a.id).where(comp_a.parent_id == hierarchy.c.id))
    results = (await db.execute(select(user_competency.c.user_id).where(user_competency.c.competency_id.in_(select(hierarchy.c.id))))).all()
    user_ids = list(set([r[0] for r in results]))
    set_cache(cache_key, user_ids, CACHE_TTL)
    return user_ids


@router.post("/bulk_tree", status_code=200)
async def bulk_import_tree(payload: TreeImportRequest, bg_tasks: BackgroundTasks, request: Request, db: AsyncSession = Depends(get_db), jwt_payload: dict = Depends(verify_jwt)):
    """(Admin) Import atomique de la taxonomie complète avec fusion, sweep et archivage des orphelins."""
    if jwt_payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Privilèges administrateur requis.")

    await db.execute(update(Competency).values(parent_id=None))
    await db.flush()
    touched_ids = set()

    async def upsert_level(nodes_dict, parent_id: Optional[int] = None):
        if isinstance(nodes_dict, list):
            for item in nodes_dict:
                if isinstance(item, dict):
                    name = item.get("name")
                    await upsert_level({name: item} if name else item, parent_id)
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
                sub = data.get("sub") or data.get("sub_competencies") if isinstance(data, dict) else None
                if sub:
                    new_comp = Competency(name=name, description=desc, aliases=aliases, parent_id=parent_id)
                    db.add(new_comp)
                    await db.flush()
                    node_id = new_comp.id
                else:
                    conflict = await check_grammatical_conflict(db, name)
                    if conflict:
                        conflict.parent_id = parent_id
                        node_id = conflict.id
                    else:
                        new_leaf = Competency(name=name, description=desc, aliases=aliases, parent_id=parent_id)
                        db.add(new_leaf)
                        await db.flush()
                        node_id = new_leaf.id
                touched_ids.add(node_id)
            if isinstance(data, dict):
                sub = data.get("sub") or data.get("sub_competencies")
                if isinstance(sub, dict):
                    await upsert_level(sub, node_id)
                elif isinstance(sub, list):
                    for item in sub:
                        sub_name = (str(item[0]) if isinstance(item, list) and item else item.get("name", str(item)) if isinstance(item, dict) else str(item)).strip()
                        leaf = (await db.execute(select(Competency).filter(Competency.name.ilike(sub_name)))).scalars().first()
                        if not leaf:
                            leaf = await check_grammatical_conflict(db, sub_name)
                        if leaf:
                            leaf.parent_id = node_id
                            touched_ids.add(leaf.id)
                        else:
                            new_leaf = Competency(name=sub_name, description="Compétence feuille ajoutée via taxonomie", parent_id=node_id)
                            db.add(new_leaf)
                            await db.flush()
                            touched_ids.add(new_leaf.id)

    merge_log = []
    sweep_log = []
    try:
        await upsert_level(payload.tree, None)

        if payload.merges:
            for merge_instr in payload.merges:
                if not merge_instr.merge_from:
                    continue
                canonical = (await db.execute(select(Competency).filter(Competency.name.ilike(merge_instr.canonical)))).scalars().first()
                if not canonical:
                    continue
                for dup_name in merge_instr.merge_from:
                    if dup_name.lower() == merge_instr.canonical.lower():
                        continue
                    dup = (await db.execute(select(Competency).filter(Competency.name.ilike(dup_name)))).scalars().first()
                    if not dup or dup.id == canonical.id:
                        continue
                    for uid in (await db.execute(select(user_competency.c.user_id).where(user_competency.c.competency_id == dup.id))).scalars().all():
                        await db.execute(pg_insert(user_competency).values(user_id=uid, competency_id=canonical.id, created_at=datetime.utcnow()).on_conflict_do_nothing(index_elements=["user_id", "competency_id"]))
                    await db.execute(user_competency.delete().where(user_competency.c.competency_id == dup.id))
                    existing_eval_users = (await db.execute(select(CompetencyEvaluation.user_id).where(CompetencyEvaluation.competency_id == canonical.id))).scalars().all()
                    q = update(CompetencyEvaluation).where(CompetencyEvaluation.competency_id == dup.id)
                    if existing_eval_users:
                        q = q.where(CompetencyEvaluation.user_id.not_in(existing_eval_users))
                    await db.execute(q.values(competency_id=canonical.id))
                    await db.execute(delete(CompetencyEvaluation).where(CompetencyEvaluation.competency_id == dup.id))
                    await db.execute(update(Competency).where(Competency.parent_id == dup.id).values(parent_id=canonical.id))
                    alias_set = set(a.strip() for a in (canonical.aliases or "").split(",") if a.strip())
                    alias_set.add(dup.name)
                    canonical.aliases = ", ".join(sorted(alias_set))
                    await db.delete(dup)
                    touched_ids.discard(dup.id)
                    touched_ids.add(canonical.id)
                    merge_log.append(f"'{dup_name}' → '{canonical.name}'")
                await db.flush()

        if payload.sweep_assignments:
            for assignment in payload.sweep_assignments:
                comp_name = (assignment.competency or "").strip()
                pillar_name = (assignment.pillar or "").strip()
                if not comp_name or not pillar_name:
                    continue
                pillar = (await db.execute(select(Competency).filter(Competency.name.ilike(pillar_name)))).scalars().first()
                if not pillar:
                    continue
                comp = (await db.execute(select(Competency).filter(Competency.name.ilike(comp_name)))).scalars().first()
                if not comp:
                    comp = Competency(name=comp_name, description="Compétence rattachée via Sweep taxonomique", parent_id=pillar.id)
                    db.add(comp)
                    await db.flush()
                    touched_ids.add(comp.id)
                    sweep_log.append(f"'{comp_name}' → '{pillar.name}' (créée)")
                    continue
                comp.parent_id = pillar.id
                touched_ids.add(comp.id)
                touched_ids.add(pillar.id)
                sweep_log.append(f"'{comp_name}' → '{pillar.name}'")
            await db.flush()

        archive_name = "Compétences Archives / Non classées"
        archives = (await db.execute(select(Competency).filter(Competency.name == archive_name))).scalars().first()
        if not archives:
            archives = Competency(name=archive_name, description="Compétences conservées mais absentes de la dernière taxonomie calculée.")
            db.add(archives)
            await db.flush()
        touched_ids.add(archives.id)
        await db.execute(update(Competency).where(Competency.parent_id.is_(None)).where(Competency.id.not_in(touched_ids)).values(parent_id=archives.id))
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'import: {str(e)}")

    delete_cache_pattern("competencies:*")
    trigger_taxonomy_cache_invalidation(bg_tasks, request.headers.get("Authorization"))
    return {"message": f"Taxonomie fusionnée avec succès !{' ' + str(len(merge_log)) + ' fusion(s).' if merge_log else ''}{' ' + str(len(sweep_log)) + ' sweep(s).' if sweep_log else ''}",
            "merges": merge_log}


@router.post("/", response_model=CompetencyResponse, status_code=201)
async def create_competency(competency: CompetencyCreate, bg_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db), jwt_payload: dict = Depends(verify_jwt)):
    """Crée une nouvelle compétence (rôles : admin, rh, service_account)."""
    if jwt_payload.get("role") not in ("admin", "rh", "service_account"):
        raise HTTPException(status_code=403, detail="Accès refusé : rôles admin/rh/service_account requis.")
    competency.name = competency.name.strip()
    if competency.parent_id is not None:
        if not (await db.execute(select(Competency).filter(Competency.id == competency.parent_id))).scalars().first():
            raise HTTPException(status_code=400, detail="Parent competency not found")
    conflict = await check_grammatical_conflict(db, competency.name)
    if conflict:
        if conflict.name.lower() == competency.name.lower():
            return CompetencyResponse(**serialize_competency(conflict))
        raise HTTPException(status_code=409, detail=f"Une variante grammaticale de '{competency.name}' existe déjà : '{conflict.name}'.")
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
        existing = (await db.execute(select(Competency).filter(Competency.name.ilike(competency.name)))).scalars().first()
        if existing:
            return CompetencyResponse(**serialize_competency(existing))
        raise HTTPException(status_code=409, detail="Competency naming conflict unresolved")
    delete_cache_pattern("competencies:tree:*")
    return CompetencyResponse(**serialize_competency(db_comp))


@router.put("/{competency_id}", response_model=CompetencyResponse)
async def update_competency(competency_id: int, competency_update: CompetencyUpdate, db: AsyncSession = Depends(get_db)):
    """Met à jour une compétence (détection de conflits grammaticaux)."""
    db_comp = (await db.execute(select(Competency).filter(Competency.id == competency_id))).scalars().first()
    if not db_comp:
        raise HTTPException(status_code=404, detail="Competency not found")
    if hasattr(competency_update, "parent_id") and competency_update.parent_id == competency_id:
        raise HTTPException(status_code=400, detail="A competency cannot be its own parent")
    for key, value in competency_update.model_dump(exclude_unset=True).items():
        if key == "name" and value and value.strip() != db_comp.name:
            value = value.strip()
            conflict = await check_grammatical_conflict(db, value, exclude_id=competency_id)
            if conflict:
                raise HTTPException(status_code=409, detail=f"Une compétence '{conflict.name}' existe déjà.")
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
async def delete_competency(competency_id: int, db: AsyncSession = Depends(get_db), jwt_payload: dict = Depends(verify_jwt)):
    """(Admin) Supprime une compétence."""
    if jwt_payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Privilèges administrateur requis.")
    db_comp = (await db.execute(select(Competency).filter(Competency.id == competency_id))).scalars().first()
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
    stmt = select(Competency.id, Competency.name, func.count(user_competency.c.user_id).label("count")).join(user_competency, Competency.id == user_competency.c.competency_id)
    if req.user_ids is not None:
        if not req.user_ids:
            return CompetencyStatsResponse(items=[])
        stmt = stmt.where(user_competency.c.user_id.in_(req.user_ids))
    stmt = stmt.group_by(Competency.id, Competency.name)
    stmt = stmt.order_by(func.count(user_competency.c.user_id).asc() if req.sort_order.lower() == "asc" else func.count(user_competency.c.user_id).desc()).limit(req.limit)
    results = (await db.execute(stmt)).all()
    return CompetencyStatsResponse(items=[CompetencyCount(id=r[0], name=r[1], count=r[2]) for r in results])
