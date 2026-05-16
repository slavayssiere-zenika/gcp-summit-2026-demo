"""
tree_router.py — Routes d'import et de maintenance de l'arbre taxonomique.

Extrait de competencies_router.py (God module) — 2026-05-14.

Routes :
  POST   /bulk_tree                — Import atomique de taxonomie complète
  POST   /bulk/cleanup-orphans     — Suppression des compétences feuilles orphelines
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from cache import delete_cache_pattern
from shared.database import get_db
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
)
from sqlalchemy import delete, update, or_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from shared.auth.jwt import VerifyJwtOrOidc
from src.competencies.helpers import (
    check_grammatical_conflict,
    trigger_taxonomy_cache_invalidation,
)
from src.competencies.models import Competency, CompetencyEvaluation, user_competency
from src.competencies.schemas import TreeImportRequest

logger = logging.getLogger(__name__)
CACHE_TTL = 60

router = APIRouter(prefix="", tags=["competency-tree"], dependencies=[Depends(VerifyJwtOrOidc())])


@router.post("/bulk_tree", status_code=200)
async def bulk_import_tree(
    payload: TreeImportRequest,
    bg_tasks: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_db),
    jwt_payload: dict = Depends(VerifyJwtOrOidc()),
):
    """(Admin) Import atomique de la taxonomie complète avec fusion, sweep et archivage des orphelins."""
    if jwt_payload.get("role") not in ("admin", "service_account", "scheduler"):
        raise HTTPException(
            status_code=403,
            detail="Privilèges administrateur ou compte de service requis.",
        )

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
            desc = (
                data.get("description", "Généré par Model IA")
                if isinstance(data, dict)
                else "Catégorie"
            )

            if (
                isinstance(data, dict)
                and "merge_from" in data
                and isinstance(data["merge_from"], list)
            ):
                from src.competencies.schemas import MergeInstruction

                merge_from_list = [
                    str(m).strip() for m in data["merge_from"] if str(m).strip()
                ]
                if merge_from_list:
                    if payload.merges is None:
                        payload.merges = []
                    payload.merges.append(
                        MergeInstruction(canonical=name, merge_from=merge_from_list)
                    )

            existing = (
                (
                    await db.execute(
                        select(Competency).filter(Competency.name.ilike(name))
                    )
                )
                .scalars()
                .first()
            )
            if existing:
                existing.parent_id = parent_id
                if aliases:
                    existing.aliases = aliases
                node_id = existing.id
                touched_ids.add(node_id)
            else:
                sub = (
                    data.get("sub") or data.get("sub_competencies")
                    if isinstance(data, dict)
                    else None
                )
                if sub:
                    new_comp = Competency(
                        name=name,
                        description=desc,
                        aliases=aliases,
                        parent_id=parent_id,
                    )
                    db.add(new_comp)
                    await db.flush()
                    node_id = new_comp.id
                else:
                    conflict = await check_grammatical_conflict(db, name)
                    if conflict:
                        conflict.parent_id = parent_id
                        node_id = conflict.id
                    else:
                        new_leaf = Competency(
                            name=name,
                            description=desc,
                            aliases=aliases,
                            parent_id=parent_id,
                        )
                        db.add(new_leaf)
                        await db.flush()
                        node_id = new_leaf.id
                touched_ids.add(node_id)
            sub = None
            if isinstance(data, dict):
                sub = data.get("sub") or data.get("sub_competencies")
            elif isinstance(data, list):
                sub = data

            if isinstance(sub, dict):
                await upsert_level(sub, node_id)
            elif isinstance(sub, list):
                for item in sub:
                    sub_name = (
                        str(item[0])
                        if isinstance(item, list) and item
                        else (
                            item.get("name", str(item))
                            if isinstance(item, dict)
                            else str(item)
                        )
                    ).strip()
                    leaf = (
                        (
                            await db.execute(
                                select(Competency).filter(
                                    Competency.name.ilike(sub_name)
                                )
                            )
                        )
                        .scalars()
                        .first()
                    )
                    if not leaf:
                        leaf = await check_grammatical_conflict(db, sub_name)
                    if leaf:
                        leaf.parent_id = node_id
                        touched_ids.add(leaf.id)
                    else:
                        new_leaf = Competency(
                            name=sub_name,
                            description="Compétence feuille ajoutée via taxonomie",
                            parent_id=node_id,
                        )
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
                canonical = (
                    (
                        await db.execute(
                            select(Competency).filter(
                                Competency.name.ilike(merge_instr.canonical)
                            )
                        )
                    )
                    .scalars()
                    .first()
                )
                if not canonical:
                    continue
                for dup_name in merge_instr.merge_from:
                    if dup_name.lower() == merge_instr.canonical.lower():
                        continue
                    dup = (
                        (
                            await db.execute(
                                select(Competency).filter(
                                    Competency.name.ilike(dup_name)
                                )
                            )
                        )
                        .scalars()
                        .first()
                    )
                    if not dup or dup.id == canonical.id:
                        continue
                    for uid in (
                        (
                            await db.execute(
                                select(user_competency.c.user_id).where(
                                    user_competency.c.competency_id == dup.id
                                )
                            )
                        )
                        .scalars()
                        .all()
                    ):
                        await db.execute(
                            pg_insert(user_competency)
                            .values(
                                user_id=uid,
                                competency_id=canonical.id,
                                created_at=datetime.now(timezone.utc).replace(
                                    tzinfo=None
                                ),
                            )
                            .on_conflict_do_nothing(
                                index_elements=["user_id", "competency_id"]
                            )
                        )
                    await db.execute(
                        user_competency.delete().where(
                            user_competency.c.competency_id == dup.id
                        )
                    )
                    existing_eval_users = (
                        (
                            await db.execute(
                                select(CompetencyEvaluation.user_id).where(
                                    CompetencyEvaluation.competency_id == canonical.id
                                )
                            )
                        )
                        .scalars()
                        .all()
                    )
                    q = update(CompetencyEvaluation).where(
                        CompetencyEvaluation.competency_id == dup.id
                    )
                    if existing_eval_users:
                        q = q.where(
                            CompetencyEvaluation.user_id.not_in(existing_eval_users)
                        )
                    await db.execute(q.values(competency_id=canonical.id))
                    await db.execute(
                        delete(CompetencyEvaluation).where(
                            CompetencyEvaluation.competency_id == dup.id
                        )
                    )
                    await db.execute(
                        update(Competency)
                        .where(Competency.parent_id == dup.id)
                        .values(parent_id=canonical.id)
                    )
                    alias_set = set(
                        a.strip()
                        for a in (canonical.aliases or "").split(",")
                        if a.strip()
                    )
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
                pillar = (
                    (
                        await db.execute(
                            select(Competency).filter(
                                Competency.name.ilike(pillar_name)
                            )
                        )
                    )
                    .scalars()
                    .first()
                )
                if not pillar:
                    logger.warning(
                        f"[bulk_tree] Sweep ignoré : le pilier '{pillar_name}' n'existe pas "
                        f"en base pour la compétence '{comp_name}'."
                    )
                    continue
                comp = (
                    (
                        await db.execute(
                            select(Competency).filter(Competency.name.ilike(comp_name))
                        )
                    )
                    .scalars()
                    .first()
                )
                if not comp:
                    comp = Competency(
                        name=comp_name,
                        description="Compétence rattachée via Sweep taxonomique",
                        parent_id=pillar.id,
                    )
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

        if payload.drops:
            for drop_name in payload.drops:
                drop_name = drop_name.strip()
                if not drop_name:
                    continue
                comp_to_drop = (
                    (
                        await db.execute(
                            select(Competency).filter(Competency.name.ilike(drop_name))
                        )
                    )
                    .scalars()
                    .first()
                )
                if not comp_to_drop:
                    continue

                await db.execute(
                    user_competency.delete().where(
                        user_competency.c.competency_id == comp_to_drop.id
                    )
                )
                await db.execute(
                    delete(CompetencyEvaluation).where(
                        CompetencyEvaluation.competency_id == comp_to_drop.id
                    )
                )
                await db.execute(
                    update(Competency)
                    .where(Competency.parent_id == comp_to_drop.id)
                    .values(parent_id=None)
                )
                await db.delete(comp_to_drop)
                touched_ids.discard(comp_to_drop.id)
                sweep_log.append(f"'{drop_name}' supprimée (Drop)")
            await db.flush()

        archive_name = "Compétences Archives / Non classées"
        archives = (
            (
                await db.execute(
                    select(Competency).filter(Competency.name == archive_name)
                )
            )
            .scalars()
            .first()
        )
        if not archives:
            archives = Competency(
                name=archive_name,
                description="Compétences conservées mais absentes de la dernière taxonomie calculée.",
            )
            db.add(archives)
            await db.flush()
        touched_ids.add(archives.id)
        await db.execute(
            update(Competency)
            .where(Competency.parent_id.is_(None))
            .where(Competency.id.not_in(touched_ids))
            .values(parent_id=archives.id)
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Erreur lors de l'import: {str(e)}"
        )

    delete_cache_pattern("competencies:*")
    trigger_taxonomy_cache_invalidation(bg_tasks, request)
    return {
        "message": f"Taxonomie fusionnée avec succès !{' ' + str(len(merge_log)) + ' fusion(s).' if merge_log else ''}{' ' + str(len(sweep_log)) + ' sweep(s).' if sweep_log else ''}",  # noqa: E501
        "merges": merge_log,
    }


@router.post(
    "/bulk/cleanup-orphans",
    summary="Supprime toutes les compétences feuilles orphelines (sans consultants)",
)
async def cleanup_orphan_competencies(
    request: Request,
    bg_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    jwt_payload: dict = Depends(VerifyJwtOrOidc()),
):
    """Supprime les compétences feuilles qui ne sont liées à aucun consultant (Quality Gate)."""
    if jwt_payload.get("role") not in ("admin", "service_account", "scheduler"):
        raise HTTPException(status_code=403, detail="Accès refusé.")

    try:
        total_deleted = 0
        uc_ids_query = select(user_competency.c.competency_id).distinct()
        # Ne considérer comme liaison valide que les évaluations où l'IA ou le user a mis un score > 0
        ce_ids_query = (
            select(CompetencyEvaluation.competency_id)
            .where(
                or_(
                    CompetencyEvaluation.ai_score > 0,
                    CompetencyEvaluation.user_score > 0,
                )
            )
            .distinct()
        )

        while True:
            # Sous-requête dynamique pour identifier les parents actuels
            parent_ids_query = (
                select(Competency.parent_id)
                .where(Competency.parent_id.is_not(None))
                .distinct()
            )

            # Trouver les compétences feuilles n'ayant aucune liaison
            orphan_query = (
                select(Competency.id)
                .where(Competency.id.not_in(parent_ids_query))
                .where(Competency.id.not_in(uc_ids_query))
                .where(Competency.id.not_in(ce_ids_query))
            )

            orphans = (await db.execute(orphan_query)).scalars().all()

            if not orphans:
                break

            await db.execute(delete(CompetencyEvaluation).where(CompetencyEvaluation.competency_id.in_(orphans)))
            await db.execute(delete(Competency).where(Competency.id.in_(orphans)))
            await db.commit()
            total_deleted += len(orphans)

        if total_deleted > 0:
            delete_cache_pattern("competencies:*")
            trigger_taxonomy_cache_invalidation(bg_tasks, request)

        return {"success": True, "deleted_count": total_deleted}
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Erreur lors du nettoyage: {str(e)}"
        )
