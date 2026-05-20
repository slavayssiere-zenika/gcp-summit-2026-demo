"""taxonomy_router.py — Recalcul interactif et batch de l'arbre taxonomique."""
import asyncio
import logging

import src.services.config as _svc_config  # _svc_config.client/_svc_config.vertex_batch_client via attribute access
from fastapi import (APIRouter, BackgroundTasks, Depends, HTTPException, Request)
from src.cvs.routers._shared import (GCP_PROJECT_ID, VERTEX_LOCATION,
                                     RecalculateStepRequest)
from src.cvs.task_state import tree_task_manager
from src.services.bulk_service import bg_retry_apply
from src.services.taxonomy_service import (fetch_prompt,
                                           get_existing_competencies,
                                           run_taxonomy_step)

from shared.auth.jwt import verify_jwt, VerifyJwtOrOidc
from src.services.taxonomy_batch_service import TaxonomyBatchService

_fetch_prompt = fetch_prompt
_get_existing_competencies = get_existing_competencies
_bg_retry_apply = bg_retry_apply

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["CV Taxonomy"], dependencies=[Depends(verify_jwt)])
public_router = APIRouter(prefix="", tags=["CV Taxonomy Public"])

verify_jwt_or_oidc = VerifyJwtOrOidc()


@router.post("/recalculate_tree/step")
async def recalculate_competencies_tree_step(
    request: Request,
    req_body: RecalculateStepRequest,
    background_tasks: BackgroundTasks,
    token_payload: dict = Depends(verify_jwt)
):
    if token_payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Privilèges administrateur requis.")

    auth_header = request.headers.get("Authorization")
    user_caller = token_payload.get("sub", "unknown")

    if req_body.step == "map":
        await tree_task_manager.initialize_task()
    else:
        await tree_task_manager.update_progress(status="running", new_log=f"Lancement de l'étape: {req_body.step}")

    background_tasks.add_task(run_taxonomy_step, auth_header, user_caller,
                              req_body.step, _svc_config.client, req_body.target_pillar)
    return {"message": f"Étape {req_body.step} lancée", "status": "running"}


@router.post("/recalculate_tree")
async def recalculate_competencies_tree(
    request: Request,
    background_tasks: BackgroundTasks,
    resume: bool = False,
    token_payload: dict = Depends(verify_jwt)
):
    if token_payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Opération refusée: privilèges administrateur requis.")

    if await tree_task_manager.is_task_running():
        return {"message": "Un calcul de l'arbre est déjà en cours", "status": "running"}

    auth_header = request.headers.get("Authorization")
    user_caller = token_payload.get("sub", "unknown")

    if not resume:
        await tree_task_manager.initialize_task()
        background_tasks.add_task(run_taxonomy_step, auth_header, user_caller, "map", _svc_config.client)
    else:
        background_tasks.add_task(run_taxonomy_step, auth_header, user_caller, "reduce", _svc_config.client)

    return {"message": "Calcul interactif de l'arbre lancé", "status": "running"}


@router.get("/recalculate_tree/status")
async def get_recalculate_tree_status():
    """Récupère le statut du recalcul de l'arbre.

    Synthètise 'batch_running' quand mode=batch && status=running pour que
    le frontend déclenche checkBatchProgress() et fasse avancer le pipeline.
    """
    status = await tree_task_manager.get_latest_status()
    if not status:
        return {"status": "idle", "message": "Aucune tâche lancée récemment."}
    # Synthèse du status composé pour le frontend
    if status.get("mode") == "batch" and status.get("status") == "running":
        status = dict(status)
        status["status"] = "batch_running"
    return status

# ─────────────────────────────────────────────────────────────────────────────
# Sprint 0 — Re-indexation des embeddings (embeddings-only, sans re-extraction LLM)
# ─────────────────────────────────────────────────────────────────────────────


@public_router.post("/recalculate_tree/batch/start", summary="Lance le processus batch asynchrone (Map)")
async def recalculate_tree_batch_start(request: Request, user: dict = Depends(verify_jwt_or_oidc)):
    auth_header = request.headers.get("Authorization")
    return await TaxonomyBatchService.start_batch(auth_header)


async def _generate_autonomous_service_token() -> str:
    return await TaxonomyBatchService.generate_autonomous_service_token()


@public_router.post("/recalculate_tree/batch/check", summary="Vérifie l'état du batch et avance la machine à états")
async def recalculate_tree_batch_check(request: Request, user: dict = Depends(verify_jwt_or_oidc)):
    auth_header = request.headers.get("Authorization")
    user_caller = user.get("sub", "scheduler")
    return await TaxonomyBatchService.check_batch(auth_header, user_caller)


