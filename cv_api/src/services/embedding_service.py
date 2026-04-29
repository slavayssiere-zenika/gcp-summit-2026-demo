"""
embedding_service.py — Re-indexation des embeddings vectoriels.

Ce module contient :
- reindex_embeddings_bg()  — Background task : recalcule tous les embeddings
                             sans relancer l'extraction LLM

Consommé par router.py pour l'endpoint :
    POST /reindex-embeddings
"""

import logging
import os
from typing import Optional

from opentelemetry.propagate import inject
from sqlalchemy.future import select

import database
from src.cvs.models import CVProfile
from src.services.finops import log_finops
from src.gemini_retry import embed_content_with_retry
from src.services.utils import _build_distilled_content

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

            logger.info(f"[REINDEX] {len(profiles)} profils à re-indexer")
            success, failed = 0, 0

            for profile in profiles:
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
                    )
                    profile.semantic_embedding = emb_res.embeddings[0].values

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
                except Exception as e:
                    logger.error(
                        f"[REINDEX] Embedding échoué pour user_id={profile.user_id}: {e}"
                    )
                    failed += 1

            await db.commit()
            logger.info(f"[REINDEX] Terminé — {success} succès, {failed} échecs")
            break
    except Exception as e:
        logger.error(f"[REINDEX] Erreur critique: {e}", exc_info=True)
