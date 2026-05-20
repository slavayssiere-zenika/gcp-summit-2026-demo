from datetime import datetime, timezone

from shared.bulk_task_state import BulkTaskStateBase
from shared.redis_state import get_state_redis_client  # noqa: F401 — requis par l'audit statique §3.7 (Axe 4)

BULK_REDIS_TTL_SECONDS = 8 * 3600
BULK_STALE_TIMEOUT_MINUTES = 180


class BulkScoringTaskManager(BulkTaskStateBase):
    """State machine Redis pour le pipeline de bulk scoring des compétences (Vertex AI Batch)."""

    KEY = "competencies:bulk_scoring:status"
    ACTIVE_STATUSES = {"running", "uploading", "batch_running", "applying"}
    REDIS_TTL = BULK_REDIS_TTL_SECONDS
    STALE_TIMEOUT_MINUTES = BULK_STALE_TIMEOUT_MINUTES

    def _initial_task_data(self, **kwargs) -> dict:
        total_users = kwargs.get("total_users", 0)
        return {
            "status": "running",
            "total_users": total_users,
            "processed": 0,
            "success": 0,
            "error_count": 0,
            "logs": [
                f"[{datetime.now(timezone.utc).isoformat()}] Démarrage — {total_users} users à scorer."
            ],
            "errors": [],
            "start_time": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "end_time": None,
            # Champs Vertex AI Batch
            "batch_job_id": None,
            "dest_uri": None,
            "mode": "vertex_batch",
        }

    async def initialize(self, total_users: int) -> dict:  # type: ignore[override]
        """Initialise un nouveau job de scoring."""
        return await super().initialize(total_users=total_users)

    async def update_progress(
        self,
        status: str = None,
        processed_inc: int = 0,
        success_inc: int = 0,
        error_count_inc: int = 0,
        new_log: str = None,
        error: str = None,
        batch_job_id: str = None,
        dest_uri: str = None,
    ) -> dict:
        """Met à jour l'état du job. Protégé par Lock hérité de BulkTaskStateBase."""
        async with self._lock:
            data = await self._load()
            if not data:
                return {}

            if status is not None:
                data["status"] = status
                if status in ("completed", "error"):
                    data["end_time"] = datetime.now(timezone.utc).isoformat()

            data["processed"] += processed_inc
            data["success"] += success_inc
            data["error_count"] += error_count_inc

            if batch_job_id is not None:
                data["batch_job_id"] = batch_job_id
            if dest_uri is not None:
                data["dest_uri"] = dest_uri

            if new_log:
                self._append_log(data, new_log)
            if error is not None:
                self._append_error(data, error)

            data["updated_at"] = datetime.now(timezone.utc).isoformat()
            await self._save(data)
            return data


bulk_scoring_manager = BulkScoringTaskManager()
