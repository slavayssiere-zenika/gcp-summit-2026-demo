import logging
from datetime import datetime
import re
import httpx
from typing import List, Dict, Any, Optional
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, text
from sqlalchemy.orm.attributes import flag_modified
from fastapi import HTTPException
from pydantic import ValidationError

from src.cvs.models import CVProfile
from src.cvs.routers._shared import USERS_API_URL
from shared.schemas.users import UserItem, UsersResponse
from src.cvs.schemas import (CVProfileResponse, CVFullProfileResponse,
                             MissionCreateRequest, MissionUpdateRequest)

logger = logging.getLogger(__name__)


def extract_google_file_id(url: str) -> str | None:
    if not url:
        return None
    match = re.search(r'/d/([a-zA-Z0-9-_]{25,50})', url)
    if match:
        return match.group(1)
    match = re.search(r'id=([a-zA-Z0-9-_]{25,50})', url)
    if match:
        return match.group(1)
    return None


class ProfileService:
    @staticmethod
    async def get_file_names(file_ids: List[str], db: AsyncSession) -> Dict[str, str]:
        if not file_ids:
            return {}
        try:
            query = text("SELECT google_file_id, file_name FROM drive_sync_state WHERE google_file_id = ANY(:file_ids)")
            result = await db.execute(query, {"file_ids": file_ids})
            return {row[0]: row[1] for row in result.all() if row[1]}
        except Exception as e:
            logger.warning(f"Failed to query file names from drive_sync_state: {e}")
            return {}

    @staticmethod
    async def get_users_by_tag(
        tag: str, skip: int, limit: int, headers_downstream: dict, db: AsyncSession
    ) -> tuple[int, List[CVProfileResponse]]:
        profiles = (await db.execute(
            select(CVProfile)
            .distinct(CVProfile.user_id)
            .order_by(CVProfile.user_id, CVProfile.created_at.desc())
        )).scalars().all()

        seen_users = set()
        unique_profiles = []

        for p in profiles:
            if p.source_tag and tag.lower() in p.source_tag.lower():
                if p.user_id not in seen_users:
                    seen_users.add(p.user_id)
                    unique_profiles.append(p)

        user_ids = list(seen_users)
        user_enrich_map = {}

        async with httpx.AsyncClient(timeout=10.0) as http_client:
            for u_id in user_ids:
                try:
                    u_res = await http_client.get(
                        f"{USERS_API_URL.rstrip('/')}/{u_id}",
                        headers=headers_downstream,
                        timeout=10.0
                    )
                    if u_res.status_code == 200:
                        try:
                            u_data = UserItem.model_validate(u_res.json())
                            user_enrich_map[u_id] = u_data.model_dump()
                        except ValidationError as ve:
                            logger.error(f"Rupture de contrat API users pour {u_id}", extra={"error": str(ve)})
                except Exception as e:
                    logger.warning(f"Failed to fetch user {u_id} for enrichment: {e}")

        total = len(unique_profiles)
        paginated_profiles = unique_profiles[skip:skip + limit]

        file_ids = [
            extract_google_file_id(p.source_url) for p in paginated_profiles if p.source_url
        ]
        file_ids = [fid for fid in file_ids if fid]
        file_names_map = await ProfileService.get_file_names(file_ids, db)

        responses = [
            CVProfileResponse(
                user_id=p.user_id,
                source_url=p.source_url,
                source_tag=p.source_tag,
                imported_by_id=p.imported_by_id,
                is_anonymous=user_enrich_map.get(p.user_id, {}).get("is_anonymous", False),
                full_name=user_enrich_map.get(p.user_id, {}).get("full_name"),
                email=user_enrich_map.get(p.user_id, {}).get("email"),
                username=user_enrich_map.get(p.user_id, {}).get("username"),
                processing_errors=p.processing_errors or [],
                extraction_reliability_score=(
                    p.extraction_reliability_score
                    if hasattr(p, "extraction_reliability_score")
                    and isinstance(p.extraction_reliability_score, int)
                    else None
                ),
                created_at=(
                    p.created_at.isoformat()
                    if hasattr(p, "created_at") and isinstance(p.created_at, datetime)
                    else None
                ),
                file_name=(
                    file_names_map.get(extract_google_file_id(p.source_url))
                    if p.source_url
                    else None
                )
            ) for p in paginated_profiles
        ]
        return total, responses

    @staticmethod
    async def get_user_cv(
        user_id: int, skip: int, limit: int, headers_downstream: dict, db: AsyncSession
    ) -> tuple[int, List[CVProfileResponse]]:
        total = (await db.execute(
            select(func.count(CVProfile.id)).filter(CVProfile.user_id == user_id)
        )).scalar() or 0
        profiles = (await db.execute(
            select(CVProfile)
            .filter(CVProfile.user_id == user_id)
            .order_by(CVProfile.created_at.desc())
            .offset(skip)
            .limit(limit)
        )).scalars().all()
        if not profiles:
            return 0, []

        user_enrich = {}
        async with httpx.AsyncClient(timeout=5.0) as http_client:
            try:
                u_res = await http_client.get(
                    f"{USERS_API_URL.rstrip('/')}/{user_id}",
                    headers=headers_downstream,
                    timeout=10.0
                )
                if u_res.status_code == 200:
                    try:
                        u_data = UserItem.model_validate(u_res.json())
                        user_enrich = u_data.model_dump()
                    except ValidationError as ve:
                        logger.error(f"Rupture de contrat API users pour {user_id}", extra={"error": str(ve)})
            except Exception as e:
                logger.warning(f"Failed to fetch user {user_id} for enrichment: {e}")

        file_ids = [
            extract_google_file_id(p.source_url) for p in profiles if p.source_url
        ]
        file_ids = [fid for fid in file_ids if fid]
        file_names_map = await ProfileService.get_file_names(file_ids, db)

        responses = [
            CVProfileResponse(
                user_id=p.user_id,
                source_url=p.source_url,
                source_tag=p.source_tag,
                imported_by_id=p.imported_by_id,
                is_anonymous=user_enrich.get("is_anonymous", False),
                full_name=user_enrich.get("full_name"),
                email=user_enrich.get("email"),
                username=user_enrich.get("username"),
                processing_errors=p.processing_errors or [],
                extraction_reliability_score=(
                    p.extraction_reliability_score
                    if hasattr(p, "extraction_reliability_score")
                    and isinstance(p.extraction_reliability_score, int)
                    else None
                ),
                created_at=(
                    p.created_at.isoformat()
                    if hasattr(p, "created_at") and isinstance(p.created_at, datetime)
                    else None
                ),
                file_name=(
                    file_names_map.get(extract_google_file_id(p.source_url))
                    if p.source_url
                    else None
                )
            ) for p in profiles
        ]
        return total, responses

    @staticmethod
    async def get_user_missions(
        user_id: int, skip: int, limit: int, db: AsyncSession
    ) -> tuple[int, List[Dict[str, Any]]]:
        profiles = (await db.execute(
            select(CVProfile)
            .filter(CVProfile.user_id == user_id)
            .order_by(CVProfile.created_at.desc())
        )).scalars().all()
        if not profiles:
            return 0, []

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
                    mission["title"] = title
                    merged_missions.append(mission)

        total = len(merged_missions)
        return total, merged_missions[skip:skip + limit]

    @staticmethod
    async def get_user_cv_details(
        user_id: int, headers_downstream: dict, db: AsyncSession
    ) -> Optional[CVFullProfileResponse]:
        profiles = (await db.execute(
            select(CVProfile)
            .filter(CVProfile.user_id == user_id)
            .order_by(CVProfile.created_at.desc())
        )).scalars().all()

        if not profiles:
            return None

        base_profile = profiles[0]
        is_anon = False

        async with httpx.AsyncClient(timeout=5.0) as http_client:
            try:
                u_res = await http_client.get(
                    f"{USERS_API_URL.rstrip('/')}/{user_id}",
                    headers=headers_downstream,
                    timeout=10.0
                )
                if u_res.status_code == 200:
                    try:
                        u_data = UserItem.model_validate(u_res.json())
                        is_anon = u_data.is_anonymous or False
                    except ValidationError as ve:
                        logger.error(f"Rupture de contrat API users pour {user_id}", extra={"error": str(ve)})
            except Exception as e:
                logger.warning(f"Failed to fetch user anonymity status for {user_id}: {e}")

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
            is_anonymous=is_anon,
            processing_errors=base_profile.processing_errors or []
        )

    @staticmethod
    async def remediate_anonymous_profiles_dry(headers_downstream: dict) -> tuple[int, List[dict]]:
        skip, limit, candidates = 0, 100, []
        async with httpx.AsyncClient(timeout=30.0) as http_client:
            while True:
                res = await http_client.get(
                    f"{USERS_API_URL.rstrip('/')}/",
                    params={"skip": skip, "limit": limit, "is_anonymous": "true"},
                    headers=headers_downstream,
                )
                if res.status_code != 200:
                    raise Exception(f"users_api error: HTTP {res.status_code}")

                try:
                    page = UsersResponse.model_validate(res.json())
                except ValidationError as ve:
                    raise Exception(f"Rupture contrat users_api: {ve}")

                if not page.items:
                    break

                for user in page.items:
                    email = getattr(user, "email", "") or ""
                    if email and "@anonymous.zenika.com" not in email.lower():
                        candidates.append({"id": user.id, "email": email,
                                          "full_name": getattr(user, "full_name", None)})

                if len(page.items) < limit:
                    break
                skip += limit

        return len(candidates), candidates[:50]

    @staticmethod
    async def run_remediation(hdrs: dict) -> None:
        skip, limit, total_fixed, total_scanned = 0, 100, 0, 0
        logger.info("[remediate-anon] Démarrage remédiation en background.")

        async with httpx.AsyncClient(timeout=30.0) as http_client:
            while True:
                res = await http_client.get(
                    f"{USERS_API_URL.rstrip('/')}/",
                    params={"skip": skip, "limit": limit, "is_anonymous": "true"},
                    headers=hdrs,
                )
                if res.status_code != 200:
                    break

                try:
                    page = UsersResponse.model_validate(res.json())
                except ValidationError:
                    break

                if not page.items:
                    break

                total_scanned += len(page.items)

                for user in page.items:
                    email = getattr(user, "email", "") or ""
                    if email and "@anonymous.zenika.com" not in email.lower():
                        logger.info(f"[remediate-anon] Correction user_id={user.id}")
                        patch_res = await http_client.put(
                            f"{USERS_API_URL.rstrip('/')}/{user.id}",
                            json={"is_anonymous": False},
                            headers=hdrs,
                        )
                        if patch_res.status_code == 200:
                            total_fixed += 1

                if len(page.items) < limit:
                    break
                skip += limit

        logger.info(f"[remediate-anon] Terminé — scanned={total_scanned}, fixed={total_fixed}.")

    @staticmethod
    async def add_user_mission(user_id: int, mission_data: MissionCreateRequest,
                               db: AsyncSession) -> dict:
        profile = (await db.execute(
            select(CVProfile)
            .filter(CVProfile.user_id == user_id)
            .order_by(CVProfile.created_at.desc())
        )).scalars().first()

        if not profile:
            raise HTTPException(status_code=404, detail="CVProfile introuvable")

        missions_list = profile.missions or []
        new_mission = mission_data.model_dump()
        missions_list = [new_mission] + missions_list
        profile.missions = missions_list
        db.add(profile)
        if hasattr(profile, "_sa_instance_state"):
            flag_modified(profile, "missions")
        await db.commit()
        await db.refresh(profile)
        return new_mission

    @staticmethod
    async def update_user_mission(user_id: int, index: int,
                                  mission_data: MissionUpdateRequest,
                                  db: AsyncSession) -> dict:
        profile = (await db.execute(
            select(CVProfile)
            .filter(CVProfile.user_id == user_id)
            .order_by(CVProfile.created_at.desc())
        )).scalars().first()

        if not profile:
            raise HTTPException(status_code=404, detail="CVProfile introuvable")

        missions_list = profile.missions or []
        if index < 0 or index >= len(missions_list):
            raise HTTPException(status_code=422, detail="Index de mission invalide")

        current_mission = missions_list[index]
        update_data = mission_data.model_dump(exclude_unset=True)
        for key, val in update_data.items():
            current_mission[key] = val

        missions_list[index] = current_mission
        profile.missions = missions_list
        db.add(profile)
        if hasattr(profile, "_sa_instance_state"):
            flag_modified(profile, "missions")
        await db.commit()
        await db.refresh(profile)
        return current_mission

    @staticmethod
    async def delete_user_mission(user_id: int, index: int,
                                  db: AsyncSession) -> dict:
        profile = (await db.execute(
            select(CVProfile)
            .filter(CVProfile.user_id == user_id)
            .order_by(CVProfile.created_at.desc())
        )).scalars().first()

        if not profile:
            raise HTTPException(status_code=404, detail="CVProfile introuvable")

        missions_list = profile.missions or []
        if index < 0 or index >= len(missions_list):
            raise HTTPException(status_code=422, detail="Index de mission invalide")

        removed_mission = missions_list.pop(index)
        profile.missions = missions_list
        db.add(profile)
        if hasattr(profile, "_sa_instance_state"):
            flag_modified(profile, "missions")
        await db.commit()
        await db.refresh(profile)
        return removed_mission
