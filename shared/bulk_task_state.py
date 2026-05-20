"""bulk_task_state.py — Classe abstraite pour les state machines Redis de tâches bulk.

Factorise la plomberie commune entre competencies_api.BulkScoringTaskManager
et cv_api.BulkReanalyseTaskManager :
  - Initialisation du client Redis via shared.redis_state
  - Méthodes CRUD Redis (get/set/delete avec TTL)
  - Watchdog zombie (is_running avec détection de stale)
  - Gestion des logs rotatifs (cap à MAX_LOG_ENTRIES)
  - asyncio.Lock pour la protection des mises à jour concurrentes

Usage (dans chaque service) :
    from shared.bulk_task_state import BulkTaskStateBase

    class MyTaskManager(BulkTaskStateBase):
        KEY = "myservice:bulk:status"
        ACTIVE_STATUSES = {"running", "processing"}

        def _initial_task_data(self, **kwargs) -> dict:
            return {
                "status": "running",
                "total": kwargs.get("total", 0),
                ...
            }
"""
import asyncio
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone

from shared.redis_state import get_state_redis_client

logger = logging.getLogger(__name__)

BULK_REDIS_TTL_SECONDS = 8 * 3600   # 8 heures (défaut)
BULK_STALE_TIMEOUT_MINUTES = 180    # 3 heures sans mise à jour → zombie
MAX_LOG_ENTRIES = 150               # Rotation des logs Redis
MAX_ERROR_ENTRIES = 50              # Rotation des erreurs Redis


class BulkTaskStateBase(ABC):
    """Classe abstraite pour les state machines Redis des pipelines bulk.

    Sous-classes requises :
        KEY (str): Clé Redis unique pour ce manager (ex: "cv:bulk:status")
        ACTIVE_STATUSES (set[str]): Statuts considérés comme "en cours"

    Méthodes abstraites :
        _initial_task_data(**kwargs) -> dict : Données initiales du job.
    """

    KEY: str = ""
    ACTIVE_STATUSES: set = {"running", "processing"}
    REDIS_TTL: int = BULK_REDIS_TTL_SECONDS
    STALE_TIMEOUT_MINUTES: int = BULK_STALE_TIMEOUT_MINUTES

    def __init__(self) -> None:
        self._redis = get_state_redis_client()
        self._lock = asyncio.Lock()

    @abstractmethod
    def _initial_task_data(self, **kwargs) -> dict:
        """Retourne le dictionnaire initial de données du job.

        Doit inclure au minimum : 'status', 'logs', 'errors', 'start_time', 'updated_at'.
        """
        raise NotImplementedError

    # ─── Primitives Redis ────────────────────────────────────────────────────

    async def _load(self) -> dict | None:
        """Charge et désérialise l'état courant depuis Redis. None si absent."""
        raw = await self._redis.get(self.KEY)
        if not raw:
            return None
        return json.loads(raw)

    async def _save(self, data: dict) -> None:
        """Sérialise et persiste l'état dans Redis avec le TTL configuré."""
        await self._redis.set(self.KEY, json.dumps(data), ex=self.REDIS_TTL)

    # ─── API publique ────────────────────────────────────────────────────────

    async def initialize(self, **kwargs) -> dict:
        """Initialise un nouveau job de traitement.

        Raises:
            ValueError: Si un job est déjà actif (is_running() retourne True).
        """
        task_data = self._initial_task_data(**kwargs)
        await self._save(task_data)
        return task_data

    async def get_status(self) -> dict | None:
        """Récupère le statut courant. Retourne None si aucun job n'existe."""
        return await self._load()

    async def is_running(self) -> bool:
        """Vérifie si un job est actif — avec watchdog zombie intégré.

        Si aucune mise à jour depuis STALE_TIMEOUT_MINUTES, le job est
        déclaré zombie et le verrou est libéré automatiquement.
        """
        status = await self.get_status()
        if not status:
            return False

        if status.get("status") not in self.ACTIVE_STATUSES:
            return False

        updated_at_str = status.get("updated_at")
        if updated_at_str:
            try:
                updated_at = datetime.fromisoformat(updated_at_str)
                # Normalise en naive UTC pour la comparaison
                if updated_at.tzinfo is not None:
                    updated_at = updated_at.replace(tzinfo=None)
                age = datetime.now(timezone.utc).replace(tzinfo=None) - updated_at
                if age > timedelta(minutes=self.STALE_TIMEOUT_MINUTES):
                    age_min = int(age.total_seconds() // 60)
                    await self._set_error_locked(
                        error=(
                            f"Tâche zombie détectée — aucune activité depuis "
                            f"{age_min} min. Verrou libéré automatiquement par le watchdog."
                        )
                    )
                    return False
            except (ValueError, TypeError):
                pass

        return True

    async def reset(self) -> None:
        """Réinitialise de force le statut (déblocage manuel ou annulation complète)."""
        await self._redis.delete(self.KEY)

    # ─── Helpers protégés ────────────────────────────────────────────────────

    def _append_log(self, data: dict, message: str) -> None:
        """Ajoute un log horodaté avec rotation (cap MAX_LOG_ENTRIES)."""
        ts = datetime.now(timezone.utc).isoformat()
        data.setdefault("logs", []).append(f"[{ts}] {message}")
        if len(data["logs"]) > MAX_LOG_ENTRIES:
            data["logs"] = data["logs"][-MAX_LOG_ENTRIES:]

    def _append_error(self, data: dict, error: str) -> None:
        """Ajoute une erreur avec rotation (cap MAX_ERROR_ENTRIES)."""
        data.setdefault("errors", []).append(error)
        if len(data["errors"]) > MAX_ERROR_ENTRIES:
            data["errors"] = data["errors"][-MAX_ERROR_ENTRIES:]

    async def _set_error_locked(self, error: str) -> None:
        """Passe le job en statut 'error' — utilisé uniquement par le watchdog."""
        data = await self._load()
        if not data:
            return
        data["status"] = "error"
        data["error"] = error
        data["end_time"] = datetime.now(timezone.utc).isoformat()
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._append_error(data, error)
        await self._save(data)
