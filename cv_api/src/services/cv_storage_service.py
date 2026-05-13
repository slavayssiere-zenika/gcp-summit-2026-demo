import asyncio
import logging
import os
import random
import re
import string
import unicodedata
from typing import Any, Optional

import httpx
from fastapi import HTTPException
from opentelemetry.propagate import inject as _inject
from sqlalchemy import delete as sa_delete, update as sa_update
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

    @staticmethod
    async def bg_process_competencies_and_missions(
            bg_user_id: int, bg_structured_cv: dict, bg_headers: dict, bg_url: str) -> list[str]:
        """Résout et assigne les compétences + missions d'un CV en arrière-plan.

        Retourne la liste d'erreurs (vide = succès total).
        C'est l'APPELANT qui est responsable du PATCH Drive final,
        garantissant un seul PATCH avec le statut définitif (IMPORTED_CV ou ERROR).
        """
        bg_errors: list[str] = []
        async with httpx.AsyncClient(timeout=120.0) as bg_http_client:
            try:
                existing_comps = set()
                try:
                    res = await bg_http_client.get(
                        f"{COMPETENCIES_API_URL.rstrip('/')}/user/{bg_user_id}",
                        headers=bg_headers, timeout=5.0
                    )
                    if res.status_code == 200:
                        body = res.json()
                        # /user/{id} retourne PaginationResponse — items est la liste
                        items_list = body.get("items", body) if isinstance(body, dict) else body
                        existing_comps = {c["id"] for c in items_list if isinstance(c, dict)}
                except Exception as e:
                    logger.warning(
                        "[import] Impossible de récupérer les compétences existantes: %s", e)

                # sem=8 : parallélisme accru pour la résolution (était 3)
                sem = asyncio.Semaphore(8)

                def normalize_comp(text):
                    if not text:
                        return ""
                    text = text.strip().lower()
                    return "".join(c for c in unicodedata.normalize(
                        'NFKD', text) if unicodedata.category(c) != 'Mn')

                async def resolve_comp_id(name: str) -> Optional[int]:
                    try:
                        res = await bg_http_client.get(
                            f"{COMPETENCIES_API_URL.rstrip('/')}/search",
                            params={"query": name, "limit": 5},
                            headers=bg_headers, timeout=5.0
                        )
                        if res.status_code == 200:
                            n_norm = normalize_comp(name)
                            # Contrat intentionnel : /search retourne PaginationResponse mais items
                            # sont des dicts compétences partiels (name, aliases) — parsing manuel OK
                            from shared.schemas.pagination import PaginationResponse
                            data = PaginationResponse[dict].model_validate(res.json())
                            for item in data.items:
                                if normalize_comp(
                                        item.get("name", "")) == n_norm:
                                    return item["id"]
                                aliases_raw = item.get("aliases") or ""
                                for alias in aliases_raw.split(","):
                                    if normalize_comp(alias.strip()) == n_norm:
                                        return item["id"]
                    except Exception as e:
                        logger.debug(
                            "[import] Competency alias lookup failed: %s", e)
                    return None

                async def process_competency(comp):
                    async with sem:
                        name = CVStorageService.sanitize_field(
                            comp.get("name"))
                    if not name or not comp.get("practiced", True):
                        return True
                    parent = CVStorageService.sanitize_field(
                        comp.get("parent"))
                    try:
                        c_id = await resolve_comp_id(name)
                        if not c_id:
                            p_id = None
                            if parent:
                                p_id = await resolve_comp_id(parent)
                                if not p_id:
                                    p_res = await bg_http_client.post(
                                        f"{COMPETENCIES_API_URL.rstrip('/')}/",
                                        json={"name": parent, "description": "Auto-identified from CV"},
                                        headers=bg_headers
                                    )
                                    if p_res.status_code < 400:
                                        p_id = p_res.json()["id"]

                            aliases_str = ", ".join(
                                comp.get("aliases", [])) if comp.get("aliases") else None
                            leaf_data = {
                                "name": name,
                                "description": "Candidate CV Skill",
                                "aliases": aliases_str}
                            if p_id:
                                leaf_data["parent_id"] = p_id

                            c_id = await resolve_comp_id(name)
                            if not c_id:
                                c_res = await bg_http_client.post(
                                    f"{COMPETENCIES_API_URL.rstrip('/')}/",
                                    json=leaf_data, headers=bg_headers
                                )
                                if c_res.status_code < 400:
                                    c_id = c_res.json()["id"]

                        return c_id
                    except Exception as e:
                        logger.warning(
                            "[import] Résolution compétence '%s' échouée: %s", name, e)
                        return None

                # ── Phase 1 : résolution parallèle de TOUS les IDs ─────────────────
                competencies_list = bg_structured_cv.get("competencies", [])
                resolve_tasks = [process_competency(c) for c in competencies_list]
                resolved_ids = await asyncio.gather(*resolve_tasks, return_exceptions=True)

                ids_to_assign = [
                    cid for cid in resolved_ids
                    if isinstance(cid, int) and cid not in existing_comps
                ]
                failed_count = sum(
                    1 for cid in resolved_ids
                    if cid is None or isinstance(cid, Exception)
                )
                if failed_count:
                    bg_errors.append(
                        f"{failed_count} compétence(s) non résolue(s) dans competencies_api"
                    )

                # ── Phase 2 : UN seul appel bulk assign (atomique, idempotent) ──────
                # POST /user/{id}/assign/bulk → ON CONFLICT DO NOTHING en base.
                # Garantit que soit TOUTES les compétences sont assignées en un
                # appel DB, soit on a une erreur claire. Élimine l'état partiel
                # (ex: "4 sur 20") causé par les timeouts de la boucle individuelle.
                #
                # Retry sur 429/5xx : competencies_api retourne 429 quand son pool DB
                # est saturé (ASSIGN_BULK_SEMAPHORE plein). La saturation est transitoire
                # (quelques ms à quelques secondes). Sans retry, chaque 429/500 générait
                # un processing_error permanent — la vraie cause du 99% d'erreurs en prod.
                if ids_to_assign:
                    assign_url = (
                        f"{COMPETENCIES_API_URL.rstrip('/')}/user/{bg_user_id}/assign/bulk"
                    )
                    assign_payload = {"competency_ids": ids_to_assign}
                    bulk_res: Optional[httpx.Response] = None
                    for attempt in range(4):
                        try:
                            bulk_res = await bg_http_client.post(
                                assign_url,
                                json=assign_payload,
                                headers=bg_headers,
                                timeout=30.0,
                            )
                            if bulk_res.status_code not in (429, 500, 502, 503, 504):
                                break
                            wait = min(2 ** attempt + random.uniform(0, 1), 30.0)
                            logger.warning(
                                "[import] assign/bulk user_id=%s → HTTP %s, retry %d/4 dans %.1fs",
                                bg_user_id, bulk_res.status_code, attempt + 1, wait,
                            )
                        except httpx.TimeoutException as exc:
                            wait = min(2 ** attempt + random.uniform(0, 1), 30.0)
                            logger.warning(
                                "[import] assign/bulk user_id=%s → %s, retry %d/4 dans %.1fs",
                                bg_user_id, type(exc).__name__, attempt + 1, wait,
                            )
                            bulk_res = None
                        if attempt < 3:
                            await asyncio.sleep(wait)

                    if bulk_res is None or bulk_res.status_code >= 400:
                        status = bulk_res.status_code if bulk_res is not None else "timeout"
                        bg_errors.append(
                            f"Bulk assign échoué après 4 tentatives (HTTP {status}): "
                            f"{bulk_res.text[:200] if bulk_res is not None else 'timeout'}"
                        )
                    else:
                        result = bulk_res.json()
                        logger.info(
                            "[import] Bulk assign user_id=%s : %d assignées, %d invalides",
                            bg_user_id,
                            result.get("assigned", 0),
                            result.get("skipped", 0),
                        )
            except Exception as e:
                bg_errors.append(f"Crash compétences: {e}")

            try:
                missions_list = bg_structured_cv.get("missions", [])
                cat_res = await bg_http_client.get(f"{ITEMS_API_URL.rstrip('/')}/categories", headers=bg_headers)
                if cat_res.status_code == 200:
                    cat_data = cat_res.json()
                    # /categories retourne {"items": [...], "total": N} (paginé) ou une liste directe
                    categories = cat_data.get("items", cat_data) if isinstance(cat_data, dict) else cat_data
                else:
                    categories = []

                def find_cat_id(name):
                    for c in categories:
                        if c["name"].lower() == name.lower():
                            return c["id"]
                    return None

                mission_cat_id = find_cat_id("Missions")
                if not mission_cat_id:
                    m_res = await bg_http_client.post(f"{ITEMS_API_URL.rstrip('/')}/categories", json={"name": "Missions", "description": "Professional experiences"}, headers=bg_headers)
                    if m_res.status_code < 400:
                        mission_cat_id = m_res.json()["id"]

                sensitive_cat_id = find_cat_id("Restricted")
                if not sensitive_cat_id:
                    s_res = await bg_http_client.post(f"{ITEMS_API_URL.rstrip('/')}/categories", json={"name": "Restricted", "description": "Sensitive missions"}, headers=bg_headers)
                    if s_res.status_code < 400:
                        sensitive_cat_id = s_res.json()["id"]

                item_data_list = []
                for m in missions_list:
                    cat_ids = [mission_cat_id] if mission_cat_id else []
                    if m.get("is_sensitive") and sensitive_cat_id:
                        cat_ids.append(sensitive_cat_id)
                    item_data_list.append({
                        "name": m["title"], "description": m.get("description", ""), "user_id": bg_user_id, "category_ids": cat_ids,
                        "metadata_json": {"company": m.get("company"), "competencies": m.get("competencies", []), "is_sensitive": m.get("is_sensitive", False), "start_date": m.get("start_date"), "end_date": m.get("end_date"), "duration": m.get("duration"), "mission_type": m.get("mission_type", "build"), "source": "CV Analysis"}
                    })

                if item_data_list:
                    m_post = await bg_http_client.post(f"{ITEMS_API_URL.rstrip('/')}/bulk", json={"items": item_data_list}, headers=bg_headers)
                    if m_post.status_code >= 400:
                        bg_errors.append("Création missions échouée")
            except Exception as e:
                bg_errors.append(f"Crash missions: {e}")

        if bg_errors:
            logger.warning(
                "[import] %d erreur(s) de post-traitement pour user_id=%s : %s",
                len(bg_errors), bg_user_id, " | ".join(bg_errors)
            )

        # ── Persistance en base (TOUJOURS, même si pas d'erreur) ────────────────
        # Une compétence non assignée = consultant invisible à la recherche = critique
        try:
            from database import SessionLocal
            async with SessionLocal() as db_bg:
                async with db_bg.begin():
                    await db_bg.execute(
                        sa_update(CVProfile)
                        .where(CVProfile.source_url == bg_url)
                        .values(processing_errors=bg_errors)
                    )
        except Exception as e:
            logger.error(
                "[import] Impossible de persister processing_errors pour url=%s : %s",
                bg_url, e
            )

        # ── NOTE : le PATCH Drive est délégué à l'appelant (pubsub_service) ────
        # bg_process retourne bg_errors ; c'est pubsub_service._run_cv_pipeline_bg
        # qui émet UN SEUL PATCH final (IMPORTED_CV ou ERROR), évitant toute
        # race condition entre les deux statuts.

        # ── Déclenchement du scoring IA (non-bloquant, timeout généreux) ────────
        try:
            async with httpx.AsyncClient(timeout=30.0) as _score_client:
                _score_headers = dict(bg_headers)
                _inject(_score_headers)
                score_res = await _score_client.post(
                    f"{COMPETENCIES_API_URL.rstrip('/')}/evaluations/user/{bg_user_id}/ai-score-all"
                    "?only_missing=true",
                    headers=_score_headers,
                    timeout=30.0
                )
                if score_res.status_code >= 400:
                    logger.warning(
                        "[import] AI scoring user_id=%s : HTTP %s — score différé",
                        bg_user_id, score_res.status_code
                    )
        except Exception as e:
            logger.warning(
                "[import] Déclenchement scoring IA user_id=%s échoué (non-bloquant): %s",
                bg_user_id, e
            )

        return bg_errors

    @staticmethod
    async def upsert_cv_profile(
        db, user_id: int, url: str, source_tag: Optional[str],
        structured_cv: dict, raw_text: str, vector_data: Optional[list], importer_id: Optional[int],
        extraction_reliability_score: Optional[int] = None
    ):
        await db.execute(sa_delete(CVProfile).where(CVProfile.source_url == url))
        comp_keywords = [
            c.get("name") for c in structured_cv.get(
                "competencies",
                []) if c.get("name")]

        # R1 — Enregistre le modèle d'embedding utilisé pour ce profil
        current_embedding_model = os.getenv("GEMINI_EMBEDDING_MODEL")

        cv_record = CVProfile(
            user_id=user_id,
            source_url=url,
            source_tag=source_tag,
            extracted_competencies=structured_cv.get("competencies", []),
            current_role=structured_cv.get("current_role"),
            years_of_experience=structured_cv.get("years_of_experience"),
            summary=_coerce_to_str(structured_cv.get("summary")),
            competencies_keywords=comp_keywords,
            missions=structured_cv.get("missions", []),
            educations=structured_cv.get("educations", []),
            raw_content=raw_text,
            semantic_embedding=vector_data,
            embedding_model=current_embedding_model if vector_data else None,
            extraction_reliability_score=extraction_reliability_score,
            imported_by_id=importer_id
        )
        db.add(cv_record)
        await db.commit()
