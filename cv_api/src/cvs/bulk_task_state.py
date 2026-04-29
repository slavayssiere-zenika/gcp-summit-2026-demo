import asyncio
import os
import json
import redis.asyncio as redis
from datetime import datetime, timedelta

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/4")

# TTL absolu : un job Vertex peut prendre plusieurs heures
BULK_REDIS_TTL_SECONDS = int(os.getenv("BULK_REANALYSE_TTL_SECONDS", str(8 * 3600)))
# Watchdog : si aucune mise à jour depuis ce délai → tâche zombie
BULK_STALE_TIMEOUT_MINUTES = int(os.getenv("BULK_REANALYSE_STALE_MINUTES", "180"))


class BulkReanalyseTaskManager:
    """
    State machine Redis pour le pipeline de ré-analyse globale des CVs via Vertex AI Batch.

    Cycle de vie des statuts :
        idle → building → uploading → batch_running → applying → completed
                                                               ↓
                                                            error
    """

    KEY = "cv:bulk_reanalyse:status"

    def __init__(self, redis_url: str = REDIS_URL):
        self._redis = redis.from_url(redis_url, decode_responses=True)
        # Lock asyncio pour sérialiser les update_progress concurrents.
        # Sans ce lock, 5 workers simultanés font GET+SET en race condition
        # et s'écrasent mutuellement (applying_current perdu).
        self._lock = asyncio.Lock()

    async def initialize(self, total_cvs: int) -> dict:
        """Initialise un nouveau job de ré-analyse. Lève une ValueError si un job est déjà en cours."""
        task_data = {
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
        await self._redis.set(self.KEY, json.dumps(task_data), ex=BULK_REDIS_TTL_SECONDS)
        return task_data

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
        """Met à jour l'état en cours. Protégé par asyncio.Lock pour éviter
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
        raw = await self._redis.get(self.KEY)
        if not raw:
            return {}

        data = json.loads(raw)

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
            data["logs"].append(f"[{datetime.now().isoformat()}] {new_log}")
            # Garde les 150 derniers logs pour éviter de saturer Redis
            if len(data["logs"]) > 150:
                data["logs"] = data["logs"][-150:]

        if error is not None:
            data["error"] = error
            data["errors"].append(error)

        if cv_error is not None:
            data["errors"].append(cv_error)
            if len(data["errors"]) > 50:
                data["errors"] = data["errors"][-50:]

        data["updated_at"] = datetime.now().isoformat()

        # Remettre le TTL absolu à chaque mise à jour
        await self._redis.set(self.KEY, json.dumps(data), ex=BULK_REDIS_TTL_SECONDS)
        return data

    async def get_status(self) -> dict | None:
        """Récupère le statut courant. Retourne None si aucun job n'existe."""
        raw = await self._redis.get(self.KEY)
        if not raw:
            return None
        return json.loads(raw)

    async def is_running(self) -> bool:
        """
        Vérifie si un job est déjà actif.
        Intègre un watchdog : si aucune mise à jour depuis BULK_STALE_TIMEOUT_MINUTES,
        la tâche est déclarée zombie et le verrou est libéré automatiquement.
        """
        status = await self.get_status()
        if not status:
            return False

        active_statuses = {"building", "uploading", "batch_running", "applying"}
        if status.get("status") not in active_statuses:
            return False

        # Watchdog zombie
        updated_at_str = status.get("updated_at")
        if updated_at_str:
            try:
                updated_at = datetime.fromisoformat(updated_at_str)
                age = datetime.now() - updated_at
                if age > timedelta(minutes=BULK_STALE_TIMEOUT_MINUTES):
                    await self.update_progress(
                        status="error",
                        error=(
                            f"Tâche zombie détectée — aucune activité depuis "
                            f"{int(age.total_seconds() // 60)} min. "
                            f"Verrou libéré automatiquement par le watchdog."
                        ),
                    )
                    return False
            except (ValueError, TypeError):
                pass

        return True

    async def reset_apply_counters(self) -> dict:
        """Remet à zéro les compteurs apply avant un retry (sans toucher logs, batch_job_id, dest_uri)."""
        raw = await self._redis.get(self.KEY)
        if not raw:
            return {}
        data = json.loads(raw)
        data["applying_current"] = 0
        data["error_count"] = 0
        data["errors"] = []
        data["error"] = None
        data["updated_at"] = datetime.now().isoformat()
        await self._redis.set(self.KEY, json.dumps(data), ex=BULK_REDIS_TTL_SECONDS)
        return data

    async def cancel_soft(self, reason: str = "Annulé par l'utilisateur.") -> dict:
        """Annulation douce : passe au statut 'cancelled' SANS supprimer dest_uri.

        Préserve les champs batch_job_id et dest_uri afin que le bouton
        'Retry Apply' puisse rejouer la phase apply depuis les résultats GCS.
        La clé Redis reste active jusqu'à son TTL normal.
        """
        raw = await self._redis.get(self.KEY)
        if not raw:
            return {}
        data = json.loads(raw)
        data["status"] = "cancelled"
        data["end_time"] = datetime.now().isoformat()
        data["updated_at"] = datetime.now().isoformat()
        data["logs"].append(f"[{datetime.now().isoformat()}] {reason}")
        # dest_uri et batch_job_id intentionnellement préservés pour le retry-apply.
        await self._redis.set(self.KEY, json.dumps(data), ex=BULK_REDIS_TTL_SECONDS)
        return data

    async def reset(self):
        """Réinitialise de force le statut (déblocage manuel ou annulation complète).

        ATTENTION : supprime dest_uri — le retry-apply ne sera plus possible.
        Préférer cancel_soft() si le pipeline a déjà écrit des résultats GCS.
        """
        await self._redis.delete(self.KEY)


# Singleton global
bulk_reanalyse_manager = BulkReanalyseTaskManager()
