import json
import logging
import os
import re

import httpx
from opentelemetry.propagate import inject
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_db
from src.auth import verify_admin

logger = logging.getLogger(__name__)

# Protégé par verify_admin (seuls les rôles 'admin' peuvent y accéder)
router = APIRouter(prefix="/admin", tags=["Admin"], dependencies=[Depends(verify_admin)])


@router.post("/remediate-legacy")
async def remediate_legacy_errors(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Endpoint d'administration pour réconcilier les CVs historiques avec des erreurs silencieuses.
    Équivalent à scripts/mark_legacy_errors.py mais exécutable sur le cluster.
    """
    logger.info("🚀 Démarrage de la remédiation des erreurs silencieuses de taxonomie.")

    # Récupérer les URLs configurées
    COMPETENCIES_API = os.getenv("COMPETENCIES_API_URL", "http://api.internal.zenika/api/competencies/")
    DRIVE_API = os.getenv("DRIVE_API_URL", "http://api.internal.zenika/api/drive/")

    COMPETENCIES_API = COMPETENCIES_API.rstrip('/')
    DRIVE_API = DRIVE_API.rstrip('/')

    # Utiliser le token de l'appelant (qui est admin) pour les appels inter-services
    auth_header = request.headers.get("Authorization")
    headers = {"Authorization": auth_header} if auth_header else {}

    try:
        result = await db.execute(
            text(
                "SELECT id, user_id, source_url, extracted_competencies "
                "FROM cv_profiles WHERE source_url IS NOT NULL"
            )
        )
        profiles = result.fetchall()
        logger.info("🔍 %d profils trouvés à vérifier.", len(profiles))

        fixed_count = 0

        inject(headers)  # propagation traces OTel vers competencies_api et drive_api
        async with httpx.AsyncClient(timeout=10.0) as client:
            for p_id, user_id, source_url, extracted_competencies in profiles:
                llm_comps = extracted_competencies if extracted_competencies else []
                nb_extracted = len([c for c in llm_comps if c.get("name")])

                if nb_extracted == 0:
                    continue

                # 1. Vérifier les compétences assignées
                nb_assigned = 0
                try:
                    res = await client.get(f"{COMPETENCIES_API}/user/{user_id}", headers=headers, timeout=10.0)
                    if res.status_code == 200:
                        data = res.json()
                        # /user/{id} retourne PaginationResponse : {items: [...], total: N}
                        # On utilise total pour avoir le vrai count (sans limite de pagination)
                        if isinstance(data, dict):
                            nb_assigned = data.get("total", len(data.get("items", [])))
                        else:
                            nb_assigned = len(data)
                        if nb_assigned >= nb_extracted:
                            continue
                except Exception as e:
                    logger.error(
                        "❌ Erreur réseau compétences user_id=%s: %s", user_id, e
                    )
                    continue

                # 2. Arrivé ici = échec partiel ou total
                logger.warning(
                    "⚠️ user_id=%s : %d/%d compétences assignées. Remédiation en cours...",
                    user_id, nb_assigned, nb_extracted
                )
                error_msg = (
                    f"Legacy: Échec partiel ou total d'assignation "
                    f"({nb_assigned}/{nb_extracted} compétences assignées)."
                )

                # 3. Patch Drive API
                google_file_id = None
                doc_id_match = re.search(r"/d/([a-zA-Z0-9_-]+)", source_url)
                if doc_id_match:
                    google_file_id = doc_id_match.group(1)
                else:
                    id_param_match = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", source_url)
                    if id_param_match:
                        google_file_id = id_param_match.group(1)

                if google_file_id:
                    try:
                        patch_res = await client.patch(
                            f"{DRIVE_API}/files/{google_file_id}",
                            json={"status": "ERROR", "error_message": error_msg},
                            headers=headers
                        )
                        if patch_res.status_code >= 400:
                            logger.error(
                                "  ❌ PATCH Drive échoué file_id=%s: HTTP %s",
                                google_file_id, patch_res.status_code
                            )
                        else:
                            logger.info("  ✅ Drive %s marqué ERROR.", google_file_id)
                    except Exception as e:
                        logger.error("  ❌ Erreur réseau PATCH Drive: %s", e)
                else:
                    logger.warning("  ⚠️ Impossible d'extraire un ID Drive de l'URL: %s", source_url)

                # 4. Mettre à jour en base
                try:
                    json_err = json.dumps([error_msg])
                    await db.execute(
                        text("UPDATE cv_profiles SET processing_errors = :err WHERE id = :p_id"),
                        {"err": json_err, "p_id": p_id}
                    )
                    await db.commit()
                    logger.info("  ✅ Profil BDD mis à jour (processing_errors).")
                    fixed_count += 1
                except Exception as e:
                    logger.error("  ❌ Échec mise à jour BDD: %s", e)
                    await db.rollback()

        return {"status": "success", "fixed_count": fixed_count}
    except Exception as exc:
        logger.error("Erreur globale dans remediate_legacy_errors: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/clear-processing-errors")
async def clear_processing_errors(
    db: AsyncSession = Depends(get_db),
):
    """Vide les erreurs de traitement historiques (processing_errors) en base.

    Cible uniquement les CVs dont le statut Drive est IMPORTED_CV (import réussi)
    ou qui ont un user_id (profil lié à un consultant).
    Opération idempotente et non-destructive : ne supprime que l'historique
    d'erreurs passées, pas les données métier.

    Retourne le nombre de profils nettoyés.
    """
    try:
        # google_drive_files est dans la DB de drive_api (schéma séparé — cross-DB impossible).
        # Critère de succès : user_id IS NOT NULL = CV lié à un consultant = import réussi.
        # Les CVs sans user_id (import échoué avant liaison) conservent leurs erreurs.
        result = await db.execute(
            text("""
                UPDATE cv_profiles
                SET processing_errors = '[]'::jsonb
                WHERE processing_errors IS NOT NULL
                  AND jsonb_array_length(processing_errors) > 0
                  AND user_id IS NOT NULL
            """)
        )
        await db.commit()
        cleared = result.rowcount or 0
        logger.info("[clear-processing-errors] %d profils nettoyés.", cleared)
        return {"status": "success", "cleared_count": cleared}
    except Exception as exc:
        await db.rollback()
        logger.error("[clear-processing-errors] Erreur: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
