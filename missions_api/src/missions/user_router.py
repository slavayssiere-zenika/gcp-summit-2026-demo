from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.auth import verify_jwt
import database
from .models import Mission

router = APIRouter(prefix="", tags=["Missions_User"], dependencies=[Depends(verify_jwt)])

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
