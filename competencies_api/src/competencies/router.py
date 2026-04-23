import json
import os
import httpx
import logging
import math
import re
from datetime import datetime, date

from opentelemetry.propagate import inject
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, Request
from sqlalchemy import update, delete, func, desc, asc
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from google import genai
from google.genai import types

import database
from database import get_db
from cache import get_cache, set_cache, delete_cache, delete_cache_pattern
from src.competencies.models import Competency, user_competency, CompetencyEvaluation, CompetencySuggestion
from src.competencies.schemas import (
    CompetencyCreate, CompetencyUpdate, CompetencyResponse,
    PaginationResponse, UserInfo, TreeImportRequest,
    StatsRequest, CompetencyCount, CompetencyStatsResponse,
    CompetencyEvaluationResponse, UserScoreRequest, AiScoreAllResponse,
    AgencyCompetencyItem, AgencyCompetencyCoverage,
    SkillGapItem, SkillGapResult,
    SimilarConsultant, SimilarConsultantsResult,
    CompetencySuggestionCreate, CompetencySuggestionResponse, SuggestionReviewRequest,
    BatchEvaluationRequest, BatchEvaluationResponse, BatchUsersEvaluationRequest,
    MergeInstruction
)

from src.auth import verify_jwt

router = APIRouter(prefix="", tags=["competencies"], dependencies=[Depends(verify_jwt)])

USERS_API_URL = os.getenv("USERS_API_URL", "http://users_api:8000")
CV_API_URL = os.getenv("CV_API_URL", "http://cv_api:8000")
CV_API_URL = os.getenv("CV_API_URL", "http://cv_api:8000")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
CACHE_TTL = 60

logger = logging.getLogger(__name__)

# ── Scoring v2 — Pondération des missions ────────────────────────────────────────
# λ du decay temporel : e^(-λ·N) où N = années depuis la fin de mission
# λ=0.1 → poids 0.90 à 1 an, 0.61 à 5 ans, 0.37 à 10 ans, 0.22 à 15 ans (jamais 0)
COMPETENCY_DECAY_LAMBDA = float(os.getenv("COMPETENCY_DECAY_LAMBDA", "0.1"))

# Bonus de valeur ajoutée par type de mission
MISSION_TYPE_BONUS: dict = {
    "audit": 0.5,
    "conseil": 0.5,
    "accompagnement": 0.3,
    "formation": 0.4,
    "expertise": 0.3,
    "build": 0.0,
}

MISSION_TYPE_LABELS: dict = {
    "audit": "Audit / Diagnostic (valeur ajoutée élevée)",
    "conseil": "Conseil / Advisory (valeur ajoutée élevée)",
    "accompagnement": "Accompagnement / Coaching (valeur ajoutée)",
    "formation": "Formation / Workshop (valeur ajoutée)",
    "expertise": "Expert / Architecte (valeur ajoutée)",
    "build": "Build / Développement (standard)",
}


def _compute_recency_weight(end_date_str: Optional[str]) -> float:
    """Calcule un poids de récence via decay exponentielle e^(-λ·N).

    - end_date_str None ou 'present' → poids 1.0 (mission en cours)
    - end_date_str 'YYYY' ou 'YYYY-MM' → poids selon l'ancienneté
    - Date non parseable → poids neutre 0.7

    Le poids ne descend jamais à 0 — les vieilles missions ont toujours de la valeur.
    """
    if not end_date_str or str(end_date_str).lower() in ("present", "aujourd'hui", "current", "en cours"):
        return 1.0
    try:
        end_year = int(str(end_date_str).strip()[:4])
        years_ago = max(0, date.today().year - end_year)
        return round(math.exp(-COMPETENCY_DECAY_LAMBDA * years_ago), 2)
    except (ValueError, TypeError):
        return 0.7  # Poids neutre si date non parseable


def _parse_duration_months(duration_str: Optional[str]) -> Optional[int]:
    """Parse une durée texte libre en nombre de mois (FR + EN).

    Exemples : '2 ans', '18 mois', '6 months', '1 year 3 months' → retourne un int.
    Retourne None si non parseable.
    """
    if not duration_str:
        return None
    s = str(duration_str).lower()
    total_months = 0
    years_match = re.search(r'(\d+)\s*(?:an|year|yr)', s)
    months_match = re.search(r'(\d+)\s*(?:mois|month|mo)', s)
    weeks_match = re.search(r'(\d+)\s*(?:semaine|week)', s)
    if years_match:
        total_months += int(years_match.group(1)) * 12
    if months_match:
        total_months += int(months_match.group(1))
    if weeks_match:
        total_months += int(weeks_match.group(1)) // 4
    return total_months if total_months > 0 else None


def _duration_multiplier(duration_months: Optional[int]) -> float:
    """Calcule un multiplicateur de durée normalisé entre 0.5 et 1.5.

    6 mois → 0.75 | 12 mois → 1.00 | 24 mois+ → 1.50 (cap).
    Retourne 1.0 (neutre) si la durée est inconnue.
    """
    if duration_months is None:
        return 1.0
    return round(min(1.5, max(0.5, 0.5 + duration_months / 24.0)), 2)


def _get_mission_bonus(mission_type: Optional[str]) -> tuple:
    """Retourne (label_lisible, bonus_score) pour un type de mission."""
    mtype = (mission_type or "build").lower().strip()
    bonus = MISSION_TYPE_BONUS.get(mtype, 0.0)
    label = MISSION_TYPE_LABELS.get(mtype, f"Type: {mtype}")
    return label, bonus


async def _generate_aliases_for_competency(name: str) -> str | None:
    """Génère 3-5 alias pour une compétence via Gemini Flash."""
    try:
        client = genai.Client()
        prompt = (
            f"Tu es un expert technique. Génère 3 à 5 aliases très courts (abréviations, "
            f"variantes de nommage) pour la technologie suivante : '{name}'.\n"
            f"Exemple pour 'Kubernetes' : 'K8s, kube, k8s, Kube, kubernetes'.\n"
            f"Retourne UNIQUEMENT une liste séparée par des virgules, sans aucun texte additionnel."
        )
        res = await client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        if res.text:
            aliases = res.text.strip().strip("'").strip('"')
            logger.info(f"Alias générés pour '{name}' : {aliases}")
            return aliases
    except Exception as e:
        logger.warning(f"Échec de génération d'alias pour '{name}': {e}")
    return None

def trigger_taxonomy_cache_invalidation(bg_tasks: BackgroundTasks, auth_header: str = None):
    """Déclenche de manière asynchrone l'invalidation du cache de la taxonomie dans cv_api."""
    async def invalidate():
        try:
            async with httpx.AsyncClient() as http_client:
                headers = {}
                if auth_header:
                    headers["Authorization"] = auth_header
                inject(headers)
                await http_client.post(f"{CV_API_URL.rstrip('/')}/cache/invalidate-taxonomy", headers=headers, timeout=3.0)
                logger.info("[Cache Sync] Ordre d'invalidation de la taxonomie envoyé à cv_api.")
        except Exception as e:
            logger.warning(f"[Cache Sync] Échec d'invalidation de cv_api: {e}")
    bg_tasks.add_task(invalidate)



def serialize_competency(c: Competency) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "description": c.description,
        "aliases": c.aliases,
        "parent_id": c.parent_id,
        "created_at": c.created_at,
        "sub_competencies": []
    }


def get_grammatical_variants(name: str) -> List[str]:
    """Generates potential singular/plural variants for a given name."""
    name = name.strip()
    variants = {name.lower()}
    
    # Plural to Singular (basic rules)
    if name.lower().endswith('s'):
        variants.add(name[:-1].lower())
    if name.lower().endswith('es'):
        variants.add(name[:-2].lower())
    if name.lower().endswith('x'):
        variants.add(name[:-1].lower())
        
    # Singular to Plural (common suffixes)
    variants.add(name.lower() + 's')
    variants.add(name.lower() + 'es')
    variants.add(name.lower() + 'x')
    
    return list(variants)


async def check_grammatical_conflict(db: AsyncSession, name: str, exclude_id: Optional[int] = None) -> Optional[Competency]:
    """Checks if any grammatical variant of the name already exists in the database."""
    variants = get_grammatical_variants(name)
    stmt = select(Competency).filter(func.lower(Competency.name).in_(variants))
    if exclude_id:
        stmt = stmt.filter(Competency.id != exclude_id)
    result = (await db.execute(stmt)).scalars().first()
    return result


