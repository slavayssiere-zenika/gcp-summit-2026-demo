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
from google.cloud import run_v2 as cloudrun_v2
from pydantic import ValidationError
from sqlalchemy import text
from shared.schemas.pagination import PaginationResponse
from metrics import CV_MISSING_EMBEDDINGS, CV_SEARCH_THRESHOLD_FILTERED, CV_SEARCH_RESULT_SCORE
from opentelemetry.propagate import inject
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from src.cvs.models import CVProfile
from src.gemini_retry import (embed_content_with_retry,
                              generate_content_with_retry)
from src.services.config import (BULK_SCALE_SERVICES, CLOUDRUN_WORKSPACE,
                                 COMPETENCIES_API_URL, GCP_PROJECT_ID,
                                 USERS_API_URL, VERTEX_LOCATION)
from src.services.finops import log_finops
from google.genai import types
from src.cvs.models import CVMissionEmbedding

logger = logging.getLogger(__name__)

# R2 — Seuil de pertinence : les candidats au-delà de ce seuil cosine distance
# sont considérés hors-sujet et exclus du résultat.
# Valeur par défaut 0.55 (distance cosine, soit ~0.45 de similarité).
# Réduire pour être plus strict, augmenter pour avoir plus de résultats.
VECTOR_DISTANCE_THRESHOLD = float(os.getenv("VECTOR_DISTANCE_THRESHOLD", "0.55"))

# 2.12 — Pool maximum de candidats explorés par la recherche vectorielle.
# Remplace le pattern anti-pattern (limit+skip)*2 qui rendait invisibles
# les candidats au-delà du rang 100.
# Le filtre R2 (VECTOR_DISTANCE_THRESHOLD) garantit la qualité de ce pool.
# Ajuster selon la taille du corpus : 500 pour <5k CVs, 1000 pour >5k CVs.
MAX_VECTOR_CANDIDATES = int(os.getenv("MAX_VECTOR_CANDIDATES", "500"))


