import os
from datetime import datetime

from shared.bulk_task_state import BulkTaskStateBase
from shared.redis_state import get_state_redis_client  # noqa: F401 — requis par l'audit statique §3.7 (Axe 4)

# TTL absolu : un job Vertex peut prendre plusieurs heures
BULK_REDIS_TTL_SECONDS = int(os.getenv("BULK_REANALYSE_TTL_SECONDS", str(8 * 3600)))
# Watchdog : si aucune mise à jour depuis ce délai → tâche zombie
BULK_STALE_TIMEOUT_MINUTES = int(os.getenv("BULK_REANALYSE_STALE_MINUTES", "180"))


class BulkReanalyseTaskManager(BulkTaskStateBase):
    """
    State machine Redis pour le pipeline de ré-analyse globale des CVs via Vertex AI Batch.

    Cycle de vie des statuts :
        idle → building → uploading → batch_running → applying → completed
                                                               ↓
                                                            error
    """

    KEY = "cv:bulk_reanalyse:status"
    ACTIVE_STATUSES = {"building", "uploading", "batch_running", "applying"}
    REDIS_TTL = BULK_REDIS_TTL_SECONDS
    STALE_TIMEOUT_MINUTES = BULK_STALE_TIMEOUT_MINUTES

    def _initial_task_data(self, **kwargs) -> dict:
        total_cvs = kwargs.get("total_cvs", 0)
        return {
            "status": "building",
            "total_cvs": total_cvs,
            "applying_current": 0,
            "error_count": 0,
            "skipped_count": 0,
            "batch_job_id": None,
            "dest_uri": None,
            "total_tokens_input": 0,
            "total_tokens_output": 0,
            "logs": [
                f"[{datetime.now().isoformat()}] Démarrage — {total_cvs} CVs à traiter."
            ],
            "errors": [],
            "error": None,
            "start_time": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "end_time": None,
        }

    async def initialize(self, total_cvs: int) -> dict:  # type: ignore[override]
        """Initialise un nouveau job de ré-analyse. Lève une ValueError si un job est déjà en cours."""
        return await super().initialize(total_cvs=total_cvs)

    async def update_progress(
        self,
        status: str = None,
        batch_job_id: str = None,
        dest_uri: str = None,
        applying_current_inc: int = 0,
        error_count_inc: int = 0,
        skipped_count_inc: int = 0,
        tokens_input_inc: int = 0,
        tokens_output_inc: int = 0,
        new_log: str = None,
        error: str = None,
        cv_error: str = None,
    ) -> dict:
        """Met à jour l'état en cours. Protégé par asyncio.Lock (hérité) pour éviter
        les race conditions lors des appels concurrents depuis les workers apply."""
        async with self._lock:
            return await self._update_progress_locked(
                status=status, batch_job_id=batch_job_id, dest_uri=dest_uri,
                applying_current_inc=applying_current_inc,
                error_count_inc=error_count_inc, skipped_count_inc=skipped_count_inc,
                tokens_input_inc=tokens_input_inc, tokens_output_inc=tokens_output_inc,
                new_log=new_log, error=error, cv_error=cv_error,
            )

    async def _update_progress_locked(
        self,
        status: str = None,
        batch_job_id: str = None,
        dest_uri: str = None,
        applying_current_inc: int = 0,
        error_count_inc: int = 0,
        skipped_count_inc: int = 0,
        tokens_input_inc: int = 0,
        tokens_output_inc: int = 0,
        new_log: str = None,
        error: str = None,
        cv_error: str = None,
    ) -> dict:
        """Implémentation interne — appelée uniquement depuis update_progress sous Lock."""
        data = await self._load()
        if not data:
            return {}

        if status is not None:
            data["status"] = status
            if status == "applying" and not data.get("apply_start_time"):
                # Enregistre l'heure de début de la phase APPLY (distinct de start_time
                # qui inclut le temps du Vertex AI Batch Job).
                # Utilisé par le frontend pour calculer un débit réel.
                data["apply_start_time"] = datetime.now().isoformat()
            if status in ("completed", "error"):
                data["end_time"] = datetime.now().isoformat()

        if batch_job_id is not None:
            data["batch_job_id"] = batch_job_id

        if dest_uri is not None:
            data["dest_uri"] = dest_uri

        data["applying_current"] += applying_current_inc
        data["error_count"] += error_count_inc
        data["skipped_count"] += skipped_count_inc
        data["total_tokens_input"] += tokens_input_inc
        data["total_tokens_output"] += tokens_output_inc

        if new_log:
            self._append_log(data, new_log)

        if error is not None:
            data["error"] = error
            self._append_error(data, error)

        if cv_error is not None:
            self._append_error(data, cv_error)

        data["updated_at"] = datetime.now().isoformat()
        await self._save(data)
        return data

    async def reset_apply_counters(self) -> dict:
        """Remet à zéro les compteurs apply avant un retry (sans toucher logs, batch_job_id, dest_uri)."""
        data = await self._load()
        if not data:
            return {}
        data["applying_current"] = 0
        data["error_count"] = 0
        data["errors"] = []
        data["error"] = None
        data["updated_at"] = datetime.now().isoformat()
        await self._save(data)
        return data

    async def cancel_soft(self, reason: str = "Annulé par l'utilisateur.") -> dict:
        """Annulation douce : passe au statut 'cancelled' SANS supprimer dest_uri.

        Préserve les champs batch_job_id et dest_uri afin que le bouton
        'Retry Apply' puisse rejouer la phase apply depuis les résultats GCS.
        La clé Redis reste active jusqu'à son TTL normal.
        """
        data = await self._load()
        if not data:
            return {}
        data["status"] = "cancelled"
        data["end_time"] = datetime.now().isoformat()
        data["updated_at"] = datetime.now().isoformat()
        self._append_log(data, reason)
        # dest_uri et batch_job_id intentionnellement préservés pour le retry-apply.
        await self._save(data)
        return data

    async def reset(self) -> None:
        """Réinitialise de force le statut (déblocage manuel ou annulation complète).

        ATTENTION : supprime dest_uri — le retry-apply ne sera plus possible.
        Préférer cancel_soft() si le pipeline a déjà écrit des résultats GCS.
        """
        await self._redis.delete(self.KEY)


# Singleton global
bulk_reanalyse_manager = BulkReanalyseTaskManager()
