"""
scheduler_control.py — Active/pause le Cloud Scheduler job du bulk scoring.

Le job `scoring-batch-polling-{workspace}` est démarré au lancement du pipeline
et mis en pause automatiquement à la fin (succès, erreur ou annulation), afin
de ne pas consommer des invocations Cloud Scheduler inutiles entre les runs.

Variables d'environnement :
  GCP_PROJECT_ID      : projet GCP (ex: prod-ia-staffing)
  VERTEX_LOCATION     : région (ex: europe-west1) — utilisée pour le scheduler
  CLOUDRUN_WORKSPACE  : workspace Terraform (ex: prd, dev)
"""

import asyncio
import logging
import os

logger = logging.getLogger(__name__)

GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "")
SCHEDULER_REGION = os.getenv("VERTEX_LOCATION", "europe-west1")
CLOUDRUN_WORKSPACE = os.getenv("CLOUDRUN_WORKSPACE", "prd")
SCHEDULER_JOB_NAME = (
    f"projects/{GCP_PROJECT_ID}/locations/{SCHEDULER_REGION}"
    f"/jobs/scoring-batch-polling-{CLOUDRUN_WORKSPACE}"
)


async def set_scoring_scheduler_enabled(enabled: bool) -> bool:
    """
    Active (resume) ou pause le Cloud Scheduler job de scoring.

    Args:
        enabled: True → resume (active), False → pause

    Returns:
        True si l'opération a réussi, False sinon (erreur loggée, non levée).
    """
    if not GCP_PROJECT_ID:
        logger.warning("[scheduler_control] GCP_PROJECT_ID absent — skip pause/resume scheduler.")
        return False

    action = "resume" if enabled else "pause"
    try:
        from google.cloud import scheduler_v1

        def _call():
            client = scheduler_v1.CloudSchedulerClient()
            if enabled:
                client.resume_job(name=SCHEDULER_JOB_NAME)
            else:
                client.pause_job(name=SCHEDULER_JOB_NAME)

        await asyncio.to_thread(_call)
        logger.info(f"[scheduler_control] Cloud Scheduler job {action}d : {SCHEDULER_JOB_NAME}")
        return True

    except Exception as e:
        # Non bloquant — le pipeline continue même si la pause/resume échoue.
        logger.warning(f"[scheduler_control] Impossible de {action} le scheduler : {e}")
        return False
