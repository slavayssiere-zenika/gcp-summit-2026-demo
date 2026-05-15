"""
embedding_service.py — Re-indexation des embeddings vectoriels.

Ce module contient :
- reindex_embeddings_bg()        — Background task : recalcule le vecteur global
- reindex_mission_chunks_bg()    — Background task : génère les chunks multi-vecteur (R7)

Consommé par router.py pour les endpoints :
    POST /reindex-embeddings
    POST /bulk-reanalyse/reindex-mission-chunks
"""

import asyncio
import logging
import math
import os
from typing import Optional

import shared.database as database
from opentelemetry.propagate import inject
from sqlalchemy import delete
from sqlalchemy.future import select
from src.cvs.models import CVMissionEmbedding, CVProfile
from src.gemini_retry import embed_content_with_retry
from src.services.finops import log_finops
from src.services.utils import (
    _build_distilled_content,
    _build_mission_chunk_text,
    _build_profile_summary_chunk,
)

logger = logging.getLogger(__name__)


async def reindex_embeddings_bg(
    tag: Optional[str],
    user_id_filter: Optional[int],
    auth_token: Optional[str],
    genai_client,
) -> None:
    """Background task : recalcule les embeddings de tous les CVs.

    N'exécute PAS l'extraction LLM — utilise les données structurées déjà en base.
    Conforme AGENTS.md §4 : le token de service est propagé pour le FinOps tracking.

    Args:
        tag: Filtre optionnel par agence (source_tag ILIKE %tag%).
        user_id_filter: Filtre optionnel par user_id.
        auth_token: Token JWT du service pour les appels FinOps.
        genai_client: Client GenAI initialisé (Gemini API key).
    """
    logger.info(
        f"[REINDEX] Démarrage re-indexation embeddings (tag={tag}, user_id={user_id_filter})"
    )
    if not genai_client:
        logger.error("[REINDEX] Client Gemini non configuré — re-indexation annulée.")
        return

    headers: dict = {"Authorization": auth_token} if auth_token else {}
    inject(headers)

    try:
        async for db in database.get_db():
            stmt = select(CVProfile)
            if tag:
                stmt = stmt.filter(CVProfile.source_tag.ilike(f"%{tag}%"))
            if user_id_filter:
                stmt = stmt.filter(CVProfile.user_id == user_id_filter)
            profiles = (await db.execute(stmt)).scalars().all()

            total = len(profiles)
            logger.info(f"[REINDEX] {total} profils à re-indexer")
            success, failed = 0, 0
            _progress_step = max(1, total // 10)  # log tous les 10%

            for idx, profile in enumerate(profiles):
                try:
                    # Reconstituer structured_cv depuis les champs BDD
                    structured_cv = {
                        "current_role": profile.current_role or "Unknown",
                        "years_of_experience": profile.years_of_experience or 0,
                        "summary": profile.summary or "",
                        "competencies": [
                            {"name": k} for k in (profile.competencies_keywords or [])
                        ],
                        "educations": profile.educations or [],
                        "missions": profile.missions or [],
                    }
                    distilled_content = _build_distilled_content(structured_cv)

                    emb_res = await embed_content_with_retry(
                        genai_client,
                        model=os.getenv("GEMINI_EMBEDDING_MODEL"),
                        contents=distilled_content,
                        config={"task_type": "RETRIEVAL_DOCUMENT"},
                    )
                    profile.semantic_embedding = emb_res.embeddings[0].values
                    # R1 — MàJ du modèle d'embedding pour ce profil
                    profile.embedding_model = os.getenv("GEMINI_EMBEDDING_MODEL")

                    # Extraction quality test during re-index
                    raw_snippet = profile.raw_content[:20000] if profile.raw_content else ""
                    if raw_snippet:
                        raw_emb_res = await embed_content_with_retry(
                            genai_client,
                            model=os.getenv("GEMINI_EMBEDDING_MODEL"),
                            contents=raw_snippet,
                            config={"task_type": "RETRIEVAL_DOCUMENT"},
                        )
                        raw_vector = raw_emb_res.embeddings[0].values

                        vector_data = profile.semantic_embedding
                        dot_product = sum(a * b for a, b in zip(vector_data, raw_vector))
                        norm_v1 = math.sqrt(sum(a * a for a in vector_data))
                        norm_v2 = math.sqrt(sum(b * b for b in raw_vector))
                        if norm_v1 > 0 and norm_v2 > 0:
                            sim = dot_product / (norm_v1 * norm_v2)
                            profile.extraction_reliability_score = min(100, max(0, int(sim * 100)))

                    # FinOps tracking
                    await log_finops(
                        "system-reindex",
                        "reindex_embedding",
                        os.getenv("GEMINI_EMBEDDING_MODEL"),
                        {
                            "prompt_token_count": len(distilled_content) // 4,
                            "candidates_token_count": 0,
                        },
                        auth_token=auth_token,
                    )
                    success += 1

                    # Log de progression tous les 10%
                    if total > 0 and (idx + 1) % _progress_step == 0:
                        pct = round((idx + 1) / total * 100)
                        logger.info(
                            f"[REINDEX] Progression {pct}% — "
                            f"{idx + 1}/{total} traités ({success} ok, {failed} échecs)"
                        )

                except Exception as e:
                    logger.error(
                        f"[REINDEX] Embedding échoué pour user_id={profile.user_id} "
                        f"(role={profile.current_role!r}): {e}"
                    )
                    failed += 1

            await db.commit()
            logger.info(f"[REINDEX] Terminé — {success} succès, {failed} échecs")
            break
    except Exception as e:
        logger.error(f"[REINDEX] Erreur critique: {e}", exc_info=True)


async def reindex_mission_chunks_bg(
    tag: Optional[str],
    user_id_filter: Optional[int],
    auth_token: Optional[str],
    genai_client,
    semaphore_count: int = 5,
    force: bool = False,
) -> None:
    """Background task R7 : génère les chunk-level embeddings pour le RAG multi-vecteur.

    Pour chaque CVProfile :
    - Si force=False (défaut) : skip les profils déjà indexés (reprise après restart).
    - Si force=True : supprime les chunks existants et recrée tout (re-indexation complète).
    - Crée 1 chunk 'profile_summary' (ROLE + SUMMARY + COMPETENCIES, sans missions).
    - Crée N chunks 'mission' (une par mission, TOUTES sans limite de 6).

    Scoring en recherche (execute_search_chunked) :
    - Score = MAX des similarités parmi tous les chunks du consultant.
    - Bonus +0.05 si >= 2 chunks passent le seuil (profondeur d'expertise).

    Args:
        tag: Filtre optionnel par agence (source_tag ILIKE %tag%).
        user_id_filter: Filtre optionnel par user_id.
        auth_token: Token JWT du service pour les appels FinOps.
        genai_client: Client GenAI initialisé (Gemini API key).
        semaphore_count: Concurrence max des appels Gemini (défaut 5).
        force: Si True, supprime et recrée tous les chunks (défaut False = reprise).
    """
    logger.info(
        f"[CHUNK_REINDEX] Démarrage (tag={tag}, user_id={user_id_filter}, "
        f"semaphore={semaphore_count}, force={force})"
    )
    if not genai_client:
        logger.error("[CHUNK_REINDEX] Client Gemini non configuré — reindex annulé.")
        return

    headers: dict = {"Authorization": auth_token} if auth_token else {}
    inject(headers)
    sem = asyncio.Semaphore(semaphore_count)
    embedding_model = os.getenv("GEMINI_EMBEDDING_MODEL")

    try:
        async for db in database.get_db():
            stmt = select(CVProfile)
            if tag:
                stmt = stmt.filter(CVProfile.source_tag.ilike(f"%{tag}%"))
            if user_id_filter:
                stmt = stmt.filter(CVProfile.user_id == user_id_filter)
            profiles = (await db.execute(stmt)).scalars().all()

            total = len(profiles)
            logger.info(f"[CHUNK_REINDEX] {total} profils à traiter")
            success, failed = 0, 0
            _progress_step = max(1, total // 10)

            async def _embed_one_chunk(chunk_text: str) -> list:
                """Embed un chunk avec sémaphore — retourne les valeurs du vecteur."""
                async with sem:
                    res = await embed_content_with_retry(
                        genai_client,
                        model=embedding_model,
                        contents=chunk_text,
                        config={"task_type": "RETRIEVAL_DOCUMENT"},
                    )
                return res.embeddings[0].values

            for idx, profile in enumerate(profiles):
                try:
                    # Reprise après restart : skip si déjà indexé (force=False par défaut)
                    if not force:
                        existing = (await db.execute(
                            select(CVMissionEmbedding.id).where(
                                CVMissionEmbedding.cv_profile_id == profile.id
                            ).limit(1)
                        )).scalar_one_or_none()
                        if existing is not None:
                            success += 1  # compter comme traité pour la progression
                            if total > 0 and (idx + 1) % _progress_step == 0:
                                pct = round((idx + 1) / total * 100)
                                logger.info(
                                    f"[CHUNK_REINDEX] {pct}% — {idx + 1}/{total} "
                                    f"({success} ok, {failed} échecs, skip déjà indexé)"
                                )
                            continue

                    # En mode force=True : supprimer les anciens chunks avant de recréer
                    if force:
                        await db.execute(
                            delete(CVMissionEmbedding).where(
                                CVMissionEmbedding.cv_profile_id == profile.id
                            )
                        )

                    structured_cv = {
                        "current_role": profile.current_role or "Unknown",
                        "years_of_experience": profile.years_of_experience or 0,
                        "summary": profile.summary or "",
                        "competencies": [
                            {"name": k} for k in (profile.competencies_keywords or [])
                        ],
                        "educations": profile.educations or [],
                        "missions": profile.missions or [],
                    }

                    chunks_to_insert: list[CVMissionEmbedding] = []

                    # Chunk 0 : profile_summary (signal identitaire)
                    summary_text = _build_profile_summary_chunk(structured_cv)
                    summary_vector = await _embed_one_chunk(summary_text)
                    chunks_to_insert.append(CVMissionEmbedding(
                        cv_profile_id=profile.id,
                        user_id=profile.user_id,
                        mission_index=0,
                        chunk_type="profile_summary",
                        chunk_text=summary_text,
                        chunk_embedding=summary_vector,
                        embedding_model=embedding_model,
                        source_tag=profile.source_tag,
                    ))

                    # Chunks 1..N : une par mission (toutes, sans limite)
                    missions = structured_cv.get("missions") or []
                    for m_idx, mission in enumerate(missions, start=1):
                        mission_text = _build_mission_chunk_text(mission)
                        if not mission_text.strip():
                            continue
                        m_vector = await _embed_one_chunk(mission_text)
                        chunks_to_insert.append(CVMissionEmbedding(
                            cv_profile_id=profile.id,
                            user_id=profile.user_id,
                            mission_index=m_idx,
                            chunk_type="mission",
                            chunk_text=mission_text,
                            chunk_embedding=m_vector,
                            embedding_model=embedding_model,
                            source_tag=profile.source_tag,
                        ))

                    db.add_all(chunks_to_insert)

                    # FinOps : 1 call par chunk
                    total_tokens = sum(
                        len(c.chunk_text) // 4 for c in chunks_to_insert
                    )
                    await log_finops(
                        "system-chunk-reindex",
                        "reindex_mission_chunks",
                        embedding_model,
                        {"prompt_token_count": total_tokens, "candidates_token_count": 0},
                        auth_token=auth_token,
                    )

                    # Commit immédiat par profil — reprise sans perte si le service redémarre
                    await db.commit()
                    success += 1

                    if total > 0 and (idx + 1) % _progress_step == 0:
                        pct = round((idx + 1) / total * 100)
                        logger.info(
                            f"[CHUNK_REINDEX] {pct}% — {idx + 1}/{total} "
                            f"({success} ok, {failed} échecs, "
                            f"{len(chunks_to_insert)} chunks ce profil)"
                        )

                except Exception as e:
                    await db.rollback()
                    logger.error(
                        f"[CHUNK_REINDEX] Échec user_id={profile.user_id} "
                        f"(role={profile.current_role!r}): {e}"
                    )
                    failed += 1

            logger.info(
                f"[CHUNK_REINDEX] Terminé — {success} succès, {failed} échecs"
            )
            break
    except Exception as e:
        logger.error(f"[CHUNK_REINDEX] Erreur critique: {e}", exc_info=True)