@router.get("/recalculate_tree/batch/list", summary="Liste l'historique des jobs batch de taxonomie")
async def recalculate_tree_batch_list(request: Request, user: dict = Depends(verify_jwt)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Privilèges administrateur requis.")
    try:
        batches = []
        all_batches = await asyncio.to_thread(lambda: list(_svc_config.vertex_batch_client.batches.list()))
        for b in all_batches:
            display_name = "batch_job"
            if hasattr(b, "display_name") and b.display_name:
                display_name = b.display_name
            elif hasattr(b, "config") and hasattr(b.config, "display_name") and b.config.display_name:
                display_name = b.config.display_name

            if hasattr(b, "name") and hasattr(b, "state"):
                # Vertex AI expose completion_stats (pas request_counts)
                cs = getattr(b, "completion_stats", None)
                completion_stats = None
                if cs:
                    successful = int(getattr(cs, "success_count", None) or getattr(cs, "successful_count", 0) or 0)
                    failed = int(getattr(cs, "failed_count", None) or getattr(cs, "error_count", 0) or 0)
                    incomplete = int(getattr(cs, "incomplete_count", 0) or 0)
                    total = int(getattr(cs, "total_count", None) or 0) or (successful + failed + incomplete)
                    if total > 0:
                        completion_stats = {
                            "successful": successful,
                            "failed": failed,
                            "incomplete": incomplete,
                            "total": total,
                            "percent": int((successful / total) * 100)
                        }

                batches.append({
                    "name": b.name,
                    "display_name": display_name,
                    "state": b.state.name if hasattr(b.state, "name") else str(b.state),
                    "create_time": str(b.create_time) if hasattr(b, "create_time") else None,
                    "start_time": str(b.start_time) if getattr(b, "start_time", None) else None,
                    "end_time": str(b.end_time) if getattr(b, "end_time", None) else None,
                    "update_time": str(b.update_time) if hasattr(b, "update_time") else None,
                    "model": getattr(b, "model", None),
                    "completion_stats": completion_stats
                })
        batches.sort(key=lambda x: x["create_time"] or "", reverse=True)
        return {"success": True, "batches": batches}
    except Exception as e:
        logger.error(f"Erreur listage batch GCP: {e}")
        return {"success": False, "error": str(e)}


@router.delete("/recalculate_tree/batch/{job_id}", summary="Supprime un job batch GCP de l'historique")
async def recalculate_tree_batch_delete(job_id: str, request: Request, user: dict = Depends(verify_jwt)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Privilèges administrateur requis.")
    try:
        # Vertex AI utilise un chemin complet : projects/.../batchPredictionJobs/ID
        # Si le frontend envoie juste l'ID numérique, on reconstruit le chemin complet.
        if "/" in job_id:
            full_job_id = job_id  # déjà un chemin complet
        else:
            full_job_id = f"projects/{GCP_PROJECT_ID}/locations/{VERTEX_LOCATION}/batchPredictionJobs/{job_id}"
        await asyncio.to_thread(_svc_config.vertex_batch_client.batches.delete, name=full_job_id)
        return {"success": True, "message": f"Job {job_id} supprimé avec succès."}
    except Exception as e:
        logger.error(f"Erreur suppression batch GCP: {e}")
        return {"success": False, "error": str(e)}


@router.post("/recalculate_tree/cancel", summary="Annule le traitement interactif en cours")
async def recalculate_tree_cancel(request: Request, user: dict = Depends(verify_jwt)):
    await tree_task_manager.update_progress(status="cancelled", error="Traitement interactif annulé par l'utilisateur.")
    return {"success": True, "message": "Traitement annulé"}


@router.post("/recalculate_tree/batch/cancel", summary="Annule le batch en cours")
async def recalculate_tree_batch_cancel(request: Request, user: dict = Depends(verify_jwt)):
    latest_status = await tree_task_manager.get_latest_status()
    if latest_status and latest_status.get("batch_job_id"):
        try:
            await asyncio.to_thread(
                _svc_config.vertex_batch_client.batches.cancel,
                name=latest_status.get("batch_job_id")
            )
        except Exception as e:
            logger.warning(f"Impossible d'annuler le batch Vertex AI (déjà terminé ou inexistant) : {e}")

    await tree_task_manager.update_progress(status="error", error="Annulé par l'utilisateur")
    return {"success": True, "message": "Batch annulé"}


@router.post("/recalculate_tree/batch/recover", summary="Tente de récupérer un batch bloqué en erreur")
async def recalculate_tree_batch_recover(request: Request, user: dict = Depends(verify_jwt)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Privilèges administrateur requis.")
    latest_status = await tree_task_manager.get_latest_status()
    if latest_status and latest_status.get("batch_job_id"):
        # On le remet en running pour que le frontend reprenne le polling
        # On efface l'erreur et on repart sur l'étape map si c'était planté au parsing
        # ou deduplicating si on a perdu l'étape. Pour être safe, on remet "map"
        # car deduplicate est idempotent.
        step = latest_status.get("batch_step")
        if step == "deduplicating":
            step = "map"
        elif step == "sweeping":
            step = "reduce"

        await tree_task_manager.update_progress(status="batch_running", batch_step=step, error="")
        return {
            "success": True,
            "message": "État du batch forcé à 'batch_running'. L'interface va reprendre le relais."
        }
    return {"success": False, "error": "Aucun job batch récent en mémoire."}


@router.post("/recalculate_tree/batch/reset", summary="Réinitialise forcé l'état Redis du batch (déblocage d'urgence)")
async def recalculate_tree_batch_reset(request: Request, user: dict = Depends(verify_jwt)):
    """Efface l'état Redis du pipeline Batch pour permettre un nouveau démarrage.
    A utiliser quand l'interface est bloquée et que Cancel/Recover ne suffisent pas.
    Le job GCP en cours n'est PAS annulé — utilisez Cancel d'abord si nécessaire.
    """
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Privileges administrateur requis.")
    await tree_task_manager.initialize_task()
    await tree_task_manager.update_progress(status="idle", error="Reinitialise manuellement par l'admin.")
    return {"success": True, "message": "Etat du pipeline reinitialise. Vous pouvez lancer un nouveau batch."}


# ─────────────────────────────────────────────────────────────────────────────
# BULK RE-ANALYSE — Vertex AI Batch (Option B — Full Quality)
# Pipeline : Build JSONL → GCS Upload → Vertex Batch → Auto-Apply complet
# Chaque CV : UPDATE cv_profiles + purge évals + purge comps + bulk assign
#             + purge missions + ré-indexation + scoring IA + FinOps
# ─────────────────────────────────────────────────────────────────────────────
