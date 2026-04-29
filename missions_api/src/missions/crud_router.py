from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from src.auth import verify_jwt
import database
from .models import Mission, MissionStatus, MissionStatusHistory, ALLOWED_TRANSITIONS, STATUS_UPDATE_ROLES
from .schemas import MissionAnalyzeResponse, MissionStatusUpdate, StatusHistoryEntry

router = APIRouter(prefix="", tags=["Missions"], dependencies=[Depends(verify_jwt)])


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
    }


@router.delete("/missions")
async def delete_all_missions(db: AsyncSession = Depends(database.get_db), token_payload: dict = Depends(verify_jwt)):
    """Supprime toutes les missions et leur historique (réservé aux admins)."""
    user_role = token_payload.get("role", "user")
    if user_role != "admin":
        raise HTTPException(status_code=403, detail="Accès refusé : rôle admin requis.")
    
    await db.execute(delete(MissionStatusHistory))
    await db.execute(delete(Mission))
    await db.commit()
    return {"status": "cleared"}

@router.delete("/missions/{mission_id}")
async def delete_mission(mission_id: int, db: AsyncSession = Depends(database.get_db), token_payload: dict = Depends(verify_jwt)):
    """Supprime une mission spécifique et son historique (réservé aux admins et commerciaux)."""
    user_role = token_payload.get("role", "user")
    if user_role not in ("admin", "commercial"):
        raise HTTPException(status_code=403, detail="Accès refusé : rôle admin ou commercial requis.")
    
    result = await db.execute(select(Mission).where(Mission.id == mission_id))
    mission = result.scalars().first()
    if not mission:
        raise HTTPException(status_code=404, detail="Mission introuvable")

    await db.execute(delete(MissionStatusHistory).where(MissionStatusHistory.mission_id == mission_id))
    await db.execute(delete(Mission).where(Mission.id == mission_id))
    await db.commit()
    return {"status": "deleted", "id": mission_id}
