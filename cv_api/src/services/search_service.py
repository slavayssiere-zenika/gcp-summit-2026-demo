"""
search_service.py — Recherche sémantique RAG et scaling Cloud Run.

Ce module contient :
- execute_search()              — Recherche vectorielle pgvector + enrichissement users_api
- scale_bulk_dependencies()     — Scaling min_instances Cloud Run (Admin API)

Consommé par router.py pour les endpoints :
    GET  /search
    POST /search
"""

import asyncio
import logging
import os
from typing import List, Optional

import httpx
from fastapi import HTTPException
from fastapi.responses import Response
from fastapi.security import HTTPAuthorizationCredentials
from opentelemetry.propagate import inject
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func

from google.cloud import run_v2 as cloudrun_v2

from src.cvs.models import CVProfile
from src.services.config import (
    COMPETENCIES_API_URL,
    USERS_API_URL,
    GCP_PROJECT_ID,
    VERTEX_LOCATION,
    CLOUDRUN_WORKSPACE,
    BULK_SCALE_SERVICES,
)
from src.services.finops import log_finops
from metrics import CV_MISSING_EMBEDDINGS
from src.gemini_retry import generate_content_with_retry, embed_content_with_retry

logger = logging.getLogger(__name__)


async def execute_search(
    request,
    response: Response,
    query: str,
    limit: int,
    skills: List[str],
    db: AsyncSession,
    token_payload: dict,
    credentials: HTTPAuthorizationCredentials,
    genai_client,
    agency: Optional[str] = None,
) -> list:
    """Recherche sémantique (RAG) du meilleur candidat via pgvector cosine distance.

    L'agent interroge cette route lorsqu'il cherche des consultants par mots-clés
    ou description de projet.

    Étapes :
    1. Extraction des compétences obligatoires depuis la query (LLM filter).
    2. Embedding de la query (Gemini Embedding API).
    3. Recherche vectorielle pgvector (cosine distance).
    4. Pré-filtrage par compétences canoniques (competencies_api).
    5. Enrichissement des candidats avec users_api (full_name, email).

    Args:
        request: FastAPI Request pour récupérer Authorization.
        response: FastAPI Response pour injecter les headers X-*.
        query: Texte de la recherche.
        limit: Nombre maximum de résultats.
        skills: Liste de compétences pré-filtrées (override LLM si non vide).
        db: Session SQLAlchemy async.
        token_payload: Payload JWT décodé de l'appelant.
        credentials: Credentials HTTP pour FinOps.
        genai_client: Client GenAI initialisé (Gemini API key).
        agency: Filtre optionnel par agence/tag.

    Returns:
        Liste de dicts {user_id, similarity_score, full_name, email, ...}.

    Raises:
        HTTPException 400 si l'embedding échoue.
        HTTPException 404 si aucun candidat n'est trouvé.
        HTTPException 500 si le client GenAI n'est pas configuré.
    """
    from google.genai import types

    if not genai_client:
        raise HTTPException(status_code=500, detail="GenAI Client not configured.")

    # ── 0. Pré-filtrage AI — extraction des compétences obligatoires ─────────
    filter_res = None
    if skills is not None and len(skills) > 0:
        required_skills = skills
    else:
        try:
            filter_prompt = (
                "Extract a JSON list of strictly required technical competencies from this search query. "
                "Return ONLY a JSON array of strings (e.g. ['Python', 'AWS']), or an empty array if none are "
                f"strictly required.\nQuery: '{query}'"
            )
            filter_res = await generate_content_with_retry(
                genai_client,
                model=os.getenv("GEMINI_CV_MODEL", os.getenv("GEMINI_MODEL")),
                contents=filter_prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            )
            required_skills = __import__("json").loads(filter_res.text)
            if not isinstance(required_skills, list):
                required_skills = []
        except Exception as e:
            logger.warning(f"Skill extraction failed, proceeding without pre-filter: {e}")
            required_skills = []

    # ── 1. Embedding de la query ─────────────────────────────────────────────
    try:
        safe_embed_query = query[:3000] if query and len(query) > 3000 else query
        emb_res = await embed_content_with_retry(
            genai_client,
            model=os.getenv("GEMINI_EMBEDDING_MODEL"),
            contents=safe_embed_query,
        )
        search_vector = emb_res.embeddings[0].values

        user_caller = token_payload.get("sub", "unknown")

        if filter_res:
            await log_finops(
                user_caller,
                "search_filter_extraction",
                os.getenv("GEMINI_CV_MODEL", os.getenv("GEMINI_MODEL")),
                filter_res.usage_metadata,
                {"query": query},
                auth_token=credentials.credentials,
            )

        await log_finops(
            user_caller,
            "search_embedding",
            os.getenv("GEMINI_EMBEDDING_MODEL"),
            {"prompt_token_count": len(query) // 4, "candidates_token_count": 0},
            auth_token=credentials.credentials,
        )
    except Exception as e:
        logger.error(f"Erreur d'embedding API Gemini (query length={len(query)}): {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Embedding search query failed: {e}")

    # ── 2. Recherche vectorielle pgvector ────────────────────────────────────
    stmt = select(
        CVProfile,
        CVProfile.semantic_embedding.cosine_distance(search_vector).label("distance"),
    ).filter(CVProfile.semantic_embedding.is_not(None))

    if agency:
        stmt = stmt.filter(CVProfile.source_tag.ilike(f"%{agency}%"))

    # Vérification des embeddings manquants (anomalie data)
    try:
        missing_count_stmt = select(func.count(CVProfile.user_id)).filter(
            CVProfile.semantic_embedding.is_(None)
        )
        missing_count = (await db.execute(missing_count_stmt)).scalar() or 0
        CV_MISSING_EMBEDDINGS.set(missing_count)

        if missing_count > 0:
            logger.warning(f"Data Anomaly: {missing_count} CV profiles ignored due to missing embeddings!")
            if response:
                response.headers["X-Missing-Embeddings-Count"] = str(missing_count)
    except Exception as e:
        logger.error(f"Failed to calculate missing embeddings: {e}")

    # ── 3. Pré-filtrage par compétences canoniques ───────────────────────────
    fallback_scan = False

    if required_skills:
        approved_user_ids: set = set()
        auth_header = f"Bearer {credentials.credentials}" if credentials else ""
        headers_downstream = {"Authorization": auth_header} if auth_header else {}

        try:
            async with httpx.AsyncClient() as http_client:
                for skill in required_skills:
                    search_res = await http_client.get(
                        f"{COMPETENCIES_API_URL.rstrip('/')}/search",
                        params={"query": skill, "limit": 1},
                        headers=headers_downstream,
                    )
                    if search_res.status_code == 200:
                        items = search_res.json().get("items", [])
                        if items:
                            canonical_id = items[0]["id"]
                            users_res = await http_client.get(
                                f"{COMPETENCIES_API_URL.rstrip('/')}/{canonical_id}/users",
                                headers=headers_downstream,
                            )
                            if users_res.status_code == 200:
                                user_ids = users_res.json()
                                approved_user_ids.update(user_ids)
        except Exception as e:
            logger.warning(f"Canonical competencies resolution failed: {e}")

        if approved_user_ids:
            stmt_filtered = stmt.filter(CVProfile.user_id.in_(list(approved_user_ids)))
            query_results = (await db.execute(stmt_filtered.order_by("distance").limit(limit * 2))).all()
            if not query_results:
                fallback_scan = True
                query_results = (await db.execute(stmt.order_by("distance").limit(limit * 2))).all()
        else:
            fallback_scan = True
            query_results = (await db.execute(stmt.order_by("distance").limit(limit * 2))).all()
    else:
        query_results = (await db.execute(stmt.order_by("distance").limit(limit * 2))).all()

    if response:
        response.headers["X-Fallback-Full-Scan"] = str(fallback_scan).lower()

    # Déduplication et formatage
    mapped_results = []
    seen_users: set = set()

    for row, distance in query_results:
        if row.user_id not in seen_users:
            seen_users.add(row.user_id)
            score = 1.0 - (distance if distance is not None else 0.0)
            mapped_results.append({"user_id": row.user_id, "similarity_score": round(score, 4)})
            if len(mapped_results) >= limit:
                break

    # ── 4. Enrichissement via users_api ─────────────────────────────────────
    auth_header = request.headers.get("Authorization") if request else None
    headers_downstream = {"Authorization": auth_header} if auth_header else {}
    inject(headers_downstream)

    async with httpx.AsyncClient(timeout=10.0) as http_client:
        async def fetch_user(res):
            try:
                u_res = await http_client.get(
                    f"{USERS_API_URL.rstrip('/')}/{res['user_id']}",
                    headers=headers_downstream,
                )
                if u_res.status_code == 200:
                    u_data = u_res.json()
                    res["full_name"] = u_data.get("full_name")
                    res["email"] = u_data.get("email")
                    res["username"] = u_data.get("username")
                    res["is_active"] = u_data.get("is_active")
                    res["is_anonymous"] = u_data.get("is_anonymous", False)
            except Exception as e:
                logger.warning(f"HTTP Enrichment failed for user {res['user_id']}: {e}")

        await asyncio.gather(*(fetch_user(res) for res in mapped_results))

    if not mapped_results:
        raise HTTPException(
            status_code=404,
            detail=(
                "Aucun collaborateur correspondant à ces critères (compétences/expérience) "
                "n'a été trouvé dans la base de CVs Zenika."
            ),
        )

    return mapped_results


async def scale_bulk_dependencies(min_instances: int) -> None:
    """Élève ou abaisse le min_instance_count des services cibles via Cloud Run Admin API.

    Appelé en scale-up (min_instances=BULK_SCALE_MIN_INSTANCES, défaut 1) avant
    la phase APPLY et en scale-down (min_instances=0) en fin de pipeline.
    Configurable via BULK_SCALE_MIN_INSTANCES sans redéploiement.

    Dimensionnement pour 1000 CVs (BULK_APPLY_SEMAPHORE=5) :
      competencies_api : 15 req simultanées max, pool=30/instance → min=1 suffit
      items_api        : 10 req simultanées max, pool=30/instance → min=1 suffit
    Si BULK_APPLY_SEMAPHORE > 10, passer BULK_SCALE_MIN_INSTANCES à 2.

    En cas d'échec (IAM manquant, API indisponible), logue un warning sans lever
    d'exception pour ne pas bloquer le pipeline.
    """
    if not GCP_PROJECT_ID or not CLOUDRUN_WORKSPACE or not VERTEX_LOCATION:
        logger.warning(
            "[bulk_scale] GCP_PROJECT_ID/CLOUDRUN_WORKSPACE/VERTEX_LOCATION manquant — scaling ignoré."
        )
        return

    def _do_scale() -> list[str]:
        """Synchrone — appelé via asyncio.to_thread."""
        client = cloudrun_v2.ServicesClient()
        scaled = []
        for svc_base in BULK_SCALE_SERVICES:
            service_name = (
                f"projects/{GCP_PROJECT_ID}/locations/{VERTEX_LOCATION}"
                f"/services/{svc_base}-{CLOUDRUN_WORKSPACE}"
            )
            try:
                service = client.get_service(name=service_name)
                current = service.template.scaling.min_instance_count
                if current == min_instances:
                    scaled.append(f"{svc_base}: already at {min_instances}")
                    continue
                service.template.scaling.min_instance_count = min_instances
                op = client.update_service(
                    request=cloudrun_v2.UpdateServiceRequest(
                        service=service,
                        update_mask={"paths": ["template.scaling.min_instance_count"]},
                    )
                )
                scaled.append(f"{svc_base}: {current}→{min_instances} (LRO: {op.operation.name})")
            except Exception as e:
                logger.warning(f"[bulk_scale] Échec scale {service_name}: {type(e).__name__}: {e}")
                scaled.append(f"{svc_base}: ERROR({e})")
        return scaled

    try:
        results = await asyncio.to_thread(_do_scale)
        logger.info(f"[bulk_scale] min_instances={min_instances} — {results}")
    except Exception as e:
        logger.warning(f"[bulk_scale] _do_scale() échoué (non bloquant): {e}")