async def get_user_from_api(user_id: int, request: Request) -> UserInfo:
    """Helper to verify user exists in users_api by propagating the original JWT."""
    auth_header = request.headers.get("Authorization")
    headers = {"Authorization": auth_header} if auth_header else {}
    
    inject(headers)

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{USERS_API_URL.rstrip('/')}/{user_id}", headers=headers)
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail=f"User {user_id} not found")
            response.raise_for_status()
            return UserInfo(**response.json())
        except httpx.HTTPError as e:
            raise HTTPException(status_code=503, detail=f"Users API unavailable: {str(e)}")


@router.get("/", response_model=PaginationResponse)
async def list_competencies(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=2000),
    db: AsyncSession = Depends(get_db)
):
    cache_key = f"competencies:tree:list:{skip}:{limit}"
    cached = get_cache(cache_key)
    if cached:
        return PaginationResponse(**cached)

    # Fetch all competencies to build the tree in memory without lazy-loading issues
    all_comps = (await db.execute(select(Competency))).scalars().all()
    
    nodes = {}
    for c in all_comps:
        nodes[c.id] = {
            "id": c.id,
            "name": c.name,
            "description": c.description,
            "aliases": c.aliases,
            "parent_id": c.parent_id,
            "created_at": c.created_at,
            "sub_competencies": []
        }
        
    roots = []
    for c in all_comps:
        if c.parent_id is None:
            roots.append(nodes[c.id])
        else:
            if c.parent_id in nodes:
                nodes[c.parent_id]["sub_competencies"].append(nodes[c.id])
                
    roots.sort(key=lambda x: x["id"])
    total = len(roots)
    paged_roots = roots[skip:skip+limit]
    
    result = PaginationResponse(
        items=paged_roots,
        total=total,
        skip=skip,
        limit=limit
    )
    set_cache(cache_key, result.model_dump(), CACHE_TTL)
    return result


