"""profile_router.py — Import CV, profils, tags, merge, pubsub."""
from src.cvs.schemas import PaginationResponse
import base64
import json
import logging
from datetime import datetime

import httpx
# _svc_config.client/_svc_config.vertex_batch_client via attribute access
import src.services.config as _svc_config
from database import get_db
from fastapi import (APIRouter, BackgroundTasks, Depends, HTTPException, Query,
                     Request)
from opentelemetry.propagate import inject
from sqlalchemy import func
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from src.auth import verify_jwt
from src.cvs.models import CVProfile
from src.cvs.routers._shared import USERS_API_URL
from src.cvs.schemas import (CVFullProfileResponse, CVImportRequest,
                             CVProfileResponse, CVResponse, UserMergeRequest,
                             ExtractedMission)
from src.services.bulk_service import bg_retry_apply
from src.services.config import _CV_CACHE
from src.services.cv_import_service import process_cv_core
from src.services.taxonomy_service import (fetch_prompt,
                                           get_existing_competencies)

_fetch_prompt = fetch_prompt
_get_existing_competencies = get_existing_competencies
_bg_retry_apply = bg_retry_apply

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="",
    tags=["CV Profiles"],
    dependencies=[
        Depends(verify_jwt)])
public_router = APIRouter(prefix="", tags=["CV_Public"])


@router.post("/cache/invalidate-taxonomy")
async def force_invalidate_taxonomy_cache(_: dict = Depends(verify_jwt)):
    """Invalide spécifiquement le contexte sémantique de l'arbre des compétences (Taxonomy Event)."""
    _CV_CACHE["tree_context"] = {"value": None, "expires": datetime.min}
    _CV_CACHE["tree_items"] = {"value": None, "expires": datetime.min}
    logger.info("Cache de taxonomie purgé avec succès (Event-driven).")
    return {"message": "Cache de taxonomie invalidé"}


@router.post("/import", response_model=CVResponse)
async def import_and_analyze_cv(req: CVImportRequest, request: Request, background_tasks: BackgroundTasks,
                                db: AsyncSession = Depends(get_db), token_payload: dict = Depends(verify_jwt)):
    # M1 : Seuls rh, admin et service_account peuvent importer et analyser un CV
    # (protection FinOps : chaque import déclenche un appel Gemini + embedding Vertex AI)
    user_role = token_payload.get("role", "user")
    if user_role not in ("admin", "rh", "service_account"):
        raise HTTPException(
            status_code=403,
            detail="Accès refusé : l'import de CV est réservé aux rôles rh, admin et service_account."
        )
    # 1. Capture Authorization Context (Crucial per RULES[AGENTS.md])
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401,
                            detail="Missing Authorization via CV upload")

    headers = {"Authorization": auth_header}
    inject(headers)  # Mandatory Trace Span Propagation (Agent.md Rule 4)

    return await process_cv_core(
        url=req.url,
        google_access_token=req.google_access_token,
        source_tag=req.source_tag,
        folder_name=req.folder_name,
        headers=headers,
        token_payload=token_payload,
        db=db,
        auth_token=auth_header.replace(
            "Bearer ", "") if "Bearer " in auth_header else auth_header,
        background_tasks=background_tasks, genai_client=_svc_config.client
    )


@public_router.post("/pubsub/import-cv")
async def handle_pubsub_cv_import(
        request: Request, background_tasks: BackgroundTasks):
    from src.services.pubsub_service import PubsubService
    return await PubsubService.handle_pubsub_cv_import(request, background_tasks)


@router.get("/users/tags/map", response_model=dict[str, str])
async def get_all_user_tags(db: AsyncSession = Depends(get_db)):
    """
    Retourne un mapping global {str(user_id): source_tag} pour tous les CVs.
    Pratique pour afficher l'agence dans la liste des utilisateurs du panel admin
    sans problème de N+1 requêtes.
    """
    # Pour garantir le bon tag, on trie par date ascendante,
    # de sorte que le dernier CV écrase les précédents dans le dictionnaire.
    profiles = (await db.execute(
        select(CVProfile.user_id, CVProfile.source_tag)
        .filter(CVProfile.source_tag.is_not(None))
        .order_by(CVProfile.created_at.asc())
    )).all()
    return {str(p.user_id): p.source_tag for p in profiles}


@router.get("/users/tag/{tag}",
            response_model=PaginationResponse[CVProfileResponse])
