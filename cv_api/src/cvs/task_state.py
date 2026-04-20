import os
import json
import redis.asyncio as redis
from datetime import datetime, timedelta

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
# Si la tâche n'a pas été mise à jour depuis ce délai, elle est considérée comme morte (crash/timeout)
REANALYSIS_STALE_TIMEOUT_MINUTES = int(os.getenv("REANALYSIS_STALE_TIMEOUT_MINUTES", "30"))
# TTL de sécurité absolu sur la clé Redis (4h) : garantit le nettoyage même sans mise à jour
REANALYSIS_REDIS_TTL_SECONDS = int(os.getenv("REANALYSIS_REDIS_TTL_SECONDS", str(4 * 3600)))

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
        # TTL absolu de sécurité : garantit que la clé sera purgée même si la tâche crashe sans mise à jour finale
        await self._redis.set(self._latest_key, json.dumps(task_data), ex=REANALYSIS_REDIS_TTL_SECONDS)
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
            
        # Remettre le TTL absolu à chaque mise à jour
        await self._redis.set(self._latest_key, json.dumps(data), ex=REANALYSIS_REDIS_TTL_SECONDS)
        return data

    async def mark_failed(self, error_msg: str = "Tâche interrompue de manière inattendue."):
        """Marque la tâche en cours comme échouée (à appeler dans un finally pour garantir le nettoyage)."""
        raw_data = await self._redis.get(self._latest_key)
        if not raw_data:
            return
        data = json.loads(raw_data)
        if data.get("status") == "running":
            data["status"] = "error"
            data["end_time"] = datetime.now().isoformat()
            data["updated_at"] = datetime.now().isoformat()
            data["errors"].append(error_msg)
            data["logs"].append(f"[{datetime.now().isoformat()}] ⚠️ {error_msg}")
            await self._redis.set(self._latest_key, json.dumps(data), ex=REANALYSIS_REDIS_TTL_SECONDS)

    async def force_reset(self):
        """Réinitialise de force l'état de la tâche (déblocage manuel en cas de tâche zombie)."""
        await self._redis.delete(self._latest_key)

    async def get_latest_status(self):
        """Récupère le statut de la dernière tâche."""
        raw_data = await self._redis.get(self._latest_key)
        if not raw_data:
            return None
        return json.loads(raw_data)

    async def is_task_running(self):
        """Vérifie si une tâche est déjà en cours, avec détection de tâche zombie (watchdog)."""
        status = await self.get_latest_status()
        if not status:
            return False
        if status.get("status") != "running":
            return False

        # Watchdog : si la tâche n'a pas été mise à jour depuis REANALYSIS_STALE_TIMEOUT_MINUTES,
        # elle est considérée comme morte (crash, déconnexion, OOM, etc.)
        updated_at_str = status.get("updated_at")
        if updated_at_str:
            try:
                updated_at = datetime.fromisoformat(updated_at_str)
                age = datetime.now() - updated_at
                if age > timedelta(minutes=REANALYSIS_STALE_TIMEOUT_MINUTES):
                    # Marquer comme error et libérer le verrou
                    await self.mark_failed(
                        f"Tâche zombie détectée — aucune activité depuis {int(age.total_seconds() // 60)} min. "
                        f"Verrou libéré automatiquement par le watchdog."
                    )
                    return False
            except (ValueError, TypeError):
                pass

        return True

# Singleton instance
task_state_manager = ReanalysisTaskState()

class TreeTaskState:
    def __init__(self, redis_url: str = REDIS_URL):
        self._redis = redis.from_url(redis_url, decode_responses=True)
        self._key_prefix = "recalc_tree_task"
        self._latest_key = f"{self._key_prefix}:latest"
        self._ttl = 4 * 3600  # TTL absolu 4h

    async def initialize_task(self):
        """Initialise une nouvelle tâche de recalcul de l'arbre."""
        task_data = {
            "status": "running",
            "logs": [f"[{datetime.now().isoformat()}] Démarrage du recalcul de l'arbre."],
            "start_time": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "tree": None,
            "usage": None,
            "error": None
        }
        await self._redis.set(self._latest_key, json.dumps(task_data), ex=self._ttl)
        return task_data

    async def update_progress(self, new_log=None, tree=None, usage=None, error=None, status=None):
        """Met à jour l'état d'avancement du calcul de l'arbre."""
        raw_data = await self._redis.get(self._latest_key)
        if not raw_data:
            return
            
        data = json.loads(raw_data)
        
        if new_log:
            data["logs"].append(f"[{datetime.now().isoformat()}] {new_log}")
            if len(data["logs"]) > 100:
                data["logs"] = data["logs"][-100:]
                
        if tree is not None:
            data["tree"] = tree
            
        if usage is not None:
            data["usage"] = usage
            
        if error:
            data["error"] = error
            
        if status:
            data["status"] = status
            if status in ("completed", "error"):
                data["end_time"] = datetime.now().isoformat()
                
        data["updated_at"] = datetime.now().isoformat()
            
        await self._redis.set(self._latest_key, json.dumps(data), ex=self._ttl)
        return data

    async def get_latest_status(self):
        """Récupère le statut de la dernière tâche."""
        raw_data = await self._redis.get(self._latest_key)
        if not raw_data:
            return None
        return json.loads(raw_data)

    async def is_task_running(self):
        """Vérifie si la tâche est en cours."""
        status = await self.get_latest_status()
        if not status:
            return False
        return status.get("status") == "running"

tree_task_manager = TreeTaskState()

