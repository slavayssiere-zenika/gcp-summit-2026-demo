"""
semaphores.py — Sémaphores asyncio partagés entre bulk_service et retry_service.

Ce module existe exclusivement pour casser le cycle d'import circulaire :
  bulk_service → retry_service → bulk_service (_items_delete_sem)

POURQUOI ce module utilise `acquire_shielded` (shared.semaphore_utils) :
  Ce sémaphore est GLOBAL (niveau module) et persiste pour toute la durée de vie
  du processus. Si une BackgroundTask FastAPI tenant ce sémaphore est annulée
  (timeout client, exception non gérée), CancelledError peut être levé PENDANT
  sem.acquire() avant que release() soit appelé. Le compteur reste alors
  décrémenté indéfiniment → deadlock jusqu'au redémarrage du container.

  `acquire_shielded` protège l'acquisition : même si la coroutine parente est
  annulée, le acquire() se termine et release() est toujours appelé.
"""

import asyncio

from shared.semaphore_utils import acquire_shielded  # noqa: F401  (ré-exporté pour les consommateurs)
from src.services.config import ITEMS_DELETE_SEMAPHORE

# Sémaphore global de concurrence pour les DELETE /user/{id}/items vers items-api.
# Partagé entre bg_bulk_reanalyse et bg_retry_apply pour éviter la saturation
# du pool AlloyDB de items-api-prd pendant les phases apply en parallèle.
# Valeur : ITEMS_DELETE_SEMAPHORE (défaut 2 — override via env var).
# ⚠️  GLOBAL PERSISTANT : toujours utiliser `acquire_shielded(_items_delete_sem)`
#     et jamais `async with _items_delete_sem:` directement.
_items_delete_sem: asyncio.Semaphore = asyncio.Semaphore(ITEMS_DELETE_SEMAPHORE)
