import os
import json
import redis.asyncio as redis
from datetime import datetime, timedelta, timezone


REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/3") # Note: using the competencies_api redis db

BULK_REDIS_TTL_SECONDS = 8 * 3600
BULK_STALE_TIMEOUT_MINUTES = 180

class BulkScoringTaskManager:
    """State machine Redis pour le pipeline de bulk scoring des compétences."""
    KEY = "competencies:bulk_scoring:status"

    def __init__(self, redis_url: str = REDIS_URL):
        self._redis = redis.from_url(redis_url, decode_responses=True)

    async def initialize(self, total_users: int) -> dict:
        task_data = {
            "status": "running",
            "total_users": total_users,
            "processed": 0,
            "success": 0,
            "error_count": 0,
            "logs": [f"[{datetime.now(timezone.utc).isoformat()}] Démarrage — {total_users} users à scorer."],
            "errors": [],
            "start_time": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "end_time": None,
            # Champs Vertex AI Batch
            "batch_job_id": None,
            "dest_uri": None,
            "mode": "vertex_batch",
        }
        await self._redis.set(self.KEY, json.dumps(task_data), ex=BULK_REDIS_TTL_SECONDS)
        return task_data

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
        raw = await self._redis.get(self.KEY)
        if not raw:
            return {}

        data = json.loads(raw)

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
            data["logs"].append(f"[{datetime.now(timezone.utc).isoformat()}] {new_log}")
            if len(data["logs"]) > 150:
                data["logs"] = data["logs"][-150:]

        if error is not None:
            data["errors"].append(error)
            if len(data["errors"]) > 50:
                data["errors"] = data["errors"][-50:]

        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        await self._redis.set(self.KEY, json.dumps(data), ex=BULK_REDIS_TTL_SECONDS)
        return data

    async def get_status(self) -> dict | None:
        raw = await self._redis.get(self.KEY)
        if not raw:
            return None
        return json.loads(raw)

    async def is_running(self) -> bool:
        status = await self.get_status()
        if not status:
            return False

        if status.get("status") not in ("running", "uploading", "batch_running", "applying"):
            return False

        # Watchdog
        updated_at_str = status.get("updated_at")
        if updated_at_str:
            try:
                updated_at = datetime.fromisoformat(updated_at_str)
                # Normalise en naive UTC pour la comparaison
                if updated_at.tzinfo is not None:
                    updated_at = updated_at.replace(tzinfo=None)
                age = datetime.utcnow() - updated_at
                if age > timedelta(minutes=BULK_STALE_TIMEOUT_MINUTES):
                    await self.update_progress(
                        status="error",
                        error=f"Tâche zombie détectée — aucune activité depuis {int(age.total_seconds() // 60)} min.",
                    )
                    return False
            except (ValueError, TypeError):
                pass
        return True

    async def reset(self):
        await self._redis.delete(self.KEY)

bulk_scoring_manager = BulkScoringTaskManager()
