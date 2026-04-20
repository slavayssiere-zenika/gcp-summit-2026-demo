from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks, File, UploadFile, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import asyncio
import database
from .models import Mission
from .schemas import MissionCreateRequest, MissionAnalyzeResponse, TaskResponse, MissionStatusUpdate, StatusHistoryEntry
from .models import MissionStatus, MissionStatusHistory, ALLOWED_TRANSITIONS, STATUS_UPDATE_ROLES
from src.auth import verify_jwt
from opentelemetry.propagate import inject
import os
import json
import httpx
from google import genai
from google.genai import types
import logging
import uuid
import traceback
import re
import urllib.parse

from .cache import get_cached_prompt, force_invalidate_prompt
from .task_state import task_manager
from src.gemini_retry import generate_content_with_retry, embed_content_with_retry

router = APIRouter(prefix="", tags=["Missions"])
public_router = APIRouter(prefix="", tags=["Public"])

GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)
else:
    client = None

CV_API_URL = os.getenv("CV_API_URL", "http://cv_api:8000")
USERS_API_URL = os.getenv("USERS_API_URL", "http://users_api:8000")

async def _process_mission_core(title: str, description: str, url: str, file_bytes: bytes, file_mime: str, headers: dict, user_email: str, auth_token: str, task_id: str, mission_id: int = None):
    logger = logging.getLogger(__name__)
    if not client:
        await task_manager.update_status_failed(task_id, "Gemini non configuré.")
        return

    try:
        async with httpx.AsyncClient(timeout=300.0) as http_client:
            # 1. Fetch from Cache
            extract_prompt = await get_cached_prompt(http_client, "missions_api.extract_mission_info", headers)
            base_staffing_prompt = await get_cached_prompt(http_client, "missions_api.staffing_heuristics", headers)
            
            # Preparation du contenu multimodal
            gemini_contents = [extract_prompt]
            final_description = description or ""

            if url and not file_bytes:
                # URL transform
                if "docs.google.com/document/d/" in url:
                    doc_id = re.search(r"/d/([a-zA-Z0-9_-]+)", url)
                    if doc_id:
                        fetch_url = f"https://docs.google.com/document/d/{doc_id.group(1)}/export?format=txt"
                    else:
                        fetch_url = url
                else:
                    fetch_url = url
                    
                req_heads = headers.copy()
                doc_res = await http_client.get(fetch_url, headers=req_heads, follow_redirects=True)
                if doc_res.status_code == 200:
                    gemini_contents.append(f"Mission Text Document from URL: \n{doc_res.text}")
                    if not final_description:
                        final_description = f"Document chargé depuis: {url}"
                else:
                    logger.warning(f"Failed to fetch document at {fetch_url}, status: {doc_res.status_code}")

            if file_bytes:
                try:
                    # Ingestion multimodale directe via Gemini (Native OCR)
                    part = types.Part.from_bytes(data=file_bytes, mime_type=file_mime)
                    gemini_contents.append(part)
                except Exception as e:
                    logger.error(f"Erreur d'ingestion binaire Gemini: {str(e)}")

                if not final_description:
                    final_description = "Mission chargée via document binaire et processée nativement par Gemini."

            if final_description and not file_bytes and not url:
                gemini_contents.append(f"Description fournie: {final_description}")

            # 2. Extract & Summarize
            model_extract = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
            
            try:
                COMPETENCIES_API_URL_LOCAL = os.getenv("COMPETENCIES_API_URL", "http://competencies_api:8003")
                tree_res = await http_client.get(f"{COMPETENCIES_API_URL_LOCAL.rstrip('/')}/?limit=1000", headers=headers, timeout=2.0)
                if tree_res.status_code == 200:
                    items = tree_res.json().get('items', [])
                    
                    def extract_mid_parents(nodes):
                        parents = []
                        for n in nodes:
                            subs = n.get("sub_competencies", [])
                            if subs:
                                has_leaf_child = any(not s.get("sub_competencies") for s in subs)
                                if has_leaf_child and n.get("parent_id") is not None and n.get("name"):
                                    parents.append(n.get("name"))
                                parents.extend(extract_mid_parents(subs))
                        return parents
                        
                    parent_categories = extract_mid_parents(items)
                    gemini_contents.append(f"\n\nHere is the official list of parent capability domains for this company. Please try to map mission required skills to these parent categories directly:\n{json.dumps(parent_categories)}")
            except Exception as e:
                logger.warning(f"Failed to fetch competencies tree for mission context: {e}")

            res_extract = await generate_content_with_retry(
                client,
                model=model_extract,
                contents=gemini_contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema={
                        "type": "object", 
                        "properties": {
                            "competencies": {
                                "type": "array", 
                                "items": {"type": "string"},
                                "description": "Liste de domaines ou compétences parentes larges (ex: Frontend, DevOps, Cloud) au lieu de technologies de niche."
                            },
                            "summary": {"type": "string", "description": "Résume explicitement le contexte de la mission pour les archives, très utile s'il s'agit d'un PDF."}
                        }, 
                        "required": ["competencies", "summary"]
                    }
                )
            )

            market_mcp_url = os.getenv("MARKET_MCP_URL", "http://market_mcp:8008")

            async def fast_log_finops(action, model, usage):
                try:
                    inject(headers)
                    await http_client.post(
                        f"{market_mcp_url.rstrip('/')}/mcp/call",
                        json={
                            "name": "log_ai_consumption",
                            "arguments": {
                                "user_email": user_email,
                                "action": action,
                                "model": model,
                                "input_tokens": usage.prompt_token_count,
                                "output_tokens": usage.candidates_token_count
                            }
                        },
                        headers=headers
                    )
                except Exception:
                    pass
            await fast_log_finops("RAG_Mission_Extraction", model_extract, res_extract.usage_metadata)
            
            extracted_data = json.loads(res_extract.text)
            extracted_competencies = extracted_data.get("competencies", [])
            
            # Subsituer la description par le résumé de Gemini si on part d'un doc brut
            if not final_description or len(final_description) < 60:
                final_description = extracted_data.get("summary", final_description)
                if isinstance(final_description, list):
                    final_description = " ".join(final_description)

            # 3. CV_API Profile Match
            candidates_data = []
            # On utilise le fallback summary généré s'il y a un pdf pour trouver via pgvector
            search_context = final_description or title
            payload = {"query": search_context, "limit": 6}
            if extracted_competencies:
                payload["skills"] = extracted_competencies

            logger.info(f"Recherche CV_API avec requête POST intégrale")
            cv_res = await http_client.post(f"{CV_API_URL.rstrip('/')}/search", json=payload, headers=headers)
            is_fallback = False
            if cv_res.status_code == 200:
                is_fallback = (cv_res.headers.get("X-Fallback-Full-Scan", "false").lower() == "true")
                missing_embeddings = cv_res.headers.get("X-Missing-Embeddings-Count")
                if missing_embeddings and int(missing_embeddings) > 0:
                    logger.warning(f"⚠️ DATA ANOMALY: {missing_embeddings} profils exclus de la recherche CV en raison d'embeddings manquants. Utilisez la ré-analyse de masse.")
                cv_res_json = cv_res.json()
                logger.info(f"CV_API a répondu avec {len(cv_res_json)} résultats bruts. Fallback_full_scan={is_fallback}")

                async def _enrich_candidate(p: dict) -> dict | None:
                    """Enrichit un candidat avec ses données users_api ET cv_api (seniority, skills)."""
                    u_id = p.get("user_id")
                    try:
                        u_res, cv_details_res = await asyncio.gather(
                            http_client.get(f"{USERS_API_URL.rstrip('/')}/{u_id}", headers=headers),
                            http_client.get(f"{CV_API_URL.rstrip('/')}/user/{u_id}/details", headers=headers),
                        )
                    except Exception as e:
                        logger.warning(f"Enrichissement candidat {u_id} échoué: {e}")
                        return None

                    if u_res.status_code != 200:
                        return None
                    u_info = u_res.json()
                    if not u_info.get("is_active", True):
                        return None

                    # --- Données CV : seniority + skills ---
                    cv_details = {}
                    if cv_details_res.status_code == 200:
                        cv_details = cv_details_res.json()
                    else:
                        logger.debug(f"cv_api /user/{u_id}/details indisponible (HTTP {cv_details_res.status_code}), seniority sera inféré.")

                    # Inférer la seniority depuis years_of_experience si non fournie par l'utilisateur
                    seniority = u_info.get("seniority") or cv_details.get("seniority")
                    if not seniority:
                        years = cv_details.get("years_of_experience") or 0
                        if years >= 8:
                            seniority = "Senior"
                        elif years >= 3:
                            seniority = "Mid"
                        elif years > 0:
                            seniority = "Junior"
                        else:
                            seniority = "Unknown"

                    # Compétences : combiner competencies_keywords du CV et mots-clés extraits
                    skills = (
                        cv_details.get("competencies_keywords")
                        or cv_details.get("skills")
                        or []
                    )

                    return {
                        "user_id": u_id,
                        "full_name": u_info.get("full_name") or f"{u_info.get('first_name')} {u_info.get('last_name')}",
                        "seniority": seniority,
                        "skills": skills,
                        "similarity_score": p.get("similarity_score"),
                        "unavailabilities": u_info.get("unavailability_periods", []),
                    }

                enriched = await asyncio.gather(*[_enrich_candidate(p) for p in cv_res_json])
                candidates_data = [c for c in enriched if c is not None]
                logger.info(f"Candidats enrichis (seniority+skills) : {[c['user_id'] for c in candidates_data]}")
            else:
                logger.error(f"Erreur CV_API: statut {cv_res.status_code}")

            logger.info(f"Candidats préfiltrés (actifs) après recherche: {[c['user_id'] for c in candidates_data]}")

            if not candidates_data:
                skills_str = ", ".join(extracted_competencies) if extracted_competencies else "identifiées pour cette mission"
                proposed_team = [{
                    "user_id": 0,
                    "full_name": "Aucun profil disponible",
                    "role": "Non staffé",
                    "justification": f"Aucun consultant qualifié n'a été trouvé dans la base de connaissance pour les compétences requises : {skills_str}.",
                    "estimated_days": 0
                }]
            else:
                # 4. LLM Staffing
                model_staffing = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
                staffing_prompt = f"{base_staffing_prompt}\nMission: '{title}'. Description: '{final_description}'. Skills: {extracted_competencies}. Candidates: {json.dumps(candidates_data)}."
                res_staffing = await generate_content_with_retry(
                    client,
                    model=model_staffing,
                    contents=staffing_prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema={"type": "array", "items": {"type": "object", "properties": {"user_id": {"type": "integer"}, "full_name": {"type": "string"}, "role": {"type": "string"}, "justification": {"type": "string"}, "estimated_days": {"type": "integer"}}, "required": ["user_id", "full_name", "role", "justification", "estimated_days"]}}
                    )
                )
                await fast_log_finops("RAG_Mission_Staffing", model_staffing, res_staffing.usage_metadata)
                proposed_team = json.loads(res_staffing.text)

            # Embed
            try:
                emb_res = await embed_content_with_retry(client, model=os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"), contents=search_context)
                vector_data = emb_res.embeddings[0].values
            except Exception:
                vector_data = None

            # 5. Save to DB decoupled
            async for db in database.get_db():
                if mission_id:
                    result = await db.execute(select(Mission).where(Mission.id == mission_id))
                    existing_mission = result.scalars().first()
                    if existing_mission:
                        old_status = existing_mission.status
                        existing_mission.title = title
                        existing_mission.description = final_description
                        existing_mission.extracted_competencies = extracted_competencies
                        existing_mission.competencies_keywords = extracted_competencies
                        existing_mission.prefiltered_candidates = candidates_data
                        existing_mission.proposed_team = proposed_team
                        existing_mission.fallback_full_scan = is_fallback
                        existing_mission.semantic_embedding = vector_data
                        existing_mission.status = MissionStatus.STAFFED
                        history_entry = MissionStatusHistory(
                            mission_id=existing_mission.id,
                            old_status=old_status,
                            new_status=MissionStatus.STAFFED,
                            reason="Ré-analyse IA complétée",
                            changed_by=user_email,
                        )
                        db.add(history_entry)
                        await db.commit()
                        await db.refresh(existing_mission)
                        await task_manager.update_status_success(task_id, existing_mission.id)
                        from metrics import MISSIONS_CREATED_TOTAL
                        MISSIONS_CREATED_TOTAL.labels(status="reanalyze_success").inc()
                        break

                new_mission = Mission(
                    title=title,
                    description=final_description,
                    extracted_competencies=extracted_competencies,
                    competencies_keywords=extracted_competencies,
                    prefiltered_candidates=candidates_data,
                    proposed_team=proposed_team,
                    semantic_embedding=vector_data,
                    fallback_full_scan=is_fallback,
                    status=MissionStatus.STAFFED,
                )
                db.add(new_mission)
                await db.flush()  # get new_mission.id before adding history
                history_entry = MissionStatusHistory(
                    mission_id=new_mission.id,
                    old_status=MissionStatus.ANALYSIS_IN_PROGRESS,
                    new_status=MissionStatus.STAFFED,
                    reason="Analyse IA complétée",
                    changed_by=user_email,
                )
                db.add(history_entry)
                await db.commit()
                await db.refresh(new_mission)
                await task_manager.update_status_success(task_id, new_mission.id)
                from metrics import MISSIONS_CREATED_TOTAL
                MISSIONS_CREATED_TOTAL.labels(status="success").inc()
                break

    except Exception as e:
        logger.error(f"Erreur task {task_id}: {traceback.format_exc()}")
        await task_manager.update_status_failed(task_id, str(e))
        from metrics import MISSIONS_CREATED_TOTAL
        MISSIONS_CREATED_TOTAL.labels(status="staffing_failed").inc()


@router.post("/missions", response_model=TaskResponse, status_code=202)
async def create_and_analyze_mission(
    req: Request, 
    bg_tasks: BackgroundTasks, 
    title: str = Form(...),
    description: str = Form(None),
    url: str = Form(None),
    file: UploadFile = File(None),
    db: AsyncSession = Depends(database.get_db), 
    token_payload: dict = Depends(verify_jwt)
):
    # Tracing & Auth Capture
    auth_header = req.headers.get("Authorization")
    headers = {"Authorization": auth_header} if auth_header else {}
    inject(headers)
    
    auth_token = auth_header.replace("Bearer ", "") if auth_header and "Bearer " in auth_header else auth_header
    user_email = token_payload.get("sub", "unknown@zenika.com")
    
    file_bytes = None
    file_mime = None
    if file:
        # Validation du MIME type (anti-spoofing) — AGENTS.md §2 / F-07
        ALLOWED_MIME_TYPES = {
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword",
            "text/plain",
        }
        if file.content_type and file.content_type not in ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=415,
                detail=f"Type de fichier non supporté : {file.content_type}. Types acceptés : PDF, DOCX, TXT."
            )
        file_bytes = await file.read()
        # Limite de taille : 10 MB max (anti-OOM sur Cloud Run)
        MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
        if len(file_bytes) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail="Fichier trop volumineux (maximum 10 MB autorisé)."
            )
        file_mime = file.content_type or "application/pdf"
    
    # Create mission in DB immediately with ANALYSIS_IN_PROGRESS status
    new_mission_pre = Mission(
        title=title,
        description=description or "",
        extracted_competencies=[],
        status=MissionStatus.ANALYSIS_IN_PROGRESS,
    )
    db.add(new_mission_pre)
    await db.flush()  # get id before adding history
    history_entry = MissionStatusHistory(
        mission_id=new_mission_pre.id,
        old_status=None,
        new_status=MissionStatus.ANALYSIS_IN_PROGRESS,
        reason="Mission créée — analyse IA lancée",
        changed_by=user_email,
    )
    db.add(history_entry)
    await db.commit()
    provisional_mission_id = new_mission_pre.id

    # Generate ID and initialize tracking
    task_id = str(uuid.uuid4())
    await task_manager.initialize_task(task_id, title)

    # Launch background processing
    bg_tasks.add_task(
        _process_mission_core,
        title, description, url, file_bytes, file_mime, headers,
        user_email, auth_token, task_id, provisional_mission_id
    )

    return {"task_id": task_id, "status": "processing"}

