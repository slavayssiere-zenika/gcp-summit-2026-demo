"""search_router.py — Recherche sémantique, similar, multi-criteria, RAG, mission-match."""
import asyncio
import logging
import math
import os
import re
import base64
import json
import traceback
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, List

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from fastapi.security import HTTPAuthorizationCredentials
from google import genai
from google.cloud import storage as gcs_storage
from google.cloud import run_v2 as cloudrun_v2
from opentelemetry.propagate import inject
from pydantic import BaseModel
from sqlalchemy import func, delete as sa_delete, text as sa_text, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from database import get_db
from src.auth import verify_jwt, security, SECRET_KEY as _AUTH_SECRET_KEY
from src.cvs.models import CVProfile
from src.cvs.schemas import (CVImportRequest, CVImportStep, CVResponse,
    SearchCandidateResponse, SearchCandidateRequest, CVProfileResponse,
    CVFullProfileResponse, UserMergeRequest, RankedExperienceResponse)
from src.cvs.task_state import task_state_manager, tree_task_manager
from src.cvs.bulk_task_state import bulk_reanalyse_manager
from src.cvs.routers._shared import (
    USERS_API_URL, COMPETENCIES_API_URL, PROMPTS_API_URL, DRIVE_API_URL,
    ITEMS_API_URL, MISSIONS_API_URL, ANALYTICS_MCP_URL, GCP_PROJECT_ID,
    VERTEX_LOCATION, BATCH_GCS_BUCKET, CLOUDRUN_WORKSPACE, BULK_SCALE_SERVICES,
    ADMIN_SERVICE_USERNAME, ADMIN_SERVICE_PASSWORD,
    BULK_APPLY_SEMAPHORE, BULK_EMBED_SEMAPHORE, BULK_SCALE_MIN_INSTANCES,
    CV_RESPONSE_SCHEMA as _CV_RESPONSE_SCHEMA,
    RecalculateStepRequest, MultiCriteriaSearchRequest,
)
from metrics import CV_PROCESSING_TOTAL, CV_MISSING_EMBEDDINGS
from src.gemini_retry import generate_content_with_retry, embed_content_with_retry
from src.services.cv_import_service import process_cv_core
from src.services.search_service import execute_search, scale_bulk_dependencies
import src.services.config as _svc_config  # _svc_config.client/_svc_config.vertex_batch_client via attribute access
from src.services.taxonomy_service import run_taxonomy_step, fetch_prompt, get_existing_competencies
from src.services.finops import log_finops
from src.services.embedding_service import reindex_embeddings_bg
from src.services.bulk_service import bg_bulk_reanalyse, _acquire_service_token, bg_retry_apply
from src.services.utils import _build_distilled_content, _clean_llm_json, _chunk_text

_fetch_prompt = fetch_prompt
_get_existing_competencies = get_existing_competencies
_bg_retry_apply = bg_retry_apply

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["CV Search"], dependencies=[Depends(verify_jwt)])