@router.get("/search", response_model=PaginationResponse)
async def search_competencies(
    query: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    cache_key = f"competencies:search:{query}:{limit}"
    cached = get_cache(cache_key)
    if cached:
        return PaginationResponse(**cached)

    from sqlalchemy import or_
    results = (await db.execute(
        select(Competency)
        .filter(
            or_(
                Competency.name.ilike(f"%{query}%"),
                Competency.aliases.ilike(f"%{query}%")
            )
        )
        .limit(limit)
    )).scalars().all()

    response = PaginationResponse(
        items=[serialize_competency(c) for c in results],
        total=len(results),
        skip=0,
        limit=limit
    )
    set_cache(cache_key, response.model_dump(), CACHE_TTL)
    return response


# ============================================================
# Axe 4 : Suggestions de compétences issu du signal marché
# NOTE: Ces routes DOIVENT être définies AVANT /{competency_id}
# pour éviter que FastAPI ne capture "suggestions" comme un int.
# ============================================================

@router.post("/suggestions", response_model=CompetencySuggestionResponse, status_code=201)
async def create_competency_suggestion(
    payload: CompetencySuggestionCreate,
    db: AsyncSession = Depends(get_db),
) -> CompetencySuggestionResponse:
    """Soumet une suggestion de compétence pour révision admin.

    Idempotent : si une suggestion avec le même nom (insensible à la casse)
    existe déjà en statut PENDING_REVIEW, on incrémente son compteur
    d'occurrence plutôt que de créer un doublon.

    Une compétence déjà présente dans la taxonomie officielle ne doit pas
    être soumise (vérification upstream dans missions_api / cv_api).
    """
    name_clean = payload.name.strip()
    if not name_clean:
        raise HTTPException(status_code=422, detail="Le nom de la suggestion ne peut pas être vide.")

    # Idempotence : chercher une suggestion PENDING existante pour ce nom
    existing = (
        await db.execute(
            select(CompetencySuggestion)
            .where(func.lower(CompetencySuggestion.name) == name_clean.lower())
            .where(CompetencySuggestion.status == "PENDING_REVIEW")
        )
    ).scalars().first()

    if existing:
        existing.occurrence_count += 1
        existing.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(existing)
        return CompetencySuggestionResponse.model_validate(existing)

    new_suggestion = CompetencySuggestion(
        name=name_clean,
        source=payload.source,
        context=payload.context[:2000] if payload.context else None,  # Guard: LLM peut générer >500 chars
        status="PENDING_REVIEW",
        occurrence_count=1,
    )
    db.add(new_suggestion)
    await db.commit()
    await db.refresh(new_suggestion)
    logger.info(f"[Suggestions] Nouvelle suggestion créée : '{name_clean}' (source={payload.source})")
    return CompetencySuggestionResponse.model_validate(new_suggestion)


@router.get("/suggestions", response_model=list[CompetencySuggestionResponse])
async def list_competency_suggestions(
    status: str = Query("PENDING_REVIEW", description="Filtre par statut : PENDING_REVIEW | ACCEPTED | REJECTED"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[CompetencySuggestionResponse]:
    """Liste les suggestions de compétences, triées par occurrence décroissante.

    Le classement par `occurrence_count` permet d'identifier en premier les
    compétences les plus fréquemment demandées par les missions client (signal marché).
    """
    rows = (
        await db.execute(
            select(CompetencySuggestion)
            .where(CompetencySuggestion.status == status)
            .order_by(CompetencySuggestion.occurrence_count.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [CompetencySuggestionResponse.model_validate(r) for r in rows]


@router.patch("/suggestions/{suggestion_id}/review", response_model=CompetencySuggestionResponse)
async def review_competency_suggestion(
    suggestion_id: int,
    payload: SuggestionReviewRequest,
    bg_tasks: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_db),
    jwt_payload: dict = Depends(verify_jwt),
) -> CompetencySuggestionResponse:
    """(Admin) Accepte ou rejette une suggestion de compétence.

    Si action='ACCEPT' : crée la compétence dans la taxonomie officielle
    (via create_competency) et marque la suggestion comme ACCEPTED.
    Si action='REJECT' : marque simplement la suggestion comme REJECTED.
    """
    if jwt_payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Privilèges administrateur requis.")

    if payload.action not in ("ACCEPT", "REJECT"):
        raise HTTPException(status_code=422, detail="action doit être 'ACCEPT' ou 'REJECT'.")

    suggestion = (
        await db.execute(select(CompetencySuggestion).where(CompetencySuggestion.id == suggestion_id))
    ).scalars().first()
    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggestion introuvable.")

    if suggestion.status != "PENDING_REVIEW":
        raise HTTPException(
            status_code=409,
            detail=f"La suggestion est déjà en statut '{suggestion.status}' et ne peut plus être traitée.",
        )

    if payload.action == "ACCEPT":
        # Vérifier qu'elle n'existe pas déjà dans la taxonomie
        existing_comp = (
            await db.execute(
                select(Competency).where(func.lower(Competency.name) == suggestion.name.lower())
            )
        ).scalars().first()

        if not existing_comp:
            new_comp = Competency(
                name=suggestion.name,
                description=payload.description or f"Importé depuis les suggestions (source: {suggestion.source})",
                parent_id=payload.parent_id,
            )
            # Auto-génération d'alias
            gen_aliases = await _generate_aliases_for_competency(suggestion.name)
            if gen_aliases:
                new_comp.aliases = gen_aliases

            db.add(new_comp)
            await db.flush()
            logger.info(
                f"[Suggestions] Compétence acceptée et créée : '{suggestion.name}' (id={new_comp.id})"
            )
            delete_cache_pattern("competencies:*")
            trigger_taxonomy_cache_invalidation(bg_tasks, request.headers.get("Authorization"))
        else:
            logger.info(
                f"[Suggestions] '{suggestion.name}' déjà présente dans la taxonomie (id={existing_comp.id}), suggestion acceptée sans création."
            )

        suggestion.status = "ACCEPTED"
    else:
        suggestion.status = "REJECTED"
        logger.info(f"[Suggestions] Suggestion rejetée : '{suggestion.name}'")

    suggestion.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(suggestion)
    return CompetencySuggestionResponse.model_validate(suggestion)


@router.get("/{competency_id}", response_model=CompetencyResponse)
async def get_competency(competency_id: int, db: AsyncSession = Depends(get_db)):
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
    cache_key = f"competencies:{competency_id}:users"
    cached = get_cache(cache_key)
    if cached:
        return cached

    # Fetch user ids associated with this competency and all its children
    hierarchy = select(Competency.id).where(Competency.id == competency_id).cte(name='hierarchy', recursive=True)
    comps_alias = select(Competency.id, Competency.parent_id).cte('comps_alias')
    
    # Alternatively a simpler approach since it's an Async API:
    # Build recursive CTE to find all descendant IDs
    from sqlalchemy.orm import aliased
    comp_a = aliased(Competency)
    hierarchy = select(Competency.id).where(Competency.id == competency_id).cte(name='hierarchy', recursive=True)
    hierarchy = hierarchy.union_all(
        select(comp_a.id).where(comp_a.parent_id == hierarchy.c.id)
    )
    
    results = (await db.execute(
        select(user_competency.c.user_id)
        .where(user_competency.c.competency_id.in_(select(hierarchy.c.id)))
    )).all()
    
    user_ids = list(set([r[0] for r in results]))
    set_cache(cache_key, user_ids, CACHE_TTL)
    return user_ids


@router.post("/bulk_tree", status_code=200)
async def bulk_import_tree(
    payload: TreeImportRequest,
    bg_tasks: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_db),
    jwt_payload: dict = Depends(verify_jwt)
):
    if jwt_payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Privilèges administrateur requis.")
        
    # --- RESET CHAINING ---
    await db.execute(update(Competency).values(parent_id=None))
    await db.flush()
    
    touched_ids = set()
        
    async def upsert_level(nodes_dict, parent_id: Optional[int] = None):
        if isinstance(nodes_dict, list):
            for item in nodes_dict:
                if isinstance(item, dict):
                    name = item.get("name")
                    if name:
                        await upsert_level({name: item}, parent_id)
                    else:
                        await upsert_level(item, parent_id)
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
                is_category = False
                if isinstance(data, dict):
                    sub = data.get("sub") or data.get("sub_competencies")
                    if sub:
                        is_category = True
                
                if is_category:
                    new_comp = Competency(name=name, description=desc, aliases=aliases, parent_id=parent_id)
                    db.add(new_comp)
                    await db.flush()
                    node_id = new_comp.id
                    touched_ids.add(node_id)
                else:
                    conflict = await check_grammatical_conflict(db, name)
                    if conflict:
                        conflict.parent_id = parent_id
                        node_id = conflict.id
                        touched_ids.add(node_id)
                        logger.info(f"Bulk Import: Matched '{name}' with existing variant '{conflict.name}'")
                    else:
                        logger.info(f"Creating missing leaf competency: {name}")
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
                        if isinstance(item, list) and len(item) > 0:
                            sub_name = str(item[0])
                        elif isinstance(item, dict):
                            sub_name = item.get("name", str(item))
                        else:
                            sub_name = str(item)
                        
                        sub_name = sub_name.strip()
                            
                        # Use ilike or grammatical check
                        leaf = (await db.execute(select(Competency).filter(Competency.name.ilike(sub_name)))).scalars().first()
                        if not leaf:
                            leaf = await check_grammatical_conflict(db, sub_name)

                        if leaf:
                            leaf.parent_id = node_id
                            touched_ids.add(leaf.id)
                        else:
                            logger.info(f"Creating missing leaf competency from list: {sub_name}")
                            new_leaf = Competency(
                                name=sub_name, 
                                description="Compétence feuille ajoutée via taxonomie", 
                                parent_id=node_id
                            )
                            db.add(new_leaf)
                            await db.flush()
                            touched_ids.add(new_leaf.id)

    try:
        await upsert_level(payload.tree, None)

        # ── FUSION DES DOUBLONS SÉMANTIQUES ─────────────────────────────────────
        # Exécutée dans la MÊME transaction que l'upsert → atomique.
        # Si la fusion échoue, l'upsert entier est rollbacké.
        merge_log = []
        if payload.merges:
            for merge_instr in payload.merges:
                if not merge_instr.merge_from:
                    continue

                # Trouver le canonique (doit exister après upsert)
                canonical = (
                    await db.execute(
                        select(Competency).filter(Competency.name.ilike(merge_instr.canonical))
                    )
                ).scalars().first()
                if not canonical:
                    logger.warning(
                        f"[BulkTree/Merge] Canonique '{merge_instr.canonical}' introuvable après upsert — ignoré."
                    )
                    continue

                for dup_name in merge_instr.merge_from:
                    if dup_name.lower() == merge_instr.canonical.lower():
                        continue  # sécurité : ne pas fusionner le canonique avec lui-même

                    dup = (
                        await db.execute(
                            select(Competency).filter(Competency.name.ilike(dup_name))
                        )
                    ).scalars().first()
                    if not dup or dup.id == canonical.id:
                        continue

                    # 1. Re-assigner user_competency du doublon → canonique
                    user_ids_with_dup = (
                        await db.execute(
                            select(user_competency.c.user_id)
                            .where(user_competency.c.competency_id == dup.id)
                        )
                    ).scalars().all()

                    for uid in user_ids_with_dup:
                        await db.execute(
                            pg_insert(user_competency)
                            .values(
                                user_id=uid,
                                competency_id=canonical.id,
                                created_at=datetime.utcnow()
                            )
                            .on_conflict_do_nothing(index_elements=["user_id", "competency_id"])
                        )
                    await db.execute(
                        user_competency.delete()
                        .where(user_competency.c.competency_id == dup.id)
                    )

                    # 2. Re-assigner les évaluations sans conflit
                    existing_eval_users = (
                        await db.execute(
                            select(CompetencyEvaluation.user_id)
                            .where(CompetencyEvaluation.competency_id == canonical.id)
                        )
                    ).scalars().all()
                    if existing_eval_users:
                        await db.execute(
                            update(CompetencyEvaluation)
                            .where(CompetencyEvaluation.competency_id == dup.id)
                            .where(CompetencyEvaluation.user_id.not_in(existing_eval_users))
                            .values(competency_id=canonical.id)
                        )
                    else:
                        await db.execute(
                            update(CompetencyEvaluation)
                            .where(CompetencyEvaluation.competency_id == dup.id)
                            .values(competency_id=canonical.id)
                        )
                    # Supprimer les évaluations résiduelles non migrables
                    await db.execute(
                        delete(CompetencyEvaluation)
                        .where(CompetencyEvaluation.competency_id == dup.id)
                    )

                    # 3. Re-parenter les sous-compétences du doublon
                    await db.execute(
                        update(Competency)
                        .where(Competency.parent_id == dup.id)
                        .values(parent_id=canonical.id)
                    )

                    # 4. Enrichir les aliases du canonique avec le nom fusionné
                    existing_aliases = canonical.aliases or ""
                    alias_set = set(a.strip() for a in existing_aliases.split(",") if a.strip())
                    alias_set.add(dup.name)
                    canonical.aliases = ", ".join(sorted(alias_set))

                    # 5. Supprimer le doublon
                    await db.delete(dup)
                    touched_ids.discard(dup.id)  # ne plus référencer l'ID supprimé
                    touched_ids.add(canonical.id)

                    merge_log.append(f"'{dup_name}' → '{canonical.name}'")
                    logger.info(
                        f"[BulkTree/Merge] '{dup_name}' (fusionné) → '{canonical.name}' (id={canonical.id})"
                    )

                await db.flush()  # flush après chaque canonique pour libérer les locks

            if merge_log:
                logger.info(f"[BulkTree/Merge] {len(merge_log)} fusion(s) exécutée(s) : {merge_log}")
        # ── FIN FUSION ──────────────────────────────────────────────────────────

        # --- ORPHAN HANDLING ---
        # Any root competency that was not touched is moved to Archives
        archive_name = "Compétences Archives / Non classées"
        archives = (await db.execute(select(Competency).filter(Competency.name == archive_name))).scalars().first()
        if not archives:
            archives = Competency(name=archive_name, description="Compétences conservées mais absentes de la dernière taxonomie calculée.")
            db.add(archives)
            await db.flush()
        
        archives_id = archives.id
        touched_ids.add(archives_id)
        
        # Update all roots (parent_id IS NULL) that were NOT touched
        await db.execute(
            update(Competency)
            .where(Competency.parent_id.is_(None))
            .where(Competency.id.not_in(touched_ids))
            .values(parent_id=archives_id)
        )
        
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'import: {str(e)}")
        
    delete_cache_pattern("competencies:*")
    trigger_taxonomy_cache_invalidation(bg_tasks, request.headers.get("Authorization"))
    fusions_summary = f" {len(merge_log)} doublon(s) fusionné(s)." if merge_log else ""
    return {"message": f"Taxonomie fusionnée avec succès et orphelins archivés !{fusions_summary}", "merges": merge_log}



@router.post("/", response_model=CompetencyResponse, status_code=201)
async def create_competency(competency: CompetencyCreate, bg_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    # Force normalization to prevent duplicates
    competency.name = competency.name.strip()
    
    if competency.parent_id is not None:
        parent = (await db.execute(select(Competency).filter(Competency.id == competency.parent_id))).scalars().first()
        if not parent:
            raise HTTPException(status_code=400, detail="Parent competency not found")
            
    # Check for direct existence explicitly to prevent ID drops on race conditions
    # This also checks for plural/singular variants
    conflict = await check_grammatical_conflict(db, competency.name)
    if conflict:
        if conflict.name.lower() == competency.name.lower():
            # Exact match (case insensitive) -> return existing
            return CompetencyResponse(**serialize_competency(conflict))
        else:
            # Grammatical variant (singular/plural) -> Conflict 409 per user request
            raise HTTPException(
                status_code=409, 
                detail=f"Une variante grammaticale de '{competency.name}' existe déjà : '{conflict.name}'."
            )
            
    # Auto-génération d'alias
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
        # Fallback safeguard
        existing = (await db.execute(select(Competency).filter(Competency.name.ilike(competency.name)))).scalars().first()
        if existing:
            return CompetencyResponse(**serialize_competency(existing))
        raise HTTPException(status_code=409, detail="Competency naming conflict unresolved")
    
    delete_cache_pattern("competencies:tree:*")
    return CompetencyResponse(**serialize_competency(db_comp))


@router.put("/{competency_id}", response_model=CompetencyResponse)
async def update_competency(
    competency_id: int, 
    competency_update: CompetencyUpdate, 
    db: AsyncSession = Depends(get_db)
):
    db_comp = (await db.execute(select(Competency).filter(Competency.id == competency_id))).scalars().first()
    if not db_comp:
        raise HTTPException(status_code=404, detail="Competency not found")
        
    # Prevent circular recursion if an ID attempts to parent itself (or logic mapping)
    if hasattr(competency_update, "parent_id") and competency_update.parent_id == competency_id:
        raise HTTPException(status_code=400, detail="A competency cannot be its own parent")
        
    for key, value in competency_update.model_dump(exclude_unset=True).items():
        if key == "name" and value is not None:
            value = value.strip()
            if value != db_comp.name:
                # Check if name already exists for another record (grammatical variant check)
                conflict = await check_grammatical_conflict(db, value, exclude_id=competency_id)
                if conflict:
                    raise HTTPException(
                        status_code=409, 
                        detail=f"Une compétence nommée '{value}' ou une variante ('{conflict.name}') existe déjà."
                    )
        setattr(db_comp, key, value)
        
    try:
        await db.commit()
        await db.refresh(db_comp)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Conflit de données : le nom est probablement déjà utilisé.")
    
    delete_cache(f"competencies:{competency_id}")
    delete_cache_pattern("competencies:tree:*")
    return CompetencyResponse(**serialize_competency(db_comp))


@router.delete("/{competency_id}", status_code=204)
async def delete_competency(competency_id: int, db: AsyncSession = Depends(get_db)):
    db_comp = (await db.execute(select(Competency).filter(Competency.id == competency_id))).scalars().first()
    if not db_comp:
        raise HTTPException(status_code=404, detail="Competency not found")
        
    await db.delete(db_comp)
    await db.commit()
    
    delete_cache(f"competencies:{competency_id}")
    delete_cache_pattern("competencies:tree:*")
    return Response(status_code=204)


@router.post("/stats/counts", response_model=CompetencyStatsResponse)
async def get_competency_stats(
    req: StatsRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Calcule les statistiques de compétences (comptage par utilisateur).
    Permet de filtrer sur une cohorte d'utilisateurs spécifique.
    """
    # Base query for counting users per competency
    stmt = (
        select(
            Competency.id,
            Competency.name,
            func.count(user_competency.c.user_id).label("count")
        )
        .join(user_competency, Competency.id == user_competency.c.competency_id)
    )
    
    # Filter by user_ids if provided
    if req.user_ids is not None:
        if not req.user_ids:
            return CompetencyStatsResponse(items=[])
        stmt = stmt.where(user_competency.c.user_id.in_(req.user_ids))
    
    # Group by competency
    stmt = stmt.group_by(Competency.id, Competency.name)
    
    # Sorting
    if req.sort_order.lower() == "asc":
        stmt = stmt.order_by(func.count(user_competency.c.user_id).asc())
    else:
        stmt = stmt.order_by(func.count(user_competency.c.user_id).desc())
        
    # Limit
    stmt = stmt.limit(req.limit)
    
    results = (await db.execute(stmt)).all()
    
    items = [
        CompetencyCount(id=r[0], name=r[1], count=r[2])
        for r in results
    ]
    
    return CompetencyStatsResponse(items=items)


# --- User Associations ---

@router.post("/user/{user_id}/assign/{competency_id}", status_code=201)
async def assign_competency_to_user(
    user_id: int, 
    competency_id: int, 
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    await get_user_from_api(user_id, request)
    competency = (await db.execute(select(Competency).filter(Competency.id == competency_id))).scalars().first()
    if not competency:
        raise HTTPException(status_code=404, detail="Competency not found")
        
    # Assign — atomique via ON CONFLICT DO NOTHING (Golden Rules §1.3 — idempotence)
    # Évite la race condition SELECT+INSERT lors des réingestions batch parallèles.
    stmt = pg_insert(user_competency).values(
        user_id=user_id,
        competency_id=competency_id,
        created_at=datetime.utcnow()
    ).on_conflict_do_nothing(index_elements=["user_id", "competency_id"])
    await db.execute(stmt)
    await db.commit()
    
    delete_cache_pattern(f"competencies:user:{user_id}:*")
    return {"message": f"Competency {competency.name} assigned to user {user_id}"}


@router.delete("/user/{user_id}/remove/{competency_id}", status_code=204)
async def remove_competency_from_user(
    user_id: int, 
    competency_id: int, 
    db: AsyncSession = Depends(get_db)
):
    await db.execute(
        user_competency.delete().where(
            user_competency.c.user_id == user_id,
            user_competency.c.competency_id == competency_id
        )
    )
    await db.commit()
    
    delete_cache_pattern(f"competencies:user:{user_id}:*")
    return Response(status_code=204)


@router.get("/user/{user_id}", response_model=List[CompetencyResponse])
async def list_user_competencies(user_id: int, db: AsyncSession = Depends(get_db)):
    cache_key = f"competencies:user:{user_id}:list"
    cached = get_cache(cache_key)
    if cached:
        return [CompetencyResponse(**c) for c in cached]

    # Join competencies with association table
    results = (await db.execute(select(Competency).join(
        user_competency, 
        Competency.id == user_competency.c.competency_id
    ).filter(user_competency.c.user_id == user_id))).scalars().all()
    
    items = [CompetencyResponse(**serialize_competency(c)) for c in results]
    set_cache(cache_key, [i.model_dump() for i in items], CACHE_TTL)
    return items

from pydantic import BaseModel

class UserMergeRequest(BaseModel):
    source_id: int
    target_id: int

@router.post("/internal/users/merge")
async def merge_users(req: UserMergeRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """
    Internal endpoint to merge user data.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing authorization via competencies merge")
        
    # Get source user competencies
    stmt = select(user_competency.c.competency_id).where(user_competency.c.user_id == req.source_id)
    source_comps = (await db.execute(stmt)).scalars().all()
    
    # Get target user competencies
    stmt_t = select(user_competency.c.competency_id).where(user_competency.c.user_id == req.target_id)
    target_comps = (await db.execute(stmt_t)).scalars().all()
    
    new_comps = set(source_comps) - set(target_comps)
    
    if new_comps:
        for cid in new_comps:
            # ON CONFLICT DO NOTHING pour éviter la race condition inter-workers
            await db.execute(
                pg_insert(user_competency).values(
                    user_id=req.target_id,
                    competency_id=cid,
                    created_at=datetime.utcnow()
                ).on_conflict_do_nothing(index_elements=["user_id", "competency_id"])
            )
            
    # delete source comps
    await db.execute(user_competency.delete().where(user_competency.c.user_id == req.source_id))
    await db.commit()
    
    delete_cache_pattern(f"competencies:user:{req.source_id}:*")
    delete_cache_pattern(f"competencies:user:{req.target_id}:*")
    
    return {"message": f"Successfully migrated competencies from user {req.source_id} to {req.target_id}"}


@router.delete("/user/{user_id}/clear", status_code=204)
async def clear_user_competencies(
    user_id: int, 
    db: AsyncSession = Depends(get_db),
    jwt_payload: dict = Depends(verify_jwt)
):
    """
    (Admin Only) Supprime toutes les assignations de compétences pour un utilisateur.
    """
    if jwt_payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Privilèges administrateur requis.")
        
    await db.execute(
        user_competency.delete().where(user_competency.c.user_id == user_id)
    )
    await db.commit()

    delete_cache_pattern(f"competencies:user:{user_id}:*")
    return Response(status_code=204)


# ============================================================
# Competency Evaluations
# ============================================================

async def _get_or_create_evaluation(
    db: AsyncSession, user_id: int, competency_id: int
) -> CompetencyEvaluation:
    """Retourne l'evaluation existante ou en cree une vide."""
    stmt = select(CompetencyEvaluation).where(
        CompetencyEvaluation.user_id == user_id,
        CompetencyEvaluation.competency_id == competency_id
    )
    ev = (await db.execute(stmt)).scalars().first()
    if not ev:
        ev = CompetencyEvaluation(user_id=user_id, competency_id=competency_id)
        db.add(ev)
        await db.flush()
    return ev


def _serialize_evaluation(ev: CompetencyEvaluation, competency_name: str = "") -> dict:
    """Serialise une evaluation en dict.

    Le parametre competency_name DOIT etre fourni explicitement depuis la requete
    (via JOIN ou chargement eager) — ne jamais acceder a ev.competency.name ici
    car cela declencherait un lazy load synchrone incompatible avec AsyncSession
    (sqlalchemy.exc.MissingGreenlet).
    """
    return {
        "id": ev.id,
        "user_id": ev.user_id,
        "competency_id": ev.competency_id,
        "competency_name": competency_name,
        "ai_score": ev.ai_score,
        "ai_justification": ev.ai_justification,
        "ai_scored_at": ev.ai_scored_at,
        "user_score": ev.user_score,
        "user_comment": ev.user_comment,
        "user_scored_at": ev.user_scored_at,
    }


@router.post("/evaluations/batch/search", response_model=BatchEvaluationResponse)
async def search_batch_evaluations(
    request: BatchEvaluationRequest,
    db: AsyncSession = Depends(get_db)
):
    """Récupère en masse les évaluations pour un utilisateur et une liste de compétences."""
    if not request.competency_ids:
        return BatchEvaluationResponse(evaluations={})

    stmt = (
        select(CompetencyEvaluation, Competency.name.label("comp_name"))
        .join(Competency, CompetencyEvaluation.competency_id == Competency.id)
        .where(
            CompetencyEvaluation.user_id == request.user_id,
            CompetencyEvaluation.competency_id.in_(request.competency_ids)
        )
    )
    rows = (await db.execute(stmt)).all()
    
    eval_dict = {}
    evaluated_ids = set()
    
    for ev, comp_name in rows:
        serialized = _serialize_evaluation(ev, comp_name)
        eval_dict[ev.competency_id] = serialized
        evaluated_ids.add(ev.competency_id)
        
    missing_ids = [cid for cid in request.competency_ids if cid not in evaluated_ids]
    
    if missing_ids:
        comps = (await db.execute(
            select(Competency).where(Competency.id.in_(missing_ids))
        )).scalars().all()
        for c in comps:
            eval_dict[c.id] = {
                "id": 0,
                "user_id": request.user_id,
                "competency_id": c.id,
                "competency_name": c.name,
                "ai_score": None,
                "ai_justification": None,
                "ai_scored_at": None,
                "user_score": None,
                "user_comment": None,
                "user_scored_at": None,
            }

    return BatchEvaluationResponse(evaluations=eval_dict)


@router.post("/evaluations/batch/users", response_model=BatchEvaluationResponse)
async def search_batch_users_evaluations(
    request: BatchUsersEvaluationRequest,
    db: AsyncSession = Depends(get_db)
):
    """Récupère en masse les évaluations pour une compétence et une liste d'utilisateurs."""
    if not request.user_ids:
        return BatchEvaluationResponse(evaluations={})

    stmt = (
        select(CompetencyEvaluation, Competency.name.label("comp_name"))
        .join(Competency, CompetencyEvaluation.competency_id == Competency.id)
        .where(
            CompetencyEvaluation.competency_id == request.competency_id,
            CompetencyEvaluation.user_id.in_(request.user_ids)
        )
    )
    rows = (await db.execute(stmt)).all()
    
    eval_dict = {}
    evaluated_users = set()
    
    # We need the competency name to fill missing users
    comp_name = rows[0][1] if rows else ""
    if not comp_name:
        comp = (await db.execute(select(Competency).where(Competency.id == request.competency_id))).scalars().first()
        comp_name = comp.name if comp else ""
    
    for ev, c_name in rows:
        serialized = _serialize_evaluation(ev, c_name)
        eval_dict[ev.user_id] = serialized
        evaluated_users.add(ev.user_id)
        
    missing_users = [uid for uid in request.user_ids if uid not in evaluated_users]
    
    for uid in missing_users:
        eval_dict[uid] = {
            "id": 0,
            "user_id": uid,
            "competency_id": request.competency_id,
            "competency_name": comp_name,
            "ai_score": None,
            "ai_justification": None,
            "ai_scored_at": None,
            "user_score": None,
            "user_comment": None,
            "user_scored_at": None,
        }

    return BatchEvaluationResponse(evaluations=eval_dict)


@router.get("/evaluations/user/{user_id}", response_model=List[CompetencyEvaluationResponse])
async def list_user_evaluations(
    user_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Liste toutes les evaluations (feuilles uniquement) pour un utilisateur."""
    # Feuilles uniquement : competences sans enfants
    leaf_ids_stmt = (
        select(user_competency.c.competency_id)
        .where(user_competency.c.user_id == user_id)
        .where(
            ~select(Competency.id)
            .where(Competency.parent_id == user_competency.c.competency_id)
            .correlate(user_competency)
            .exists()
        )
    )
    leaf_ids = (await db.execute(leaf_ids_stmt)).scalars().all()

    if not leaf_ids:
        return []

    # JOIN explicite sur Competency pour eviter le lazy load (MissingGreenlet en AsyncSession)
    stmt = (
        select(CompetencyEvaluation, Competency.name.label("comp_name"))
        .join(Competency, CompetencyEvaluation.competency_id == Competency.id)
        .where(
            CompetencyEvaluation.user_id == user_id,
            CompetencyEvaluation.competency_id.in_(leaf_ids)
        )
    )
    rows = (await db.execute(stmt)).all()
    evaluations = [(row[0], row[1]) for row in rows]  # (CompetencyEvaluation, comp_name)

    # Aussi retourner les feuilles sans evaluation (score null)
    evaluated_ids = {ev.competency_id for ev, _ in evaluations}
    missing_ids = [cid for cid in leaf_ids if cid not in evaluated_ids]

    result = [_serialize_evaluation(ev, comp_name) for ev, comp_name in evaluations]

    if missing_ids:
        comps = (await db.execute(
            select(Competency).where(Competency.id.in_(missing_ids))
        )).scalars().all()
        for c in comps:
            result.append({
                "id": 0,
                "user_id": user_id,
                "competency_id": c.id,
                "competency_name": c.name,
                "ai_score": None,
                "ai_justification": None,
                "ai_scored_at": None,
                "user_score": None,
                "user_comment": None,
                "user_scored_at": None,
            })

    return result


@router.get(
    "/evaluations/user/{user_id}/competency/{competency_id}",
    response_model=CompetencyEvaluationResponse
)
async def get_user_competency_evaluation(
    user_id: int,
    competency_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Evaluation d'une competence specifique pour un utilisateur."""
    comp = (await db.execute(
        select(Competency).where(Competency.id == competency_id)
    )).scalars().first()
    if not comp:
        raise HTTPException(status_code=404, detail="Competency not found")

    stmt = select(CompetencyEvaluation).where(
        CompetencyEvaluation.user_id == user_id,
        CompetencyEvaluation.competency_id == competency_id
    )
    ev = (await db.execute(stmt)).scalars().first()
    if not ev:
        return CompetencyEvaluationResponse(
            id=0, user_id=user_id, competency_id=competency_id,
            competency_name=comp.name
        )
    return CompetencyEvaluationResponse(**_serialize_evaluation(ev, comp.name))


@router.post(
    "/evaluations/user/{user_id}/competency/{competency_id}/user-score",
    response_model=CompetencyEvaluationResponse
)
async def set_user_competency_score(
    user_id: int,
    competency_id: int,
    body: UserScoreRequest,
    db: AsyncSession = Depends(get_db)
):
    """Saisie de la note manuelle du consultant pour une competence."""
    comp = (await db.execute(
        select(Competency).where(Competency.id == competency_id)
    )).scalars().first()
    if not comp:
        raise HTTPException(status_code=404, detail="Competency not found")

    ev = await _get_or_create_evaluation(db, user_id, competency_id)
    ev.user_score = body.score
    ev.user_comment = body.comment
    ev.user_scored_at = datetime.utcnow()
    ev.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(ev)

    delete_cache_pattern(f"competencies:evaluations:user:{user_id}:*")
    return CompetencyEvaluationResponse(**_serialize_evaluation(ev, comp.name))


@router.post(
    "/evaluations/user/{user_id}/competency/{competency_id}/ai-score",
    response_model=CompetencyEvaluationResponse
)
async def trigger_ai_score_single(
    user_id: int,
    competency_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Declenche le calcul IA pour une competence specifique."""
    comp = (await db.execute(
        select(Competency).where(Competency.id == competency_id)
    )).scalars().first()
    if not comp:
        raise HTTPException(status_code=404, detail="Competency not found")

    auth_header = request.headers.get("Authorization", "")
    headers = {"Authorization": auth_header}
    inject(headers)

    score, justification = await _compute_ai_score(user_id, comp.name, headers)

    ev = await _get_or_create_evaluation(db, user_id, competency_id)
    ev.ai_score = score
    ev.ai_justification = justification
    ev.ai_scored_at = datetime.utcnow()
    ev.scoring_version = "v2"
    ev.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(ev)

    delete_cache_pattern(f"competencies:evaluations:user:{user_id}:*")
    return CompetencyEvaluationResponse(**_serialize_evaluation(ev, comp.name))



@router.post(
    "/evaluations/user/{user_id}/ai-score-all",
    response_model=AiScoreAllResponse
)
async def trigger_ai_score_all(
    user_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Declenche le calcul IA pour toutes les competences feuilles d'un utilisateur (BackgroundTask).

    Conformément à la règle absolue AGENTS.md §4 : on obtient un service token à longue
    durée de vie via /internal/service-token AVANT de lancer la tâche. Cela garantit
    que le token ne expire pas en cours de traitement et que l'identité du service
    (et non du compte admin) est tracée dans les logs FinOps.
    """
    auth_header = request.headers.get("Authorization", "")

    # Feuilles uniquement
    leaf_ids_stmt = (
        select(user_competency.c.competency_id)
        .where(user_competency.c.user_id == user_id)
        .where(
            ~select(Competency.id)
            .where(Competency.parent_id == user_competency.c.competency_id)
            .correlate(user_competency)
            .exists()
        )
    )
    leaf_ids = (await db.execute(leaf_ids_stmt)).scalars().all()
    logger.info(f"[ai-score-all] start process for user_id={user_id}. Found {len(leaf_ids)} leaf competencies.")

    if not leaf_ids:
        logger.warning(f"[ai-score-all] No leaf competencies found for user={user_id}. Aborting background scoring task.")

    comps_raw = (await db.execute(
        select(Competency.id, Competency.name).where(Competency.id.in_(leaf_ids))
    )).all()
    # Sérialisation en tuples simples (id, name) pour éviter les erreurs cross-session SQLAlchemy
    comp_tuples = [(row[0], row[1]) for row in comps_raw]

    # RÈGLE ABSOLUE AGENTS.md §4 : obtenir un service token avant la background task.
    # Ne jamais passer le bearer utilisateur directement — il peut expirer en mid-flight.
    bg_auth_header = auth_header
    logger.info(f"[ai-score-all] Fetching service token for user={user_id}...")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            svc_res = await client.post(
                f"{USERS_API_URL.rstrip('/')}/internal/service-token",
                headers={"Authorization": auth_header},
            )
            if svc_res.status_code == 200:
                service_token = svc_res.json().get("access_token")
                if service_token:
                    bg_auth_header = f"Bearer {service_token}"
                    logger.info(f"[ai-score-all] Service token obtenu pour user={user_id}")
                else:
                    logger.warning("[ai-score-all] Service token vide — fallback sur JWT utilisateur")
            else:
                logger.warning(
                    f"[ai-score-all] /internal/service-token status={svc_res.status_code} "
                    f"— fallback sur JWT utilisateur (tâche risque d'expirer en mid-flight)"
                )
    except Exception as e:
        logger.warning(f"[ai-score-all] Impossible d'obtenir un service token: {e} — fallback JWT utilisateur")

    headers = {"Authorization": bg_auth_header}
    inject(headers)

    logger.info(f"[ai-score-all] Adding background task for user={user_id} with {len(comp_tuples)} competencies")
    background_tasks.add_task(_score_all_bg, user_id, comp_tuples, dict(headers))

    return AiScoreAllResponse(
        user_id=user_id,
        triggered=len(comp_tuples),
        message=f"Scoring IA lance en arriere-plan pour {len(comp_tuples)} competences."
    )


async def _compute_ai_score(
    user_id: int, competency_name: str, headers: dict
) -> tuple[Optional[float], Optional[str]]:
    """Appelle cv_api pour obtenir les missions puis demande a Gemini de noter la competence.

    Retourne (score: float 0.0-5.0, justification: str) ou (None, message_erreur).
    Le score est arrondi au pas de 0.5 le plus proche.
    """
    api_key = os.environ.get("GOOGLE_API_KEY", "")
    if not api_key:
        logger.warning(f"[_compute_ai_score] GOOGLE_API_KEY non configurée — scoring IA désactivé pour user_id={user_id}, competency='{competency_name}'")
        return None, "GOOGLE_API_KEY non configurée — scoring IA désactivé."

    logger.info(f"[_compute_ai_score] Starting evaluation for user_id={user_id}, competency='{competency_name}'")

    # 1. Récupération des missions depuis cv_api
    missions = []
    try:
        logger.info(f"[_compute_ai_score] Fetching missions from cv_api for user_id={user_id}...")
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(
                f"{CV_API_URL.rstrip('/')}/user/{user_id}/missions",
                headers=headers
            )
            if res.status_code == 200:
                missions = res.json().get("missions", [])
                logger.info(f"[_compute_ai_score] Found {len(missions)} missions for user_id={user_id}")
            else:
                logger.error(f"[_compute_ai_score] Error fetching missions for user {user_id}: HTTP {res.status_code} - {res.text}")
    except Exception as e:
        logger.warning(f"[AI Score] Failed to fetch missions for user {user_id}: {e}")
        return None, "Missions non disponibles (erreur réseau)."

    if not missions:
        logger.warning(f"[_compute_ai_score] No missions found in CV for user_id={user_id}. Assigning minimal score 1.0")
        return 1.0, "Aucune mission trouvée dans le CV — score minimal attribué."

    # 2. Filtrage des missions pertinentes (contenant la compétence)
    comp_norm = competency_name.lower()
    relevant_missions = [
        m for m in missions
        if any(comp_norm in c.lower() or c.lower() in comp_norm
               for c in m.get("competencies", []))
    ]
    # Si aucune mission n'est directement liée, utiliser les 5 premières comme contexte général
    context_missions = relevant_missions if relevant_missions else missions[:5]

    # 3. Construction du contexte enrichi v2 : titre + méta-données de pondération
    def _estimate_duration_from_dates(start: Optional[str], end: Optional[str]) -> Optional[str]:
        """Estime la durée en mois depuis start/end_date si disponibles."""
        if not start or not end:
            return None
        try:
            sy = int(str(start)[:4])
            sm = int(str(start)[5:7]) if len(str(start)) >= 7 else 1
            if str(end).lower() in ("present", "en cours", "current"):
                from datetime import date as _date
                ey, em = _date.today().year, _date.today().month
            else:
                ey = int(str(end)[:4])
                em = int(str(end)[5:7]) if len(str(end)) >= 7 else 12
            months = max(1, (ey - sy) * 12 + (em - sm))
            return f"{months} mois"
        except (ValueError, TypeError):
            return None

    def _format_mission_v2(m: dict) -> str:
        """Formate une mission avec ses méta-données de pondération explicites pour le LLM."""
        title = m.get('title', 'Mission sans titre')
        company = m.get('company', '?')

        # --- Récence (decay exponentiel) ---
        recency_weight = _compute_recency_weight(m.get("end_date"))
        end_date_label = m.get("end_date") or "date inconnue"
        if recency_weight >= 0.9:
            recency_label = f"récente (poids={recency_weight})"
        elif recency_weight >= 0.6:
            recency_label = f"semi-récente (poids={recency_weight})"
        else:
            recency_label = f"ancienne, valeur diminuée (poids={recency_weight})"

        # --- Durée (multiplicateur) ---
        raw_duration = m.get("duration") or _estimate_duration_from_dates(
            m.get("start_date"), m.get("end_date")
        )
        duration_months = _parse_duration_months(raw_duration)
        dur_mult = _duration_multiplier(duration_months)
        dur_label = (
            f"{duration_months} mois (multiplicateur={dur_mult})"
            if duration_months
            else f"durée non précisée (multiplicateur neutre={dur_mult})"
        )

        # --- Type de mission (bonus valeur ajoutée) ---
        mtype_label, mtype_bonus = _get_mission_bonus(m.get("mission_type"))
        bonus_str = f"+{mtype_bonus} bonus" if mtype_bonus > 0 else "pas de bonus"

        parts = [
            f"▶ Mission [{recency_label} | {dur_label} | {mtype_label}, {bonus_str}]",
            f"  Titre : {title} chez {company}",
            f"  Période : {m.get('start_date', '?')} → {end_date_label}",
        ]
        if m.get('description'):
            desc_text = str(m['description'])[:300]
            parts.append(f"  Description : {desc_text}")
        comps = m.get("competencies", [])
        if comps:
            parts.append(f"  Compétences utilisées : {', '.join(comps)}")
        return "\n".join(parts)

    missions_text = "\n\n".join([_format_mission_v2(m) for m in context_missions])
    context_label = "directement liées à cette compétence" if relevant_missions else "générales du consultant"

    # 4. Prompt v2 — le LLM reçoit les poids et les applique lui-même
    prompt = (
        f"Tu es un évaluateur expert de consultants IT et tech (scoring v2 avec pondération)."
        f" Tu dois noter la maîtrise de la compétence '{competency_name}' "
        f"pour ce consultant, de 0.0 à 5.0 (par pas de 0.5).\n\n"
        f"=== RÈGLES DE PONDÉRATION OBLIGATOIRES ===\n"
        f"Tu DOIS appliquer ces poids dans ton évaluation :\n"
        f"1. RÉCENCE : chaque mission affiche un 'poids' entre 0.0 et 1.0.\n"
        f"   - poids proche de 1.0 = mission récente → compte PLEINEMENT\n"
        f"   - poids 0.2-0.4 = mission ancienne → compte mais de façon RÉDUITE\n"
        f"   - une mission ancienne poids=0.3 vaut ~30% d'une mission récente équivalente\n"
        f"2. DURÉE : chaque mission affiche un 'multiplicateur' entre 0.5 et 1.5.\n"
        f"   - multiplicateur > 1.0 = mission longue → profondeur de maîtrise accrue\n"
        f"   - multiplicateur < 1.0 = mission courte → maîtrise plus superficielle\n"
        f"3. TYPE DE MISSION : audit/conseil/accompagnement/formation/expertise affichent\n"
        f"   un bonus (+0.3 à +0.5). Ces missions = maîtrise plus profonde car le consultant\n"
        f"   est en position d'expert exposé à des clients variés. Valorise-les davantage.\n\n"
        f"=== NIVEAUX DE RÉFÉRENCE ===\n"
        f"  - 0.0 : Aucune trace dans le CV\n"
        f"  - 1.0 : Notions de base, mentionné dans des missions anciennes ou courtes\n"
        f"  - 2.0 : Utilisation ponctuelle (1 mission récente ou 2-3 missions anciennes)\n"
        f"  - 3.0 : Maîtrise confirmée, plusieurs missions avec bons poids\n"
        f"  - 4.0 : Expert, missions longues/récentes ou audit/conseil intense\n"
        f"  - 5.0 : Référence reconnue / Lead sur plusieurs missions à forte valeur ajoutée\n\n"
        f"=== MISSIONS {context_label.upper()} AVEC MÉTA-DONNÉES DE PONDÉRATION ===\n"
        f"{missions_text}\n\n"
        f"=== CONSIGNE ===\n"
        f"Réponds UNIQUEMENT en JSON valide avec exactement deux champs :\n"
        f"- score : float entre 0.0 et 5.0, arrondi au pas de 0.5\n"
        f"- justification : string factuelle de 50 à 250 caractères en français, citant\n"
        f"  les missions concrètes et expliquant comment les poids ont influencé le score\n\n"
        f'Exemple : {{"score": 3.5, "justification": "2 missions récentes (poids>0.9) dont 1 audit chez Airbus (bonus +0.5). Mission 2018 comptée à poids réduit 0.4."}}'  # noqa
    )


    # 5. Appel Gemini avec JSON forcé
    try:
        client = genai.Client(api_key=api_key)
        response = await client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1)
        )
        raw = response.text.strip()
        # Nettoyage robuste : extraire le bloc JSON si le modèle ajoute du texte autour
        if not raw.startswith("{"):
            json_match = re.search(r'\{.*\}', raw, re.DOTALL)
            raw = json_match.group(0) if json_match else raw
        data = json.loads(raw)
        score = max(0.0, min(5.0, float(data.get("score", 0.0))))
        # Arrondir au pas de 0.5
        score = round(score * 2) / 2
        justification = str(data.get("justification", ""))[:500]
        logger.info(f"[AI Score] user={user_id} comp='{competency_name}' score={score} (missions_contexte={len(context_missions)})")
        return score, justification
    except json.JSONDecodeError as e:
        logger.error(f"[AI Score] JSON parse error for '{competency_name}': {e} — raw='{raw[:200]}'")
        return None, "Réponse Gemini non parseable en JSON."
    except Exception as e:
        logger.error(f"[AI Score] Gemini call failed for '{competency_name}': {e}")

    return None, "Calcul IA échoué."


async def _score_all_bg(user_id: int, comp_tuples: list[tuple[int, str]], headers: dict):
    """BackgroundTask : score toutes les competences feuilles d'un utilisateur.

    Recoit des tuples (competency_id, competency_name) pour eviter toute
    contamination cross-session SQLAlchemy (les objets ORM de la requete HTTP
    ne peuvent pas etre utilises dans une nouvelle session AsyncSession).
    """
    logger.info(f"[AI Score BG] Background task started for user={user_id} - processing {len(comp_tuples)} competencies")
    async with database.SessionLocal() as db:
        for comp_id, comp_name in comp_tuples:
            try:
                score, justification = await _compute_ai_score(user_id, comp_name, headers)
                ev = await _get_or_create_evaluation(db, user_id, comp_id)
                ev.ai_score = score
                ev.ai_justification = justification
                ev.ai_scored_at = datetime.utcnow()
                ev.scoring_version = "v2"
                ev.updated_at = datetime.utcnow()
                # Pas d'assignation ev.competency = <objet ORM externe> — charger
                # via db.refresh() uniquement si necessaire pour la serialisation.
                await db.commit()
                if score is not None:
                    logger.info(
                        f"[AI Score BG] user={user_id} competency='{comp_name}' "
                        f"comp_id={comp_id} score={score}"
                    )
                else:
                    logger.warning(
                        f"[AI Score BG] score=None user={user_id} competency='{comp_name}' "
                        f"comp_id={comp_id} — raison: {justification}"
                    )
            except Exception as e:
                logger.error(
                    f"[AI Score BG] Failed for user={user_id} comp='{comp_name}': {e}"
                )
                await db.rollback()
    delete_cache_pattern(f"competencies:evaluations:user:{user_id}:*")
    logger.info(f"[AI Score BG] Scoring terminé pour user={user_id} — {len(comp_tuples)} compétences traitées.")


# ============================================================
# Analytics Endpoints (Knowledge Graph Pragmatique)
# ============================================================

@router.get("/analytics/agency-coverage", response_model=AgencyCompetencyCoverage)
async def get_agency_competency_coverage(
    min_count: int = Query(1, ge=1, description="Nombre minimum de consultants possédant la compétence pour apparaitre"),
    limit: int = Query(50, ge=1, le=200),
    request: Request = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Heatmap compétences x agences.

    Pour chaque paire (agence, compétence feuille), retourne le nombre de consultants
    et le score IA moyen. Permet de comparer les agences sur leurs pool de compétences.

    Stratégie :
    1. Récupère les utilisateurs et leur agence depuis users_api (tag category)
    2. Fait un GROUP BY (agence, competency_id) sur user_competency + evaluations
    """
    cache_key = f"competencies:analytics:agency-coverage:{min_count}:{limit}"
    cached = get_cache(cache_key)
    if cached:
        return AgencyCompetencyCoverage(**cached)

    # 1. Récupérer les utilisateurs avec leur agence depuis users_api
    auth_header = request.headers.get("Authorization") if request else None
    headers = {"Authorization": auth_header} if auth_header else {}
    inject(headers)

    agency_map: dict[int, str] = {}  # user_id -> agency_name
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(
                f"{USERS_API_URL.rstrip('/')}/users",
                params={"limit": 500},
                headers=headers
            )
            if res.status_code == 200:
                data = res.json()
                users = data.get("items", data) if isinstance(data, dict) else data
                for u in users:
                    uid = u.get("id")
                    # Chercher le tag d'agence dans les catégories
                    agency = None
                    for tag in (u.get("tags") or []):
                        if isinstance(tag, dict) and tag.get("category") in ("agence", "agency", "Agence"):
                            agency = tag.get("name", tag.get("value"))
                            break
                    if uid and agency:
                        agency_map[uid] = agency
    except Exception as e:
        logger.warning(f"[analytics/agency-coverage] users_api indisponible: {e}")

    if not agency_map:
        return AgencyCompetencyCoverage(items=[], total_consultants=0, total_agencies=0)

    # 2. Jointure SQL : user_competency x competencies x evaluations
    #    Filtre sur les feuilles (pas de sous-compétences) + utilisateurs connus
    from sqlalchemy import case as sa_case

    leaf_subq = (
        select(Competency.id)
        .where(~select(Competency.id).where(Competency.parent_id == Competency.id).correlate().exists())
    ).scalar_subquery()

    stmt = (
        select(
            user_competency.c.user_id,
            user_competency.c.competency_id,
            Competency.name.label("competency_name"),
            CompetencyEvaluation.ai_score,
        )
        .join(Competency, user_competency.c.competency_id == Competency.id)
        .outerjoin(
            CompetencyEvaluation,
            (CompetencyEvaluation.user_id == user_competency.c.user_id)
            & (CompetencyEvaluation.competency_id == user_competency.c.competency_id)
        )
        .where(user_competency.c.user_id.in_(list(agency_map.keys())))
        .where(~Competency.id.in_(
            select(Competency.parent_id).where(Competency.parent_id.isnot(None)).distinct()
        ))
    )
    rows = (await db.execute(stmt)).all()

    # 3. Agrégation Python : (agency, competency) -> {count, scores}
    from collections import defaultdict
    agg: dict[tuple[str, str], dict] = defaultdict(lambda: {"count": 0, "scores": []})
    for row in rows:
        agency = agency_map.get(row.user_id)
        if not agency:
            continue
        key = (agency, row.competency_name)
        agg[key]["count"] += 1
        if row.ai_score is not None:
            agg[key]["scores"].append(row.ai_score)

    items = []
    for (agency, competency), vals in agg.items():
        if vals["count"] < min_count:
            continue
        avg_score = round(sum(vals["scores"]) / len(vals["scores"]), 2) if vals["scores"] else None
        items.append(AgencyCompetencyItem(
            agency=agency,
            competency=competency,
            count=vals["count"],
            avg_ai_score=avg_score
        ))

    items.sort(key=lambda x: (-x.count, x.agency, x.competency))
    items = items[:limit]

    result = AgencyCompetencyCoverage(
        items=items,
        total_consultants=len(agency_map),
        total_agencies=len(set(agency_map.values()))
    )
    set_cache(cache_key, result.model_dump(), 300)  # Cache 5 min
    return result


@router.get("/analytics/skill-gaps", response_model=SkillGapResult)
async def get_skill_gaps(
    user_ids: List[int] = Query(..., description="Liste des user_ids du pool à analyser"),
    competency_ids: Optional[List[int]] = Query(None, description="Liste de compétences cibles (toutes si omis)"),
    min_coverage: float = Query(0.0, ge=0.0, le=1.0, description="Seuil: compétences en-dessous de ce taux de couverture"),
    db: AsyncSession = Depends(get_db)
):
    """
    Gap de compétences dans un pool d'utilisateurs.

    Pour chaque compétence cible, calcule le pourcentage de consultants du pool
    qui la possèdent. Les compétences sous le seuil sont les 'gaps'.

    Cas d'usage :
    - Identifier les compétences manquantes dans une agence spécifique
    - Détecter les lacunes avant un AO (pass user_ids d'une agence)
    """
    if not user_ids:
        return SkillGapResult(gaps=[], pool_size=0)

    pool_size = len(user_ids)

    # Base : compétences cibles (toutes les feuilles, ou celles demandées)
    if competency_ids:
        comps_stmt = select(Competency).where(Competency.id.in_(competency_ids))
    else:
        # Toutes les feuilles
        comps_stmt = select(Competency).where(
            ~Competency.id.in_(
                select(Competency.parent_id).where(Competency.parent_id.isnot(None)).distinct()
            )
        )
    target_comps = (await db.execute(comps_stmt)).scalars().all()

    if not target_comps:
        return SkillGapResult(gaps=[], pool_size=pool_size)

    # Compter les consultants du pool ayant chaque compétence
    count_stmt = (
        select(
            user_competency.c.competency_id,
            func.count(user_competency.c.user_id).label("n")
        )
        .where(user_competency.c.user_id.in_(user_ids))
        .where(user_competency.c.competency_id.in_([c.id for c in target_comps]))
        .group_by(user_competency.c.competency_id)
    )
    count_rows = {r.competency_id: r.n for r in (await db.execute(count_stmt)).all()}

    gaps = []
    for comp in target_comps:
        n = count_rows.get(comp.id, 0)
        coverage = n / pool_size
        if coverage <= min_coverage:
            gaps.append(SkillGapItem(
                competency_id=comp.id,
                competency_name=comp.name,
                consultants_with_skill=n,
                consultants_in_pool=pool_size,
                coverage_pct=round(coverage * 100, 1)
            ))

    gaps.sort(key=lambda x: x.coverage_pct)
    return SkillGapResult(gaps=gaps, pool_size=pool_size)


@router.get("/analytics/similar-consultants/{user_id}", response_model=SimilarConsultantsResult)
async def get_similar_consultants(
    user_id: int,
    top_n: int = Query(5, ge=1, le=20, description="Nombre de consultants similaires à retourner"),
    db: AsyncSession = Depends(get_db)
):
    """
    Trouve les consultants les plus similaires à un consultant de référence.

    Utilise la similarité de Jaccard sur le set de compétences feuilles assignées.
    Jaccard = |A ∩ B| / |A ∪ B|

    Cas d'usage :
    - Trouver un remplaçant sur une mission
    - Identifier un mentor ou pair pour le coaching
    - Staffing de secours (backup consultant)
    """
    # Compétences du consultant de référence (feuilles uniquement)
    leaf_filter = ~Competency.id.in_(
        select(Competency.parent_id).where(Competency.parent_id.isnot(None)).distinct()
    )

    ref_stmt = (
        select(user_competency.c.competency_id, Competency.name)
        .join(Competency, user_competency.c.competency_id == Competency.id)
        .where(user_competency.c.user_id == user_id)
        .where(leaf_filter)
    )
    ref_rows = (await db.execute(ref_stmt)).all()
    ref_set: set[int] = {r.competency_id for r in ref_rows}
    ref_names: dict[int, str] = {r.competency_id: r.name for r in ref_rows}

    if not ref_set:
        return SimilarConsultantsResult(
            reference_user_id=user_id,
            reference_competency_count=0,
            similar_consultants=[]
        )

    # Tous les autres utilisateurs qui ont au moins une compétence commune
    other_stmt = (
        select(user_competency.c.user_id, user_competency.c.competency_id, Competency.name)
        .join(Competency, user_competency.c.competency_id == Competency.id)
        .where(user_competency.c.user_id != user_id)
        .where(user_competency.c.competency_id.in_(ref_set))
        .where(leaf_filter)
    )
    other_rows = (await db.execute(other_stmt)).all()

    # Grouper par user_id
    from collections import defaultdict
    user_comp_sets: dict[int, set[int]] = defaultdict(set)
    user_comp_names: dict[int, dict[int, str]] = defaultdict(dict)
    for row in other_rows:
        user_comp_sets[row.user_id].add(row.competency_id)
        user_comp_names[row.user_id][row.competency_id] = row.name

    # Calcul Jaccard pour chaque candidat
    results: list[SimilarConsultant] = []
    for other_uid, other_set in user_comp_sets.items():
        intersection = ref_set & other_set
        union = ref_set | other_set
        jaccard = len(intersection) / len(union) if union else 0.0
        shared_names = [ref_names.get(cid, user_comp_names[other_uid].get(cid, "")) for cid in intersection]
        results.append(SimilarConsultant(
            user_id=other_uid,
            common_competencies=len(intersection),
            jaccard_score=round(jaccard, 3),
            shared_competency_names=sorted(shared_names)
        ))

    results.sort(key=lambda x: -x.jaccard_score)
    results = results[:top_n]

    return SimilarConsultantsResult(
        reference_user_id=user_id,
        reference_competency_count=len(ref_set),
        similar_consultants=results
    )

