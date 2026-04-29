import asyncio
import os
import io
import json
import httpx
from google import genai
from google.genai import types
import logging
import traceback
import re
import docx
from sqlalchemy import select

import database
from .models import Mission, MissionStatus, MissionStatusHistory
from opentelemetry.propagate import inject

from .cache import get_cached_prompt
from .task_state import task_manager
from src.gemini_retry import generate_content_with_retry, embed_content_with_retry
from .helpers import build_taxonomy_context, find_domains_for_skills, _collect_all_known_names

GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)
else:
    client = None

CV_API_URL = os.getenv("CV_API_URL", "http://cv_api:8000")
USERS_API_URL = os.getenv("USERS_API_URL", "http://users_api:8000")

async def process_mission_core(title: str, description: str, url: str, file_bytes: bytes, file_mime: str, headers: dict, user_email: str, auth_token: str, task_id: str, mission_id: int = None):
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
            from .document_extractor import extract_document_contents
            gemini_contents, final_description = await extract_document_contents(
                url, file_bytes, file_mime, description, headers, http_client
            )
            gemini_contents.insert(0, extract_prompt)

            # 2. Extract & Summarize
            model_extract = os.getenv("GEMINI_MISSIONS_MODEL", os.getenv("GEMINI_MODEL"))
            
            try:
                COMPETENCIES_API_URL_LOCAL = os.getenv("COMPETENCIES_API_URL", "http://competencies_api:8003")
                # Pagination scalable : pages de 100 nœuds racines jusqu'à épuisement
                items: list = []
                skip = 0
                page_size = 100
                while True:
                    page_res = await http_client.get(
                        f"{COMPETENCIES_API_URL_LOCAL.rstrip('/')}/",
                        params={"skip": skip, "limit": page_size},
                        headers=headers, timeout=5.0
                    )
                    if page_res.status_code != 200:
                        break
                    page_items = page_res.json().get("items", [])
                    items.extend(page_items)
                    if len(page_items) < page_size:
                        break  # dernière page
                    skip += page_size

                if items:
                    taxonomy_context, _, _ = build_taxonomy_context(items)
                    # Mémoriser noms canoniques ET aliases pour le filtre Axe 4
                    # (évite de soumettre 'GCP' si 'Google Cloud Platform' a déjà l'alias 'GCP')
                    _taxonomy_leaf_names = _collect_all_known_names(items)
                    gemini_contents.append(taxonomy_context)
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
                            "summary": {"type": "string", "description": "Résume explicitement le contexte de la mission pour les archives, très utile s'il s'agit d'un PDF."},
                            "mission_duration_days": {
                                "type": "integer",
                                "description": "Durée totale estimée de la mission en jours ouvrés. Extraire depuis des mentions comme '3 mois', '6 semaines', '1 an', '2 sprints'. Convertir : 1 mois = 20 jours, 1 semaine = 5 jours. Retourner 0 si aucune durée n'est mentionnée."
                            }
                        }, 
                        "required": ["competencies", "summary", "mission_duration_days"]
                    }
                )
            )

            analytics_mcp_url = os.getenv("ANALYTICS_MCP_URL", "http://analytics_mcp:8008")

            async def fast_log_finops(action, model, usage):
                try:
                    inject(headers)
                    await http_client.post(
                        f"{analytics_mcp_url.rstrip('/')}/mcp/call",
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
                except Exception: raise
            await fast_log_finops("RAG_Mission_Extraction", model_extract, res_extract.usage_metadata)

            extracted_data = json.loads(res_extract.text)
            extracted_competencies = extracted_data.get("competencies", [])

            # ── Axe 4 : Boucle de rétroaction Mission → Taxonomie ─────────────────
            # Les compétences extraites mais absentes de la taxonomie sont soumises
            # pour révision admin via POST /suggestions dans competencies_api.
            COMPETENCIES_API_URL_LOCAL = os.getenv("COMPETENCIES_API_URL", "http://competencies_api:8003")
            try:
                # _taxonomy_leaf_names contient déjà les noms en lowercase (via _collect_all_known_names)
                known_leaves = _taxonomy_leaf_names if '_taxonomy_leaf_names' in dir() else set()
                new_skills = []
                for c in extracted_competencies:
                    if not c:
                        continue
                    c_clean = c.lower().strip()
                    c_no_parens = re.sub(r'\(.*?\)', '', c_clean).strip()
                    parens_matches = re.findall(r'\((.*?)\)', c_clean)
                    in_parens = any(p.strip() in known_leaves for p in parens_matches)
                    
                    if c_clean not in known_leaves and c_no_parens not in known_leaves and not in_parens:
                        new_skills.append(c)
                if new_skills:
                    logger.info(f"[Mission→Taxonomy] {len(new_skills)} compétences candidates à suggestion : {new_skills}")
                    suggest_tasks = [
                        http_client.post(
                            f"{COMPETENCIES_API_URL_LOCAL.rstrip('/')}/suggestions",
                            json={"name": skill, "source": "mission", "context": title},
                            headers=headers,
                            timeout=3.0,
                        )
                        for skill in new_skills
                    ]
                    await asyncio.gather(*suggest_tasks, return_exceptions=True)
            except Exception as e:
                logger.warning(f"[Mission→Taxonomy] Échec de la soumission des suggestions : {e}")
            
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
                    
                    skill_domains = find_domains_for_skills(skills, items)

                    return {
                        "user_id": u_id,
                        "full_name": u_info.get("full_name") or f"{u_info.get('first_name')} {u_info.get('last_name')}",
                        "seniority": seniority,
                        "skills": skills,
                        "skill_domains": skill_domains,
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
                model_staffing = os.getenv("GEMINI_MISSIONS_MODEL", os.getenv("GEMINI_MODEL"))
                mission_duration_days = extracted_data.get("mission_duration_days", 0) or 0
                logger.info(f"[Staffing] Durée de mission extraite : {mission_duration_days} jours")
                # Expliciter que candidates_data inclut les skill_domains pour aider le LLM
                staffing_prompt = (
                    f"{base_staffing_prompt}\n"
                    f"Mission: '{title}'. Description: '{final_description}'.\n"
                    f"Required Skills: {extracted_competencies}.\n"
                    f"mission_duration_days: {mission_duration_days} (0 means not explicitly specified in the document — apply role-based heuristics).\n"
                    f"Candidates (each mapped with their specific 'skills' and broad 'skill_domains'): {json.dumps(candidates_data)}."
                )
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
                emb_res = await embed_content_with_retry(client, model=os.getenv("GEMINI_EMBEDDING_MODEL"), contents=search_context)
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