async def execute_search(
    request,
    response: Response,
    query: str,
    skip: int,
    limit: int,
    skills: List[str],
    db: AsyncSession,
    token_payload: dict,
    credentials: HTTPAuthorizationCredentials,
    genai_client,
    agency: Optional[str] = None,
) -> dict:
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
        skip: Nombre de résultats à ignorer.
        limit: Nombre maximum de résultats.
        skills: Liste de compétences pré-filtrées (override LLM si non vide).
        db: Session SQLAlchemy async.
        token_payload: Payload JWT décodé de l'appelant.
        credentials: Credentials HTTP pour FinOps.
        genai_client: Client GenAI initialisé (Gemini API key).
        agency: Filtre optionnel par agence/tag.

    Returns:
        Dictionnaire avec les clés items, total, skip, limit.

    Raises:
        HTTPException 400 si l'embedding échoue.
        HTTPException 404 si aucun candidat n'est trouvé.
        HTTPException 500 si le client GenAI n'est pas configuré.
    """

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
            config={"task_type": "RETRIEVAL_QUERY"},
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
    current_embedding_model = os.getenv("GEMINI_EMBEDDING_MODEL")
    stmt = select(
        CVProfile,
        CVProfile.semantic_embedding.cosine_distance(search_vector).label("distance"),
    ).filter(CVProfile.semantic_embedding.is_not(None))

    # R1 — Filtre par version du modèle d'embedding (cohérence vectorielle)
    # Autorise aussi les profils sans modèle enregistré (antérieurs à la migration R1).
    if current_embedding_model:
        stmt = stmt.filter(
            (CVProfile.embedding_model == current_embedding_model)
            | (CVProfile.embedding_model.is_(None))
        )

    # R2 — Seuil de pertinence : exclut les candidats trop éloignés sémantiquement.
    # Configurable via VECTOR_DISTANCE_THRESHOLD (défaut 0.55).
    stmt = stmt.filter(
        CVProfile.semantic_embedding.cosine_distance(search_vector) < VECTOR_DISTANCE_THRESHOLD
    )

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
            limits = httpx.Limits(max_keepalive_connections=50, max_connections=100)
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=3.0), limits=limits) as http_client:
                async def fetch_canonical_skill(skill: str):
                    skill_users = set()
                    try:
                        search_res = await http_client.get(
                            f"{COMPETENCIES_API_URL.rstrip('/')}/search",
                            params={"query": skill, "limit": 1},
                            headers=headers_downstream,
                        )
                        if search_res.status_code == 200:
                            try:
                                page_data = PaginationResponse[dict].model_validate(search_res.json())
                                items = page_data.items
                            except ValidationError as ve:
                                logger.warning(
                                    "[search_service] Rupture de contrat API competencies/search",
                                    extra={"skill": skill, "error": str(ve)},
                                )
                                items = []
                            if items:
                                canonical_id = items[0]["id"]
                                users_res = await http_client.get(
                                    f"{COMPETENCIES_API_URL.rstrip('/')}/{canonical_id}/users",
                                    headers=headers_downstream,
                                )
                                if users_res.status_code == 200:
                                    skill_users.update(users_res.json())
                    except Exception as e:
                        logger.warning(f"Canonical competencies resolution failed for {skill}: {e}")
                    return skill_users

                tasks = [fetch_canonical_skill(skill) for skill in required_skills]
                results = await asyncio.gather(*tasks)
                for res in results:
                    approved_user_ids.update(res)
        except Exception as e:
            logger.warning(f"Canonical competencies resolution failed: {e}")

        if approved_user_ids:
            stmt_filtered = stmt.filter(CVProfile.user_id.in_(list(approved_user_ids)))
            query_results = (
                await db.execute(stmt_filtered.order_by("distance").limit(MAX_VECTOR_CANDIDATES))
            ).all()
            if not query_results:
                fallback_scan = True
                query_results = (
                    await db.execute(stmt.order_by("distance").limit(MAX_VECTOR_CANDIDATES))
                ).all()
        else:
            fallback_scan = True
            query_results = (
                await db.execute(stmt.order_by("distance").limit(MAX_VECTOR_CANDIDATES))
            ).all()
    else:
        query_results = (
            await db.execute(stmt.order_by("distance").limit(MAX_VECTOR_CANDIDATES))
        ).all()

    if response:
        response.headers["X-Fallback-Full-Scan"] = str(fallback_scan).lower()

    # Déduplication et formatage
    mapped_results = []
    seen_users: set = set()
    agency_label = agency or "all"

    # R6 — Calcul du nombre de candidats élagués par le seuil R2
    # On exécute la même query SANS le filtre de distance pour avoir le total brut
    stmt_unfiltered = select(
        func.count(CVProfile.user_id)
    ).filter(CVProfile.semantic_embedding.is_not(None))
    if current_embedding_model:
        stmt_unfiltered = stmt_unfiltered.filter(
            (CVProfile.embedding_model == current_embedding_model)
            | (CVProfile.embedding_model.is_(None))
        )
    if agency:
        stmt_unfiltered = stmt_unfiltered.filter(CVProfile.source_tag.ilike(f"%{agency}%"))
    total_before_threshold = (await db.execute(stmt_unfiltered)).scalar() or 0
    filtered_count = max(0, total_before_threshold - len(query_results))
    if filtered_count > 0:
        CV_SEARCH_THRESHOLD_FILTERED.labels(agency=agency_label).inc(filtered_count)
    if response:
        response.headers["X-Threshold-Filtered-Count"] = str(filtered_count)
        response.headers["X-Distance-Threshold"] = str(VECTOR_DISTANCE_THRESHOLD)

    for row, distance in query_results:
        if row.user_id not in seen_users:
            seen_users.add(row.user_id)
            score = 1.0 - (distance if distance is not None else 0.0)
            # R6 — Observe la distribution des scores dans l'histogram
            CV_SEARCH_RESULT_SCORE.observe(score)
            mapped_results.append({
                "user_id": row.user_id,
                "similarity_score": round(score, 4),
                # R5 — Citation de la source documentaire (URL Drive)
                "source_url": row.source_url,
                "embedding_model": row.embedding_model,
            })

    total = len(mapped_results)
    paginated_results = mapped_results[skip:skip+limit]

    # ── 4. Enrichissement via users_api ─────────────────────────────────────
    auth_header = request.headers.get("Authorization") if request else None
    headers_downstream = {"Authorization": auth_header} if auth_header else {}
    inject(headers_downstream)

    limits = httpx.Limits(max_keepalive_connections=50, max_connections=100)
    async with httpx.AsyncClient(timeout=10.0, limits=limits) as http_client:
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

        await asyncio.gather(*(fetch_user(res) for res in paginated_results))

    if not paginated_results and skip == 0:
        raise HTTPException(
            status_code=404,
            detail=(
                "Aucun collaborateur correspondant à ces critères (compétences/expérience) "
                "n'a été trouvé dans la base de CVs Zenika."
            ),
        )

    return {"items": paginated_results, "total": total, "skip": skip, "limit": limit}


async def execute_search_chunked(
    request,
    response,
    query: str,
    skip: int,
    limit: int,
    db: AsyncSession,
    token_payload: dict,
    credentials,
    genai_client,
    agency: Optional[str] = None,
) -> dict:
    """R7 — Recherche RAG multi-vecteur (chunk-level) via cv_mission_embeddings.

    Stratégie de scoring MAX + bonus :
    - Score de base = 1 - MIN(distance cosine) parmi tous les chunks du consultant
    - Bonus +0.05 si >= 2 chunks passent le seuil VECTOR_DISTANCE_THRESHOLD
      (indique une profondeur d'expertise, pas une occurrence isolée)

    Activé via la variable d'env RAG_CHUNKED_SEARCH=true.
    Fallback automatique sur execute_search() si la table est vide.
    """

    if not genai_client:
        raise HTTPException(status_code=500, detail="GenAI Client not configured.")

    # ── 1. Embedding de la query ─────────────────────────────────────────────
    try:
        safe_query = query[:3000] if query and len(query) > 3000 else query
        emb_res = await embed_content_with_retry(
            genai_client,
            model=os.getenv("GEMINI_EMBEDDING_MODEL"),
            contents=safe_query,
            config={"task_type": "RETRIEVAL_QUERY"},
        )
        search_vector = emb_res.embeddings[0].values
        await log_finops(
            token_payload.get("sub", "unknown"),
            "search_chunked_embedding",
            os.getenv("GEMINI_EMBEDDING_MODEL"),
            {"prompt_token_count": len(query) // 4, "candidates_token_count": 0},
            auth_token=credentials.credentials if credentials else None,
        )
    except Exception as e:
        logger.error(f"[CHUNKED_SEARCH] Embedding query échoué: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Embedding search query failed: {e}")

    # ── 2. Vérification que la table chunks est peuplée ──────────────────────
    count_stmt = select(func.count(CVMissionEmbedding.id)).filter(
        CVMissionEmbedding.chunk_embedding.is_not(None)
    )
    chunk_count = (await db.execute(count_stmt)).scalar() or 0
    if chunk_count == 0:
        logger.warning(
            "[CHUNKED_SEARCH] Table cv_mission_embeddings vide — "
            "fallback sur recherche globale. Lancez /reindex-mission-chunks."
        )
        return await execute_search(
            request, response, query, skip, limit, [], db,
            token_payload, credentials, genai_client, agency,
        )

    # ── 3. Requête pgvector groupée par user_id ───────────────────────────────
    # MIN(distance) = meilleur chunk (score MAX)
    # COUNT FILTER = nombre de chunks sous le seuil (profondeur)
    current_model = os.getenv("GEMINI_EMBEDDING_MODEL")
    vector_str = f"[{','.join(str(v) for v in search_vector)}]"

    raw_sql = text("""
        SELECT
            user_id,
            MIN(chunk_embedding <=> CAST(:vec AS vector)) AS best_distance,
            COUNT(*) FILTER (
                WHERE chunk_embedding <=> CAST(:vec AS vector) < :threshold
            ) AS matching_chunks
        FROM cv_mission_embeddings
        WHERE chunk_embedding IS NOT NULL
          AND (CAST(:model AS text) IS NULL OR embedding_model = CAST(:model AS text))
          AND (CAST(:agency AS text) IS NULL OR source_tag ILIKE CAST(:agency_pattern AS text))
          AND chunk_embedding <=> CAST(:vec AS vector) < :threshold
        GROUP BY user_id
        ORDER BY best_distance ASC
        LIMIT :max_candidates
    """)

    rows = (await db.execute(raw_sql, {
        "vec": vector_str,
        "threshold": VECTOR_DISTANCE_THRESHOLD,
        "model": current_model,
        "agency": agency,
        "agency_pattern": f"%{agency}%" if agency else None,
        "max_candidates": MAX_VECTOR_CANDIDATES,
    })).fetchall()

    # ── 4. Scoring MAX + bonus profondeur ────────────────────────────────────
    DEPTH_BONUS = 0.05
    mapped_results = []
    for row in rows:
        user_id, best_distance, matching_chunks = row
        base_score = 1.0 - (best_distance if best_distance is not None else 0.0)
        depth_bonus = DEPTH_BONUS if (matching_chunks or 0) >= 2 else 0.0
        final_score = min(1.0, round(base_score + depth_bonus, 4))
        CV_SEARCH_RESULT_SCORE.observe(final_score)
        mapped_results.append({
            "user_id": user_id,
            "similarity_score": final_score,
            "matching_chunks": int(matching_chunks or 0),
            "source_url": None,  # enrichi dans l'étape 5
            "embedding_model": current_model,
        })

    if response:
        response.headers["X-Chunked-Search"] = "true"
        response.headers["X-Distance-Threshold"] = str(VECTOR_DISTANCE_THRESHOLD)
        response.headers["X-Threshold-Filtered-Count"] = str(len(rows))

    total = len(mapped_results)
    paginated_results = mapped_results[skip:skip + limit]

    # ── 5. Enrichissement via users_api ─────────────────────────────────────
    auth_header = request.headers.get("Authorization") if request else None
    headers_downstream = {"Authorization": auth_header} if auth_header else {}
    inject(headers_downstream)

    limits = httpx.Limits(max_keepalive_connections=50, max_connections=100)
    async with httpx.AsyncClient(timeout=10.0, limits=limits) as http_client:
        async def fetch_user_chunked(res):
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
                logger.warning(f"[CHUNKED_SEARCH] Enrichissement user {res['user_id']}: {e}")

        await asyncio.gather(*(fetch_user_chunked(res) for res in paginated_results))

    if not paginated_results and skip == 0:
        raise HTTPException(
            status_code=404,
            detail=(
                "Aucun collaborateur correspondant à ces critères n'a été trouvé "
                "(recherche multi-vecteur)."
            ),
        )

    return {"items": paginated_results, "total": total, "skip": skip, "limit": limit}


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
