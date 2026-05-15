"""
semaphores.py — Sémaphores asyncio partagés entre bulk_service et retry_service.

Ce module existe exclusivement pour casser le cycle d'import circulaire :
  bulk_service → retry_service → bulk_service (_items_delete_sem)

En déplaçant _items_delete_sem ici, les deux services peuvent l'importer
depuis un module neutre sans dépendance croisée.
"""

import asyncio

from src.services.config import ITEMS_DELETE_SEMAPHORE

# Sémaphore global de concurrence pour les DELETE /user/{id}/items vers items-api.
# Partagé entre bg_bulk_reanalyse et bg_retry_apply pour éviter la saturation
# du pool AlloyDB de items-api-prd pendant les phases apply en parallèle.
# Valeur : ITEMS_DELETE_SEMAPHORE (défaut 2 — override via env var).
_items_delete_sem: asyncio.Semaphore = asyncio.Semaphore(ITEMS_DELETE_SEMAPHORE)
