"""
semaphore_utils.py — Utilitaires asyncio.Semaphore robustes aux cancellations.

## Problème résolu

Un `asyncio.Semaphore` acquis via `async with sem:` est normalement sûr.
MAIS si la coroutine est annulée PENDANT `sem.acquire()` (avant d'avoir obtenu
le slot), `asyncio.CancelledError` est propagé sans que `release()` soit jamais
appelé — le compteur interne reste décrémenté indéfiniment.

Ce bug se manifeste exclusivement sur les sémaphores GLOBAUX (niveau module),
persistants pour toute la durée de vie du processus. Les sémaphores locaux
(créés dans une fonction) sont recréés à chaque appel et ne sont pas impactés.

## Quand utiliser ce module

Sémaphores GLOBAUX persistants à corriger (risque de deadlock production) :
  - `_items_delete_sem`    (cv_api/services/semaphores.py)
  - `_BULK_SEM`            (items_api/items/crud_router.py)
  - `_ASSIGN_BULK_SEM`     (competencies_api/assignments_router.py)
  - `_ENRICH_SEM`          (items_api/items/crud_router.py et search_router.py)

Sémaphores LOCAUX (créés dans une fonction) → PAS besoin de ce module :
  - `sem_embed` dans bulk_service.py, retry_service.py (créés à chaque appel)
  - `sem` dans embedding_service.py, cv_storage_service.py, scoring_pipeline.py

## Solution

`asyncio.shield(sem.acquire())` protège l'acquisition contre l'annulation :
si la coroutine parente est annulée pendant l'attente, l'acquire() se poursuit
en arrière-plan jusqu'à obtenir le slot, puis le libère immédiatement via
le finally. Cela évite le deadlock au prix d'une légère surconsommation
momentanée du sémaphore lors d'annulations massives (acceptable en pratique).
"""

import asyncio
from contextlib import asynccontextmanager


@asynccontextmanager
async def acquire_shielded(sem: asyncio.Semaphore):
    """Context manager qui acquiert un sémaphore de façon immune à CancelledError.

    À utiliser UNIQUEMENT sur les sémaphores globaux persistants (niveau module).
    Pour les sémaphores locaux (créés dans une fonction), `async with sem:` suffit.

    Usage :
        # Avant (dangereux sur sémaphore global)
        async with _GLOBAL_SEM:
            await operation()

        # Après (immune aux cancellations)
        async with acquire_shielded(_GLOBAL_SEM):
            await operation()

    Args:
        sem: Le sémaphore global à acquérir.

    Yields:
        None — le sémaphore est acquis pendant le bloc with.

    Raises:
        asyncio.CancelledError: Re-propagé après release() si la coroutine
                                parente était annulée pendant l'opération.
    """
    await asyncio.shield(sem.acquire())
    try:
        yield
    finally:
        sem.release()