@router.post("/missions/{mission_id}/reanalyze", response_model=TaskResponse, status_code=202)
async def reanalyze_mission(
    mission_id: int,
    req: Request, 
    bg_tasks: BackgroundTasks, 
    db: AsyncSession = Depends(database.get_db), 
    token_payload: dict = Depends(verify_jwt)
):
    # Tracing & Auth Capture
    auth_header = req.headers.get("Authorization")
    headers = {"Authorization": auth_header} if auth_header else {}
    inject(headers)
    
    auth_token = auth_header.replace("Bearer ", "") if auth_header and "Bearer " in auth_header else auth_header
    user_email = token_payload.get("sub", "unknown@zenika.com")
    
    result = await db.execute(select(Mission).where(Mission.id == mission_id))
    m = result.scalars().first()
    if not m:
        raise HTTPException(status_code=404, detail="Mission introuvable")

    # Generate ID and initialize tracking
    task_id = str(uuid.uuid4())
    await task_manager.initialize_task(task_id, f"Re-analyse: {m.title}")
    
    # Launch background processing
    bg_tasks.add_task(_process_mission_core, m.title, m.description, None, None, None, headers, user_email, auth_token, task_id, mission_id)
    
    return {"task_id": task_id, "status": "processing"}

@router.get("/missions/task/{task_id}")
async def get_mission_task_status(task_id: str, _: dict = Depends(verify_jwt)):
    stat = await task_manager.get_task(task_id)
    if not stat:
        raise HTTPException(status_code=404, detail="Task introuvable.")
    return stat