@router.get("/search", response_model=List[SearchCandidateResponse])
async def search_candidates(
    request: Request,
    response: Response,
    query: str, 
    limit: int = 5, 
    skills: List[str] = Query(default=None),
    agency: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    token_payload: dict = Depends(verify_jwt),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    return await execute_search(request, response, query, limit, skills, db, token_payload, credentials, _svc_config.client, agency)


@router.post("/search", response_model=List[SearchCandidateResponse])
async def search_candidates_post(
    req_body: SearchCandidateRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    token_payload: dict = Depends(verify_jwt),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    return await execute_search(request, response, req_body.query, req_body.limit, req_body.skills, db, token_payload, credentials, _svc_config.client, req_body.agency)


@router.get("/user/{user_id}/similar")
async def find_similar_consultants(
    user_id: int,
    limit: int = Query(default=5, le=20),
    agency: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    token_payload: dict = Depends(verify_jwt),
    request: Request = None,
):
    """Retourne les N consultants dont le profil sémantique est le plus proche d'un consultant donné.
    Utile pour : cloner un profil de staffing, trouver des remplaçants potentiels, constituer une équipe.
    Zéro appel LLM — résultat O(log N) grâce à l'index HNSW pgvector.
    """
    # Récupère l'embedding du profil source
    source_result = await db.execute(
        select(CVProfile.semantic_embedding).filter(CVProfile.user_id == user_id)
    )
    source_embedding = source_result.scalar_one_or_none()
    if source_embedding is None:
        raise HTTPException(status_code=404, detail=f"Profil introuvable ou embedding manquant pour user_id={user_id}")

    stmt = (
        select(CVProfile, CVProfile.semantic_embedding.cosine_distance(source_embedding).label("distance"))
        .filter(CVProfile.user_id != user_id)
        .filter(CVProfile.semantic_embedding.is_not(None))
    )
    if agency:
        stmt = stmt.filter(CVProfile.source_tag.ilike(f"%{agency}%"))

    stmt = stmt.order_by("distance").limit(limit)
    rows = (await db.execute(stmt)).all()

    auth_header = request.headers.get("Authorization") if request else None
    headers_downstream = {"Authorization": auth_header} if auth_header else {}
    inject(headers_downstream)

    results = []
    async with httpx.AsyncClient(timeout=8.0) as http_client:
        for profile, distance in rows:
            entry = {
                "user_id": profile.user_id,
                "similarity_score": round(max(0.0, 1.0 - distance), 4),
                "current_role": profile.current_role,
                "years_of_experience": profile.years_of_experience,
                "source_tag": profile.source_tag,
            }
            try:
                u_res = await http_client.get(
                    f"{USERS_API_URL.rstrip('/')}/{profile.user_id}", headers=headers_downstream
                )
                if u_res.status_code == 200:
                    u_data = u_res.json()
                    entry["full_name"] = u_data.get("full_name")
                    entry["email"] = u_data.get("email")
            except Exception as e:
                logger.warning(f"[SIMILAR] Enrichissement user {profile.user_id} échoué: {e}")
            results.append(entry)

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Sprint A2 — Recherche multi-critères (N vecteurs pondérés, 1 requête SQL)
# ─────────────────────────────────────────────────────────────────────────────

class MultiCriteriaSearchRequest(BaseModel):
    queries: List[str]
    weights: Optional[List[float]] = None
    limit: int = 10
    agency: Optional[str] = None



@router.post("/search/multi-criteria")
async def search_candidates_multi_criteria(
    req_body: MultiCriteriaSearchRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    token_payload: dict = Depends(verify_jwt),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Recherche sémantique multi-critères : trouve les consultants correspondant à
    PLUSIEURS dimensions simultanément via une moyenne pondérée de distances cosine.
    Remplace N appels search_best_candidates séquentiels par une seule requête SQL.
    Exemple : queries=["expert GCP", "migration legacy"], weights=[0.7, 0.3]
    """
    if not _svc_config.client:
        raise HTTPException(status_code=500, detail="Client Gemini non configuré.")
    if not req_body.queries:
        raise HTTPException(status_code=400, detail="Au moins une query est requise.")
    if len(req_body.queries) > 5:
        raise HTTPException(status_code=400, detail="Maximum 5 critères simultanés.")

    weights = req_body.weights or [1.0 / len(req_body.queries)] * len(req_body.queries)
    if len(weights) != len(req_body.queries):
        raise HTTPException(status_code=400, detail="Nombre de weights ≠ nombre de queries.")

    # Normaliser les weights pour que leur somme = 1
    total_w = sum(weights)
    weights = [w / total_w for w in weights]

    # Calculer un embedding par query
    embeddings = []
    for q in req_body.queries:
        try:
            emb_res = await embed_content_with_retry(
                _svc_config.client,
                model=os.getenv("GEMINI_EMBEDDING_MODEL"),
                contents=q[:3000]
            )
            embeddings.append(emb_res.embeddings[0].values)
        except Exception as e:
            logger.error(f"[MULTI-SEARCH] Embedding échoué pour query '{q}': {e}")
            raise HTTPException(status_code=400, detail=f"Embedding échoué pour: {q}")

    # Score combiné = somme pondérée des distances cosine
    combined_distance = sum(
        CVProfile.semantic_embedding.cosine_distance(emb) * w
        for emb, w in zip(embeddings, weights)
    )

    stmt = (
        select(CVProfile, combined_distance.label("combined_distance"))
        .filter(CVProfile.semantic_embedding.is_not(None))
    )
    if req_body.agency:
        stmt = stmt.filter(CVProfile.source_tag.ilike(f"%{req_body.agency}%"))
    stmt = stmt.order_by("combined_distance").limit(req_body.limit * 2)

    rows = (await db.execute(stmt)).all()

    user_caller = token_payload.get("sub", "unknown")
    for q in req_body.queries:
        await log_finops(
            user_caller, "multi_criteria_embedding",
            os.getenv("GEMINI_EMBEDDING_MODEL"),
            {"prompt_token_count": len(q) // 4, "candidates_token_count": 0},
            auth_token=credentials.credentials
        )

    auth_header = request.headers.get("Authorization")
    headers_downstream = {"Authorization": auth_header} if auth_header else {}
    inject(headers_downstream)

    results, seen = [], set()
    async with httpx.AsyncClient(timeout=8.0) as http_client:
        for profile, dist in rows:
            if profile.user_id in seen:
                continue
            seen.add(profile.user_id)
            score = round(max(0.0, 1.0 - float(dist)), 4)
            entry = {
                "user_id": profile.user_id,
                "combined_similarity": score,
                "current_role": profile.current_role,
                "years_of_experience": profile.years_of_experience,
                "source_tag": profile.source_tag,
            }
            try:
                u_res = await http_client.get(
                    f"{USERS_API_URL.rstrip('/')}/{profile.user_id}", headers=headers_downstream
                )
                if u_res.status_code == 200:
                    u_data = u_res.json()
                    entry["full_name"] = u_data.get("full_name")
                    entry["email"] = u_data.get("email")
            except Exception as e:
                logger.warning(f"[MULTI-SEARCH] Enrichissement user {profile.user_id} échoué: {e}")
            results.append(entry)
            if len(results) >= req_body.limit:
                break

    if not results:
        raise HTTPException(status_code=404, detail="Aucun candidat correspondant à ces critères combinés.")
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Sprint A3 — RAG Snippet (passages les plus pertinents d'un CV pour une query)
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/user/{user_id}/rag-snippet")
async def get_rag_snippet(
    user_id: int,
    query: str = Query(..., description="La requête pour laquelle chercher les passages pertinents"),
    top_k: int = Query(default=3, le=5),
    db: AsyncSession = Depends(get_db),
    token_payload: dict = Depends(verify_jwt),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Retourne les passages les plus pertinents du CV d'un consultant pour une query donnée.
    Utilise un chunking du distilled_content + re-ranking par similarité cosine.
    Permet de JUSTIFIER une recommandation avec des preuves textuelles précises.
    Timeout MCP : 30s (embedding de la query + N passages).
    """
    if not _svc_config.client:
        raise HTTPException(status_code=500, detail="Client Gemini non configuré.")

    profile = (await db.execute(
        select(CVProfile).filter(CVProfile.user_id == user_id).order_by(CVProfile.created_at.desc())
    )).scalars().first()

    if not profile:
        raise HTTPException(status_code=404, detail=f"Profil introuvable pour user_id={user_id}")

    # Reconstituer le distilled_content depuis les champs structurés en base
    structured_cv = {
        "current_role": profile.current_role or "Unknown",
        "years_of_experience": profile.years_of_experience or 0,
        "summary": profile.summary or "",
        "competencies": [{"name": k} for k in (profile.competencies_keywords or [])],
        "educations": profile.educations or [],
        "missions": profile.missions or [],
    }
    distilled = _build_distilled_content(structured_cv)

    # Chunking du contenu distillé
    passages = _chunk_text(distilled, chunk_size=150, overlap=20)
    if not passages:
        return {"user_id": user_id, "snippets": [], "message": "Aucun contenu disponible pour ce profil."}

    # Embedding de la query
    try:
        query_emb_res = await embed_content_with_retry(
            _svc_config.client,
            model=os.getenv("GEMINI_EMBEDDING_MODEL"),
            contents=query[:3000]
        )
        query_vector = query_emb_res.embeddings[0].values
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Embedding de la query échoué: {e}")

    # Embedding de chaque passage (parallèle, max 10 passages)
    passages_to_rank = passages[:10]

    async def embed_passage(p: str):
        try:
            res = await embed_content_with_retry(
                _svc_config.client,
                model=os.getenv("GEMINI_EMBEDDING_MODEL"),
                contents=p
            )
            return res.embeddings[0].values
        except Exception:
            return None

    passage_embeddings = await asyncio.gather(*[embed_passage(p) for p in passages_to_rank])

    # Cosine similarity inline (pgvector non dispo ici — calcul Python sur N<10 passages)

    def cosine_sim(a, b):
        if not a or not b:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        return dot / (norm_a * norm_b + 1e-9)

    ranked = sorted(
        [(passages_to_rank[i], cosine_sim(query_vector, passage_embeddings[i]))
         for i in range(len(passages_to_rank)) if passage_embeddings[i] is not None],
        key=lambda x: x[1],
        reverse=True
    )

    await log_finops(
        token_payload.get("sub", "unknown"),
        "rag_snippet",
        os.getenv("GEMINI_EMBEDDING_MODEL"),
        {"prompt_token_count": (len(query) + len(distilled)) // 4, "candidates_token_count": 0},
        auth_token=credentials.credentials
    )

    return {
        "user_id": user_id,
        "query": query,
        "snippets": [
            {"text": text, "relevance_score": round(score, 4)}
            for text, score in ranked[:top_k]
        ]
    }



@router.post("/search/mission-match")
async def match_mission_to_candidates(
    request: Request,
    mission_id: int = Query(..., description="ID de la mission à staffer"),
    limit: int = Query(default=10, le=50),
    agency: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    token_payload: dict = Depends(verify_jwt),
):
    """Matching direct mission → candidats via le semantic_embedding de la mission.
    Plus précis que search_best_candidates pour le staffing car utilise le contexte
    complet de la mission (description + compétences extraites). Zéro appel LLM.
    Requiert que la mission ait été analysée par l'IA (semantic_embedding alimenté).
    """
    auth_header = request.headers.get("Authorization")
    headers_downstream = {"Authorization": auth_header} if auth_header else {}
    inject(headers_downstream)

    # 1. Récupérer l'embedding de la mission depuis missions_api
    try:
        async with httpx.AsyncClient(timeout=10.0) as http_client:
            mission_res = await http_client.get(
                f"{MISSIONS_API_URL.rstrip('/')}/missions/{mission_id}",
                headers=headers_downstream
            )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"missions_api inaccessible: {e}")

    if mission_res.status_code == 404:
        raise HTTPException(status_code=404, detail=f"Mission {mission_id} introuvable.")
    if mission_res.status_code != 200:
        raise HTTPException(status_code=502, detail=f"missions_api erreur HTTP {mission_res.status_code}")

    # Récupérer l'embedding directement en base (missions_api ne l'expose pas via l'API REST)
    # On requête cv_api's DB pour la mission via missions_api internal
    async with httpx.AsyncClient(timeout=10.0) as http_client:
        emb_res = await http_client.get(
            f"{MISSIONS_API_URL.rstrip('/')}/missions/{mission_id}/embedding",
            headers=headers_downstream
        )

    mission_embedding = None
    if emb_res.status_code == 200:
        mission_embedding = emb_res.json().get("embedding")

    if not mission_embedding:
        raise HTTPException(
            status_code=422,
            detail=f"La mission {mission_id} n'a pas d'embedding vectoriel. Lancez une ré-analyse via missions_api d'abord."
        )

    # 2. Cosine search dans cv_profiles
    stmt = (
        select(CVProfile, CVProfile.semantic_embedding.cosine_distance(mission_embedding).label("distance"))
        .filter(CVProfile.semantic_embedding.is_not(None))
    )
    if agency:
        stmt = stmt.filter(CVProfile.source_tag.ilike(f"%{agency}%"))
    stmt = stmt.order_by("distance").limit(limit)

    rows = (await db.execute(stmt)).all()

    results = []
    async with httpx.AsyncClient(timeout=8.0) as http_client:
        for profile, distance in rows:
            entry = {
                "user_id": profile.user_id,
                "similarity_score": round(max(0.0, 1.0 - distance), 4),
                "current_role": profile.current_role,
                "years_of_experience": profile.years_of_experience,
                "source_tag": profile.source_tag,
            }
            try:
                u_res = await http_client.get(
                    f"{USERS_API_URL.rstrip('/')}/{profile.user_id}", headers=headers_downstream
                )
                if u_res.status_code == 200:
                    u_data = u_res.json()
                    entry["full_name"] = u_data.get("full_name")
                    entry["email"] = u_data.get("email")
            except Exception as e:
                logger.warning(f"[MISSION-MATCH] Enrichissement user {profile.user_id} échoué: {e}")
            results.append(entry)

    if not results:
        raise HTTPException(status_code=404, detail=f"Aucun candidat trouvé pour la mission {mission_id}.")
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Sprint C1 — Analytics : couverture des compétences corpus
# ─────────────────────────────────────────────────────────────────────────────