async def get_users_by_tag(tag: str, skip: int = Query(
        0, ge=0), limit: int = 50, request: Request = None, db: AsyncSession = Depends(get_db)):
    """
    Récupère les profils CV (et user_ids) associés à un tag spécifique (ex: localisation 'Niort').
    Sans redondance par utilisateur (déduplication).
    """
    # On utilise DISTINCT ON pour récupérer uniquement le CV le plus récent
    # par utilisateur
    profiles = (await db.execute(
        select(CVProfile)
        .distinct(CVProfile.user_id)
        .order_by(CVProfile.user_id, CVProfile.created_at.desc())
    )).scalars().all()

    seen_users = set()
    unique_profiles = []

    for p in profiles:
        # On ne garde que les utilisateurs dont le CV le plus récent correspond
        # au tag
        if p.source_tag and tag.lower() in p.source_tag.lower():
            if p.user_id not in seen_users:
                seen_users.add(p.user_id)
                unique_profiles.append(p)
    # Group by user for bulk enrichment
    user_ids = list(seen_users)
    user_enrich_map = {}
    auth_header = request.headers.get("Authorization") if request else None
    headers_downstream = {"Authorization": auth_header} if auth_header else {}
    inject(headers_downstream)

    async with httpx.AsyncClient(timeout=10.0) as http_client:
        for u_id in user_ids:
            try:
                u_res = await http_client.get(f"{USERS_API_URL.rstrip('/')}/{u_id}", headers=headers_downstream)
                if u_res.status_code == 200:
                    user_enrich_map[u_id] = u_res.json()
            except Exception as e:
                logger.warning(
                    f"Failed to fetch user {u_id} for enrichment: {e}")

    total = len(unique_profiles)
    paginated_profiles = unique_profiles[skip:skip + limit]

    return {
        "items": [
            CVProfileResponse(
                user_id=p.user_id,
                source_url=p.source_url,
                source_tag=p.source_tag,
                imported_by_id=p.imported_by_id,
                is_anonymous=user_enrich_map.get(
                    p.user_id, {}).get(
                    "is_anonymous", False),
                full_name=user_enrich_map.get(p.user_id, {}).get("full_name"),
                email=user_enrich_map.get(p.user_id, {}).get("email"),
                username=user_enrich_map.get(p.user_id, {}).get("username")
            ) for p in paginated_profiles
        ],
        "total": total,
        "skip": skip,
        "limit": limit
    }


@router.get("/user/{user_id}",
            response_model=PaginationResponse[CVProfileResponse])
async def get_user_cv(user_id: int, skip: int = Query(
        0, ge=0), limit: int = 50, request: Request = None, db: AsyncSession = Depends(get_db)):
    """
    Récupére le ou les liens source (Google Doc) originaux des CVs associés au collaborateur.
    """
    total = (await db.execute(select(func.count(CVProfile.id)).filter(CVProfile.user_id == user_id))).scalar() or 0
    profiles = (await db.execute(select(CVProfile).filter(CVProfile.user_id == user_id).order_by(CVProfile.created_at.desc()).offset(skip).limit(limit))).scalars().all()
    if not profiles:
        raise HTTPException(status_code=404,
                            detail="Aucun CV trouvé pour cet utilisateur.")

    # Fetch user details for anonymity status
    is_anon = False
    auth_header = request.headers.get("Authorization") if request else None
    headers_downstream = {"Authorization": auth_header} if auth_header else {}
    inject(headers_downstream)
    async with httpx.AsyncClient(timeout=5.0) as http_client:
        try:
            u_res = await http_client.get(f"{USERS_API_URL.rstrip('/')}/{user_id}", headers=headers_downstream)
            if u_res.status_code == 200:
                is_anon = u_res.json().get("is_anonymous", False)
        except Exception as e:
            logger.warning(
                f"Failed to fetch user {user_id} for is_anonymous check: {e}")

    return {
        "items": [
            CVProfileResponse(
                user_id=p.user_id,
                source_url=p.source_url,
                source_tag=p.source_tag,
                imported_by_id=p.imported_by_id,
                is_anonymous=is_anon
            ) for p in profiles
        ],
        "total": total,
        "skip": skip,
        "limit": limit
    }


@router.get("/user/{user_id}/missions",
            response_model=PaginationResponse[ExtractedMission])
async def get_user_missions(user_id: int, skip: int = Query(
        0, ge=0), limit: int = 50, db: AsyncSession = Depends(get_db)):
    """
    Récupère le détail des missions extraites du CV pour un utilisateur.
    """
    profiles = (await db.execute(select(CVProfile).filter(CVProfile.user_id == user_id).order_by(CVProfile.created_at.desc()))).scalars().all()
    if not profiles:
        raise HTTPException(
            status_code=404,
            detail="Aucun profil CV trouvé pour cet utilisateur.")

    merged_missions = []
    seen_mission_keys = set()

    for profile in profiles:
        if not profile.missions:
            continue
        for mission in profile.missions:
            if not isinstance(mission, dict):
                continue
            title = (mission.get("title") or "").strip()
            company_key = (mission.get("company") or "").strip().lower()

            if not title:
                continue

            key = f"{title.lower()}|{company_key}"

            if key not in seen_mission_keys:
                seen_mission_keys.add(key)
                # Assure que title n'est pas None pour la validation Pydantic
                # (title: str)
                mission["title"] = title
                merged_missions.append(mission)

    total = len(merged_missions)
    paginated = merged_missions[skip:skip + limit]
    return {"items": paginated, "total": total, "skip": skip, "limit": limit}


