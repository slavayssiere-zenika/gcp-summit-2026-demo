import json
from datetime import datetime

from shared.redis_state import get_state_redis_client


class MissionTaskState:
    def __init__(self):
        # Client Redis partagé via shared.redis_state (URL résolue via SERVICE_NAME → DB mapping).
        self._redis = get_state_redis_client()
        self._key_prefix = "mission_job"

    async def initialize_task(self, task_id: str, title: str):
        """Initialise une nouvelle tâche de staffing."""
        task_data = {
            "task_id": task_id,
            "status": "processing",
            "title": title,
            "error": None,
            "mission_id": None,
            "start_time": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        await self._redis.setex(f"{self._key_prefix}:{task_id}", 3600 * 24, json.dumps(task_data))  # Retenu 24h max
        return task_data

    async def get_task(self, task_id: str):
        raw_data = await self._redis.get(f"{self._key_prefix}:{task_id}")
        if not raw_data:
            return None
        return json.loads(raw_data)

    async def update_status_success(self, task_id: str, mission_id: int):
        data = await self.get_task(task_id)
        if data:
            data["status"] = "completed"
            data["mission_id"] = mission_id
            data["updated_at"] = datetime.now().isoformat()
            await self._redis.setex(f"{self._key_prefix}:{task_id}", 3600 * 24, json.dumps(data))

    async def update_status_failed(self, task_id: str, error_msg: str):
        data = await self.get_task(task_id)
        if data:
            data["status"] = "failed"
            data["error"] = error_msg
            data["updated_at"] = datetime.now().isoformat()
            await self._redis.setex(f"{self._key_prefix}:{task_id}", 3600 * 24, json.dumps(data))


task_manager = MissionTaskState()