@router.post("/cache/invalidate")
async def force_invalidate(prompt_key: str, token_payload: dict = Depends(verify_jwt)):
    await force_invalidate_prompt(prompt_key)
    return {"message": "Cache invalidé"}

@router.get("/missions", response_model=list[MissionAnalyzeResponse])
async def list_missions(
    db: AsyncSession = Depends(database.get_db),
    status: str = None,
    _: dict = Depends(verify_jwt),
):
    query = select(Mission).order_by(Mission.created_at.desc())
    if status:
        query = query.where(Mission.status == status)
    result = await db.execute(query)
    missions = result.scalars().all()

    response = []
    for m in missions:
        response.append({
            "id": m.id,
            "title": m.title,
            "description": m.description,
            "status": m.status or MissionStatus.STAFFED,
            "extracted_competencies": m.extracted_competencies or [],
            "prefiltered_candidates": m.prefiltered_candidates or [],
            "proposed_team": m.proposed_team or [],
            "fallback_full_scan": m.fallback_full_scan,
        })
    return response


@router.patch("/missions/{mission_id}/status")
async def update_mission_status(
    mission_id: int,
    payload: MissionStatusUpdate,
    req: Request,
    db: AsyncSession = Depends(database.get_db),
    token_payload: dict = Depends(verify_jwt),
):
    """Modifie le statut d'une mission (réservé aux rôles commercial et admin).
    Vérifie la validité de la transition avant application et enregistre l'audit.
    """
    user_role = token_payload.get("role", "user")
    user_email = token_payload.get("sub", "unknown@zenika.com")

    if user_role not in STATUS_UPDATE_ROLES:
        raise HTTPException(
            status_code=403,
            detail=f"Accès refusé : seuls les rôles {STATUS_UPDATE_ROLES} peuvent modifier le statut d'une mission.",
        )

    result = await db.execute(select(Mission).where(Mission.id == mission_id))
    mission = result.scalars().first()
    if not mission:
        raise HTTPException(status_code=404, detail="Mission introuvable")

    current_status = mission.status or MissionStatus.STAFFED
    new_status = payload.status

    # Validate transition
    allowed = ALLOWED_TRANSITIONS.get(current_status, [])
    if new_status not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"Transition invalide : '{current_status}' → '{new_status}'. Transitions autorisées : {allowed}",
        )

    # Apply status change
    old_status = current_status
    mission.status = new_status

    # Persist audit entry
    history_entry = MissionStatusHistory(
        mission_id=mission_id,
        old_status=old_status,
        new_status=new_status,
        reason=payload.reason,
        changed_by=user_email,
    )
    db.add(history_entry)
    await db.commit()
    await db.refresh(mission)

    return {
        "id": mission.id,
        "status": mission.status,
        "old_status": old_status,
        "changed_by": user_email,
        "reason": payload.reason,
    }


