from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks, File, UploadFile, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid
import traceback

import database
from .models import Mission, MissionStatus, MissionStatusHistory
from .schemas import TaskResponse
from src.auth import verify_jwt
from opentelemetry.propagate import inject

from .cache import force_invalidate_prompt
from .task_state import task_manager

# Import du service coeur pour l'analyse des missions
from .analysis_service import process_mission_core

router = APIRouter(prefix="", tags=["Missions_Analysis"], dependencies=[Depends(verify_jwt)])


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
    # C4 : Seuls commercial, admin et service_account peuvent créer une mission
    # (protection FinOps : chaque mission déclenche 2 appels Gemini)
    user_role = token_payload.get("role", "user")
    if user_role not in ("admin", "commercial", "service_account"):
        raise HTTPException(
            status_code=403,
            detail="Accès refusé : seuls les rôles commercial, admin et service_account peuvent créer une mission."
        )
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
        # Validation par magic bytes (anti-spoofing) — AGENTS.md §2
        # Le content_type HTTP est fourni par le client et peut être falsifié.
        # On inspecte les premiers octets pour valider la signature binaire réelle.
        MAGIC_SIGNATURES = [
            b"%PDF",          # PDF
            b"PK\x03\x04",   # DOCX / ZIP (Open XML)
            b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1",  # OLE2 (doc)
        ]
        is_text = False
        try:
            file_bytes[:256].decode("utf-8")
            is_text = True
        except (UnicodeDecodeError, ValueError):
            pass

        if not is_text and not any(file_bytes.startswith(sig) for sig in MAGIC_SIGNATURES):
            raise HTTPException(
                status_code=400,
                detail="Fichier invalide : la signature binaire ne correspond pas à un PDF ou DOCX reconnu."
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
        process_mission_core,
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
    # C4b : Seuls commercial, admin et service_account peuvent ré-analyser une mission
    user_role = token_payload.get("role", "user")
    if user_role not in ("admin", "commercial", "service_account"):
        raise HTTPException(
            status_code=403,
            detail="Accès refusé : seuls les rôles commercial, admin et service_account peuvent ré-analyser une mission."
        )
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
    bg_tasks.add_task(process_mission_core, m.title, m.description, None, None, None, headers, user_email, auth_token, task_id, mission_id)
    
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

@router.get("/missions/{mission_id}/embedding")
async def get_mission_embedding(
    mission_id: int,
    db: AsyncSession = Depends(database.get_db),
    _: dict = Depends(verify_jwt),
):
    """Retourne le semantic_embedding vectoriel d'une mission pour le matching CV.
    Utilisé par cv_api /search/mission-match pour trouver les consultants
    correspondant au profil d'une mission analysée par l'IA.
    Retourne 422 si la mission n'a pas encore été analysée (embedding NULL).
    """
    result = await db.execute(select(Mission).where(Mission.id == mission_id))
    m = result.scalars().first()
    if not m:
        raise HTTPException(status_code=404, detail="Mission introuvable")
    if m.semantic_embedding is None:
        raise HTTPException(
            status_code=422,
            detail="Cette mission n'a pas encore d'embedding vectoriel. Déclenchez une ré-analyse IA d'abord."
        )
    # Convertir le vecteur pgvector en liste Python sérialisable
    embedding_list = list(m.semantic_embedding) if hasattr(m.semantic_embedding, "__iter__") else m.semantic_embedding
    return {"mission_id": mission_id, "embedding": embedding_list, "dimensions": len(embedding_list)}
