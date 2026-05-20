"""profile_router.py — Import CV, profils, tags, merge, pubsub."""
from src.cvs.schemas import PaginationResponse
import base64
import json
import logging

# _svc_config.client/_svc_config.vertex_batch_client via attribute access
import src.services.config as _svc_config
from shared.database import get_db
from fastapi import (APIRouter, BackgroundTasks, Depends, HTTPException, Query,
                     Request)
from opentelemetry.propagate import inject
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from shared.auth.jwt import verify_jwt
from src.cvs.models import CVProfile
from src.cvs.schemas import (CVFullProfileResponse, CVImportRequest,
                             CVProfileResponse, CVResponse, UserMergeRequest,
                             ExtractedMission)
from src.services.bulk_service import bg_retry_apply
from shared.cache import delete_cache
from src.services.cv_import_service import process_cv_core, process_cv_direct
from src.services.pubsub_service import PubsubService
from src.services.profile_service import ProfileService
from src.services.taxonomy_service import fetch_prompt, get_existing_competencies

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
    await delete_cache("cv_api:tree_context")
    await delete_cache("cv_api:tree_items")
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

    auth_token = auth_header.replace("Bearer ", "") if "Bearer " in auth_header else auth_header

    # Mode perf-test : bypass Drive + identity resolution
    if req.raw_text and req.direct_user_id:
        return await process_cv_direct(
            direct_user_id=req.direct_user_id,
            raw_text=req.raw_text,
            source_tag=req.source_tag or "perf-test",
            headers=headers,
            token_payload=token_payload,
            db=db,
            auth_token=auth_token,
            background_tasks=background_tasks,
            genai_client=_svc_config.client,
        )

    # req.url est garanti non-None ici (model_validator l'a validé au niveau Pydantic)
    return await process_cv_core(
        url=req.url,
        google_access_token=req.google_access_token,
        source_tag=req.source_tag,
        folder_name=req.folder_name,
        headers=headers,
        token_payload=token_payload,
        db=db,
        auth_token=auth_token,
        background_tasks=background_tasks, genai_client=_svc_config.client
    )


@public_router.post("/pubsub/import-cv")
async def handle_pubsub_cv_import(
        request: Request, background_tasks: BackgroundTasks):
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

    auth_header = request.headers.get("Authorization") if request else None
    headers_downstream = {"Authorization": auth_header} if auth_header else {}
    inject(headers_downstream)

    total, responses = await ProfileService.get_users_by_tag(tag, skip, limit, headers_downstream, db)

    return {
        "items": responses,
        "total": total,
        "skip": skip,
        "limit": limit
    }


@router.get("/user/{user_id}",
            response_model=PaginationResponse[CVProfileResponse])
async def get_user_cv(user_id: int, skip: int = Query(
        0, ge=0), limit: int = 50, request: Request = None, db: AsyncSession = Depends(get_db),
        token_payload: dict = Depends(verify_jwt)):

    if token_payload.get("role") not in ("admin", "rh", "service_account") and str(user_id) != str(token_payload.get("sub")):
        raise HTTPException(
            status_code=403,
            detail="Accès refusé : consultation du CV non autorisée."
        )

    auth_header = request.headers.get("Authorization") if request else None
    headers_downstream = {"Authorization": auth_header} if auth_header else {}
    inject(headers_downstream)

    total, responses = await ProfileService.get_user_cv(user_id, skip, limit, headers_downstream, db)
    if total == 0:
        raise HTTPException(status_code=404, detail="Aucun CV trouvé pour cet utilisateur.")

    return {
        "items": responses,
        "total": total,
        "skip": skip,
        "limit": limit
    }


@router.get("/user/{user_id}/missions",
            response_model=PaginationResponse[ExtractedMission])
async def get_user_missions(user_id: int, skip: int = Query(
        0, ge=0), limit: int = 50, db: AsyncSession = Depends(get_db),
        token_payload: dict = Depends(verify_jwt)):

    if token_payload.get("role") not in ("admin", "rh", "service_account") and str(user_id) != str(token_payload.get("sub")):
        raise HTTPException(
            status_code=403,
            detail="Accès refusé : consultation du CV non autorisée."
        )
    total, items = await ProfileService.get_user_missions(user_id, skip, limit, db)
    if total == 0 and not items:
        profiles = (await db.execute(select(CVProfile).filter(CVProfile.user_id == user_id).order_by(CVProfile.created_at.desc()))).scalars().all()
        if not profiles:
            raise HTTPException(status_code=404, detail="Aucun profil CV trouvé pour cet utilisateur.")

    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.get("/user/{user_id}/details", response_model=CVFullProfileResponse)
async def get_user_cv_details(
        user_id: int, request: Request, db: AsyncSession = Depends(get_db),
        token_payload: dict = Depends(verify_jwt)):

    if token_payload.get("role") not in ("admin", "rh", "service_account") and str(user_id) != str(token_payload.get("sub")):
        raise HTTPException(
            status_code=403,
            detail="Accès refusé : consultation du CV non autorisée."
        )

    auth_header = request.headers.get("Authorization")
    headers = {"Authorization": auth_header} if auth_header else {}
    inject(headers)

    profile = await ProfileService.get_user_cv_details(user_id, headers, db)
    if not profile:
        raise HTTPException(
            status_code=404,
            detail="Profil sémantique introuvable pour cet utilisateur.")

    return profile


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


@router.post("/internal/remediate-anonymous-profiles")
async def remediate_anonymous_profiles(
    request: Request,
    background_tasks: BackgroundTasks,
    dry_run: bool = Query(
        True, description="Si True, ne modifie rien — retourne seulement le compte de profils à corriger."),
    token_payload: dict = Depends(verify_jwt),
    db: AsyncSession = Depends(get_db),
):

    if token_payload.get("role") not in ("admin", "service_account"):
        raise HTTPException(status_code=403, detail="Privilèges administrateur requis.")

    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    headers_downstream = {"Authorization": auth_header}
    inject(headers_downstream)

    if dry_run:
        try:
            total, candidates = await ProfileService.remediate_anonymous_profiles_dry(headers_downstream)
            return {
                "dry_run": True,
                "candidates_to_fix": total,
                "profiles": candidates,
                "message": f"{total} profil(s) incorrectement anonymes détectés. Relancez avec dry_run=false pour les corriger."
            }
        except Exception as e:
            raise HTTPException(status_code=502, detail=str(e))

    background_tasks.add_task(ProfileService.run_remediation, dict(headers_downstream))
    return {
        "dry_run": False,
        "status": "accepted",
        "message": "Remédiation lancée en arrière-plan. Consultez les logs Cloud Run pour le détail.",
    }