@router.get("/missions/{mission_id}/status/history", response_model=list[StatusHistoryEntry])
async def get_mission_status_history(
    mission_id: int,
    db: AsyncSession = Depends(database.get_db),
    token_payload: dict = Depends(verify_jwt),
):
    """Retourne l'historique complet des changements de statut d'une mission (audit trail)."""
    result = await db.execute(select(Mission).where(Mission.id == mission_id))
    mission = result.scalars().first()
    if not mission:
        raise HTTPException(status_code=404, detail="Mission introuvable")

    history_result = await db.execute(
        select(MissionStatusHistory)
        .where(MissionStatusHistory.mission_id == mission_id)
        .order_by(MissionStatusHistory.changed_at.asc())
    )
    return history_result.scalars().all()

@router.get("/missions/user/{user_id}/active")
async def get_active_missions_for_user(user_id: int, db: AsyncSession = Depends(database.get_db), _: dict = Depends(verify_jwt)):
    """Retourne toutes les missions où l'utilisateur (user_id) figure dans proposed_team.

    Utilisé par le tool MCP get_user_availability (users_api) pour détecter les conflits
    de staffing. Un consultant déjà proposé sur une mission active ne peut pas être
    considéré comme pleinement disponible (STAFF-003).

    Returns:
        Liste de missions actives avec : id, title, role du user, estimated_days.
    """
    result = await db.execute(select(Mission).order_by(Mission.created_at.desc()))
    missions = result.scalars().all()

    active_missions = []
    for m in missions:
        proposed_team = m.proposed_team or []
        for member in proposed_team:
            try:
                member_user_id = int(member.get("user_id", -1))
            except (ValueError, TypeError):
                continue
            # user_id 0 est la valeur sentinelle "aucun profil"
            if member_user_id == user_id and member_user_id > 0:
                active_missions.append({
                    "mission_id": m.id,
                    "mission_title": m.title,
                    "role": member.get("role", "Consultant"),
                    "estimated_days": member.get("estimated_days", 0),
                    "justification": member.get("justification", "")
                })
                break  # Un user ne peut figurer qu'une fois par mission

    return {"user_id": user_id, "active_missions": active_missions, "total": len(active_missions)}


@router.get("/missions/{mission_id}", response_model=MissionAnalyzeResponse)
async def get_mission(mission_id: int, db: AsyncSession = Depends(database.get_db), _: dict = Depends(verify_jwt)):
    result = await db.execute(select(Mission).where(Mission.id == mission_id))
    m = result.scalars().first()
    if not m:
        raise HTTPException(status_code=404, detail="Mission introuvable")
    return {
        "id": m.id,
        "title": m.title,
        "description": m.description,
        "status": m.status or MissionStatus.STAFFED,
        "extracted_competencies": m.extracted_competencies or [],
        "prefiltered_candidates": m.prefiltered_candidates or [],
        "proposed_team": m.proposed_team or [],
        "fallback_full_scan": m.fallback_full_scan,
    }
