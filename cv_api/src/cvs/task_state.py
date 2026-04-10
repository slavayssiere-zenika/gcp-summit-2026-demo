import os
import json
import redis.asyncio as redis
from datetime import datetime

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

class ReanalysisTaskState:
    def __init__(self, redis_url: str = REDIS_URL):
        self._redis = redis.from_url(redis_url, decode_responses=True)
        self._key_prefix = "reanalyze_task"
        self._latest_key = f"{self._key_prefix}:latest"

    async def initialize_task(self, total_cv_count: int, filter_type: str, filter_value: str = None):
        """Initialise une nouvelle tâche de réanalyse."""
        task_data = {
            "status": "running",
            "total_cvs": total_cv_count,
            "processed_count": 0,
            "error_count": 0,
            "mismatch_count": 0,
            "errors": [],
            "logs": [f"[{datetime.now().isoformat()}] Démarrage de la réanalyse ({filter_type}: {filter_value or 'Tous'}). Total: {total_cv_count} CVs."],
            "start_time": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        await self._redis.set(self._latest_key, json.dumps(task_data))
        return task_data

    async def update_progress(self, processed_inc=0, error_inc=0, mismatch_inc=0, new_log=None, error_msg=None):
        """Met à jour l'état d'avancement de la tâche en cours."""
        raw_data = await self._redis.get(self._latest_key)
        if not raw_data:
            return
            
        data = json.loads(raw_data)
        data["processed_count"] += processed_inc
        data["error_count"] += error_inc
        data["mismatch_count"] += mismatch_inc
        
        if new_log:
            # On garde les 100 derniers logs pour éviter de saturer Redis
            data["logs"].append(f"[{datetime.now().isoformat()}] {new_log}")
            if len(data["logs"]) > 100:
                data["logs"] = data["logs"][-100:]
                
        if error_msg:
            data["errors"].append(error_msg)
            if len(data["errors"]) > 20:
                data["errors"] = data["errors"][-20:]
                
        data["updated_at"] = datetime.now().isoformat()
        
        # Si tout est fini
        if data["processed_count"] + data["error_count"] >= data["total_cvs"]:
            data["status"] = "completed"
            data["end_time"] = datetime.now().isoformat()
            
        await self._redis.set(self._latest_key, json.dumps(data))
        return data

    async def get_latest_status(self):
        """Récupère le statut de la dernière tâche."""
        raw_data = await self._redis.get(self._latest_key)
        if not raw_data:
            return None
        return json.loads(raw_data)

    async def is_task_running(self):
        """Vérifie si une tâche est déjà en cours."""
        status = await self.get_latest_status()
        if not status:
            return False
        return status.get("status") == "running"

# Singleton instance
task_state_manager = ReanalysisTaskState()
