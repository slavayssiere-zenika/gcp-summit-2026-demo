import json
import logging

import shared.database as database
from fastapi import APIRouter, Depends
from sqlalchemy import cast, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from shared.auth.jwt import verify_jwt

from shared.cache import delete_cache, get_cache, set_cache
from .models import Mission

logger = logging.getLogger(__name__)

# TTL du cache utilisateur-missions (P3 perf — hot path MCP get_user_availability).
# 30s : acceptable pour le matching temps réel ; une mission ne change pas
# plus vite que ça en pratique.
_CACHE_TTL = 30
_CACHE_KEY_PREFIX = "missions:user:active:v1"

router = APIRouter(prefix="", tags=["Missions_User"], dependencies=[Depends(verify_jwt)])


def _user_cache_key(user_id: int) -> str:
    return f"{_CACHE_KEY_PREFIX}:{user_id}"


async def invalidate_user_active_cache(user_id: int) -> None:
    """Invalide le cache actif d'un user (à appeler sur toute mutation de mission)."""
    try:
        await delete_cache(_user_cache_key(user_id))
    except Exception as e:
        logger.warning("[user_router] Echec invalidation cache user %s: %s", user_id, e)


@router.get("/missions/user/{user_id}/active")
async def get_active_missions_for_user(
    user_id: int,
    db: AsyncSession = Depends(database.get_db),
    _: dict = Depends(verify_jwt),
):
    """Retourne toutes les missions où l'utilisateur (user_id) figure dans proposed_team.

    Utilisé par le tool MCP get_user_availability (users_api) pour détecter les conflits
    de staffing. Un consultant déjà proposé sur une mission active ne peut pas être
    considéré comme pleinement disponible (STAFF-003).

    Cache Redis TTL=30s (clé: missions:user:active:v1:{user_id}).
    Invalidé sur toute mutation de mission (POST/PUT/DELETE crud_router).

    Returns:
        Liste de missions actives avec : id, title, role du user, estimated_days.
    """
    cache_key = _user_cache_key(user_id)

    # 1. Lecture cache Redis
    try:
        data = await get_cache(cache_key)
        if data:
            logger.debug("[user_router] Cache HIT user_id=%s", user_id)
            return data
    except Exception as e:
        logger.warning("[user_router] Cache read error user_id=%s: %s", user_id, e)

    # 2. Requête DB — filtre JSONB via index GIN (changeset 7)
    #    WHERE proposed_team @> '[{"user_id": X}]' exploite idx_missions_proposed_team_gin
    #    ORDER BY created_at DESC exploite idx_missions_created_at_desc
    #    O(log n) au lieu du full scan O(n) + filtre Python précédent.
    user_filter = cast(json.dumps([{"user_id": user_id}]), JSONB)
    result = await db.execute(
        select(Mission)
        .where(Mission.proposed_team.op("@>")(user_filter))
        .order_by(Mission.created_at.desc())
    )
    missions = result.scalars().all()

    active_missions = []
    for m in missions:
        proposed_team = m.proposed_team or []
        for member in proposed_team:
            try:
                member_user_id = int(member.get("user_id", -1))
            except (ValueError, TypeError):
                continue
            if member_user_id == user_id and member_user_id > 0:
                active_missions.append({
                    "mission_id": m.id,
                    "mission_title": m.title,
                    "role": member.get("role", "Consultant"),
                    "estimated_days": member.get("estimated_days", 0),
                    "justification": member.get("justification", ""),
                })
                break

    response = {
        "user_id": user_id,
        "active_missions": active_missions,
        "total": len(active_missions),
    }

    # 3. Écriture cache Redis (fail-soft)
    try:
        await set_cache(cache_key, response, _CACHE_TTL)
        logger.debug("[user_router] Cache SET user_id=%s TTL=%ss", user_id, _CACHE_TTL)
    except Exception as e:
        logger.warning("[user_router] Cache write error user_id=%s: %s", user_id, e)

    return response