@router.get("/user/{user_id}/details", response_model=CVFullProfileResponse)
async def get_user_cv_details(
        user_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """
    Récupère le profil sémantique complet d'un utilisateur (RAG Context).
    """
    profiles = (await db.execute(
        select(CVProfile)
        .filter(CVProfile.user_id == user_id)
        .order_by(CVProfile.created_at.desc())
    )).scalars().all()

    if not profiles:
        raise HTTPException(
            status_code=404,
            detail="Profil sémantique introuvable pour cet utilisateur.")

    base_profile = profiles[0]

    # Fetch user details for anonymity status
    is_anon = False

    # Propagate Authorization and Tracing (Rule 3 & 4)
    auth_header = request.headers.get("Authorization")
    headers = {"Authorization": auth_header} if auth_header else {}
    inject(headers)

    async with httpx.AsyncClient(timeout=5.0) as http_client:
        try:
            u_res = await http_client.get(f"{USERS_API_URL.rstrip('/')}/{user_id}", headers=headers)
            if u_res.status_code == 200:
                is_anon = u_res.json().get("is_anonymous", False)
        except Exception as e:
            logger.warning(
                f"Failed to fetch user anonymity status for {user_id}: {e}")

    # Inférer seniority depuis years_of_experience si non stocké directement
    years = base_profile.years_of_experience or 0
    if years >= 8:
        inferred_seniority = "Senior"
    elif years >= 3:
        inferred_seniority = "Mid"
    elif years > 0:
        inferred_seniority = "Junior"
    else:
        inferred_seniority = None

    merged_missions = []
    seen_mission_keys = set()
    merged_comp_keywords = set()

    merged_educations = []
    seen_edu_keys = set()

    for p in profiles:
        if p.competencies_keywords:
            merged_comp_keywords.update(p.competencies_keywords)

        if p.educations:
            for edu in p.educations:
                degree = edu.get("degree", "").strip().lower()
                school = edu.get("school", "").strip().lower()
                key = f"{degree}|{school}"
                if key not in seen_edu_keys:
                    seen_edu_keys.add(key)
                    merged_educations.append(edu)

        if not p.missions:
            continue
        for mission in p.missions:
            title = mission.get("title", "").strip().lower()
            company = mission.get("company", "").strip().lower()
            key = f"{title}|{company}"

            if key not in seen_mission_keys:
                seen_mission_keys.add(key)
                merged_missions.append(mission)

    return CVFullProfileResponse(
        user_id=base_profile.user_id,
        summary=base_profile.summary,
        current_role=base_profile.current_role,
        seniority=inferred_seniority,
        years_of_experience=base_profile.years_of_experience,
        competencies_keywords=list(merged_comp_keywords),
        missions=merged_missions,
        educations=merged_educations,
        is_anonymous=is_anon
    )


@router.post("/internal/users/merge")
async def merge_users(req: UserMergeRequest, request: Request,
                      db: AsyncSession = Depends(get_db)):
    """
    Internal endpoint to merge user data.
    Updates cv_profiles.user_id = target_id where user_id = source_id.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401,
                            detail="Missing Authorization via CV merge")

    stmt = sa_update(CVProfile).where(
        CVProfile.user_id == req.source_id).values(
        user_id=req.target_id)
    await db.execute(stmt)

    stmt2 = sa_update(CVProfile).where(
        CVProfile.imported_by_id == req.source_id).values(
        imported_by_id=req.target_id)
    await db.execute(stmt2)

    await db.commit()
    return {"message": f"Successfully migrated CVs from user {req.source_id} to {req.target_id}"}


@public_router.post("/pubsub/user-events")
async def handle_user_pubsub_events(
        request: Request, db: AsyncSession = Depends(get_db)):
    """
    Handle GCP Pub/Sub Push Notifications for CV API.
    """
    try:
        payload = await request.json()
        message = payload.get("message")
        if not message or "data" not in message:
            return {"status": "ignored"}

        data_str = base64.b64decode(message["data"]).decode("utf-8")
        event_data = json.loads(data_str)
        event_type = event_data.get("event")
        data = event_data.get("data", {})

        if event_type == "user.merged":
            source_id = data.get("source_id")
            target_id = data.get("target_id")
            if source_id and target_id:
                stmt = sa_update(CVProfile).where(
                    CVProfile.user_id == source_id).values(
                    user_id=target_id)
                await db.execute(stmt)

                # Update profiles imported BY the user
                stmt2 = sa_update(CVProfile).where(
                    CVProfile.imported_by_id == source_id).values(
                    imported_by_id=target_id)
                await db.execute(stmt2)

                await db.commit()

        return {"status": "processed"}
    except Exception as e:
        logger.error(f"Error processing Pub/Sub event: {e}")
        return {"status": "error", "detail": str(e)}
