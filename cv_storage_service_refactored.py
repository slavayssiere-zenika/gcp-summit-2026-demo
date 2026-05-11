import asyncio
import logging
import os
import random
import re
import string
import unicodedata
from typing import Any, Optional, Tuple, List

import httpx
from fastapi import HTTPException
from opentelemetry.propagate import inject as _inject
from sqlalchemy import delete as sa_delete
from sqlalchemy.future import select

from src.cvs.models import CVProfile
from src.services.config import COMPETENCIES_API_URL, ITEMS_API_URL, USERS_API_URL
from src.services.utils import _coerce_to_str
from shared.schemas.users import UsersResponse
from pydantic import ValidationError

logger = logging.getLogger(__name__)


class CVStorageService:
    @staticmethod
    def sanitize_field(val: Any) -> Optional[str]:
        if val is None:
            return None
        s = str(val).strip()
        clean_s = s.lower().strip(",").strip()
        if clean_s in ("null", "none", "", "unknown", "n/a", "na", "nil"):
            return None
        return s

    @staticmethod
    def normalize_str(s: str) -> str:
        if not s:
            return ""
        return unicodedata.normalize('NFKD', s).encode(
            'ASCII', 'ignore').decode('utf-8').lower()

    @staticmethod
    def is_valid_name(n: Optional[str]) -> bool:
        NAME_REGEX = r"^[A-Za-zÀ-ÿ\s'-]+$"
        return bool(n and re.match(NAME_REGEX, n))

    @staticmethod
    def is_valid_email(e: Optional[str]) -> bool:
        EMAIL_REGEX = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
        return bool(e and re.match(EMAIL_REGEX, e))

    @staticmethod
    async def _lookup_user_by_folder_name(http_client: httpx.AsyncClient, folder_first_name: str, folder_last_name: str, headers: dict) -> Optional[int]:
        folder_search_q = f"{folder_first_name} {folder_last_name}"
        fn_res = await http_client.get(
            f"{USERS_API_URL.rstrip('/')}/search",
            params={"query": folder_search_q, "limit": 10, "is_anonymous": "false"},
            headers=headers
        )
        if fn_res.status_code == 200:
            try:
                fn_data = UsersResponse.model_validate(fn_res.json())
                for u in fn_data.items:
                    if CVStorageService.normalize_str(u.first_name) == CVStorageService.normalize_str(folder_first_name) and \
                       CVStorageService.normalize_str(u.last_name) == CVStorageService.normalize_str(folder_last_name):
                        return u.id
            except ValidationError as ve:
                logger.error("[cv_storage] Rupture contrat users /search (folder)", extra={"error": str(ve)})
        return None

    @staticmethod
    async def _lookup_user_by_email(http_client: httpx.AsyncClient, email: str, ext_full_norm: str, headers: dict) -> Optional[int]:
        search_res = await http_client.get(
            f"{USERS_API_URL.rstrip('/')}/search",
            params={"query": email, "limit": 10, "is_anonymous": "false"},
            headers=headers
        )
        if search_res.status_code == 200:
            try:
                search_data = UsersResponse.model_validate(search_res.json())
                for u in search_data.items:
                    if u.email and u.email.lower() == email.lower():
                        u_full_norm = CVStorageService.normalize_str(u.full_name or f"{u.first_name or ''} {u.last_name or ''}")
                        if ext_full_norm and ext_full_norm not in u_full_norm and u_full_norm not in ext_full_norm:
                            continue
                        return u.id
            except ValidationError as ve:
                logger.error("[cv_storage] Rupture contrat users /search (email)", extra={"error": str(ve)})
        return None

    @staticmethod
    async def _lookup_user_by_name(http_client: httpx.AsyncClient, first_name: str, last_name: str, headers: dict) -> Optional[int]:
        search_q = f"{first_name} {last_name}"
        name_res = await http_client.get(
            f"{USERS_API_URL.rstrip('/')}/search",
            params={"query": search_q, "limit": 10, "is_anonymous": "false"},
            headers=headers
        )
        if name_res.status_code == 200:
            try:
                name_data = UsersResponse.model_validate(name_res.json())
                for u in name_data.items:
                    if CVStorageService.normalize_str(u.first_name) == CVStorageService.normalize_str(first_name) and \
                       CVStorageService.normalize_str(u.last_name) == CVStorageService.normalize_str(last_name):
                        return u.id
            except ValidationError as ve:
                logger.error("[cv_storage] Rupture contrat users /search (name)", extra={"error": str(ve)})
        return None

    @staticmethod
    async def _resolve_importer(http_client: httpx.AsyncClient, token_payload: dict, headers: dict) -> Optional[int]:
        importer_username = token_payload.get("sub")
        if not importer_username:
            return None
        importer_res = await http_client.get(f"{USERS_API_URL.rstrip('/')}/search", params={"query": importer_username, "limit": 10}, headers=headers)
        if importer_res.status_code == 200:
            try:
                importer_data = UsersResponse.model_validate(importer_res.json())
                for u in importer_data.items:
                    if u.username and u.username.lower() == importer_username.lower():
                        return u.id
            except ValidationError as ve:
                logger.error("[cv_storage] Rupture contrat users /search (importer)", extra={"error": str(ve)})
        return None

    @staticmethod
    async def _create_user(http_client: httpx.AsyncClient, email: str, first_name: str, last_name: str, is_anonymous: bool, headers: dict) -> int:
        safe_fn = first_name or "u"
        safe_ln = last_name or f"user{random.randint(1000, 9999)}"
        new_u = {
            "username": f"{safe_fn[0].lower()}{safe_ln.lower().replace(' ', '')}{random.randint(100, 999)}",
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "full_name": f"{first_name or ''} {last_name or ''}".strip() or "Unknown User",
            "password": "zenikacv123",
            "is_anonymous": is_anonymous
        }
        create_res = await http_client.post(f"{USERS_API_URL.rstrip('/')}/", json=new_u, headers=headers)
        if create_res.status_code == 409 or (create_res.status_code >= 400 and "already exists" in create_res.text.lower()):
            host = email.split('@')[1] if '@' in email else "zenika.com"
            prefix = email.split('@')[0] if '@' in email else "conflict"
            conflict_email = f"{prefix}.conflict.{random.randint(1000, 9999)}@{host}"
            new_u["email"] = conflict_email
            create_res = await http_client.post(f"{USERS_API_URL.rstrip('/')}/", json=new_u, headers=headers)
        if create_res.status_code >= 400:
            raise HTTPException(status_code=500, detail=f"User creation failed: {create_res.text}")
        return create_res.json()["id"]

    @staticmethod
    async def resolve_identity_and_user(
        db, structured_cv: dict, folder_name: Optional[str], token_payload: dict, url: str, headers: dict
    ):
        raw_email = CVStorageService.sanitize_field(structured_cv.get("email"))
        llm_first_name = CVStorageService.sanitize_field(structured_cv.get("first_name"))
        llm_last_name = CVStorageService.sanitize_field(structured_cv.get("last_name"))
        is_anonymous = structured_cv.get("is_anonymous", False)
        trigram = CVStorageService.sanitize_field(structured_cv.get("trigram"))

        if llm_first_name and not CVStorageService.is_valid_name(llm_first_name):
            llm_first_name = None
        if llm_last_name and not CVStorageService.is_valid_name(llm_last_name):
            llm_last_name = None

        folder_first_name: Optional[str] = None
        folder_last_name: Optional[str] = None

        if folder_name and folder_name.strip():
            parts = folder_name.strip().split(None, 1)
            if len(parts) == 2:
                folder_first_name = CVStorageService.sanitize_field(parts[0])
                folder_last_name = CVStorageService.sanitize_field(parts[1])
                if not CVStorageService.is_valid_name(folder_first_name):
                    folder_first_name = None
                if not CVStorageService.is_valid_name(folder_last_name):
                    folder_last_name = None

        first_name = folder_first_name or llm_first_name
        last_name = folder_last_name or llm_last_name

        warnings = []
        if folder_first_name and folder_last_name and llm_first_name and llm_last_name:
            if folder_first_name.lower() != llm_first_name.lower() or folder_last_name.lower() != llm_last_name.lower():
                warn_folder = f"⚠️ Divergence d'identité — Dossier: '{folder_first_name} {folder_last_name}' / LLM: '{llm_first_name} {llm_last_name}'"
                warnings.append(warn_folder)
                first_name, last_name = folder_first_name, folder_last_name

        if not CVStorageService.is_valid_name(first_name):
            first_name = None
        if not CVStorageService.is_valid_name(last_name):
            last_name = None

        if not CVStorageService.is_valid_email(raw_email):
            if first_name and last_name:
                email = f"{CVStorageService.normalize_str(first_name).replace(' ', '').replace('-', '')}.{CVStorageService.normalize_str(last_name).replace(' ', '').replace('-', '')}@zenika.com"
                warnings.append(f"Email absent ou invalide dans le CV — email généré : {email}")
            else:
                is_anonymous = True
                trigram = trigram or ''.join(random.choices(string.ascii_uppercase, k=3))
                first_name, last_name = "Anon", trigram
                email = f"anon.{trigram.lower()}@anonymous.zenika.com"
                warnings.append("Identité introuvable dans le CV — profil anonymisé automatiquement")
        else:
            email = raw_email

        ext_full_norm = f"{CVStorageService.normalize_str(first_name)} {CVStorageService.normalize_str(last_name)}"

        user_id = None
        importer_id = None

        async with httpx.AsyncClient(timeout=30.0) as http_client:
            try:
                existing_cv = (await db.execute(select(CVProfile).where(CVProfile.source_url == url))).scalars().first()
            except AttributeError:
                existing_cv = (await db.execute(select(CVProfile).where(CVProfile.source_url == url))).first()

            if existing_cv and existing_cv.user_id:
                user_id = existing_cv.user_id

            if not user_id and folder_first_name and folder_last_name:
                user_id = await CVStorageService._lookup_user_by_folder_name(http_client, folder_first_name, folder_last_name, headers)

            if not user_id and email:
                user_id = await CVStorageService._lookup_user_by_email(http_client, email, ext_full_norm, headers)

            if not user_id and first_name and last_name:
                user_id = await CVStorageService._lookup_user_by_name(http_client, first_name, last_name, headers)

            importer_id = await CVStorageService._resolve_importer(http_client, token_payload, headers)

            filename = os.path.basename(url).lower()
            if not is_anonymous and not user_id and any(x in filename for x in ["annonym", "anon", "abc"]):
                is_anonymous = True
                if first_name != "Anon":
                    trigram = trigram or ''.join(random.choices(string.ascii_uppercase, k=3))
                    first_name, last_name = "Anon", trigram
                    email = f"anon.{trigram.lower()}@anonymous.zenika.com"

            if user_id and is_anonymous:
                user_info_res = await http_client.get(f"{USERS_API_URL.rstrip('/')}/{user_id}", headers=headers)
                if user_info_res.status_code == 200:
                    user_data = user_info_res.json()
                    if not user_data.get("is_anonymous", False):
                        is_anonymous = False
                        logger.info("[cv_storage] Profil dés-anonymisé : user_id=%s résolu comme consultant réel.", user_id)
                else:
                    logger.warning("[cv_storage] Impossible de vérifier le statut anonyme de user_id=%s (HTTP %s).", user_id, user_info_res.status_code)

            if not user_id:
                user_id = await CVStorageService._create_user(http_client, email, first_name, last_name, is_anonymous, headers)

        return user_id, importer_id, first_name, last_name, email, is_anonymous, warnings
