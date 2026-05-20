"""
redis_state.py — Client Redis dédié aux State Machines (GET → modify → SET atomique).

## Cas d'usage distinct de shared.cache

`shared.cache` (get_cache / set_cache) gère le cache applicatif :
  - Clés simples avec TTL
  - Sérialisation JSON transparente
  - Fail-open : retourne None en cas d'erreur (ne bloque pas l'appelant)

Ce module (`redis_state.py`) gère les state machines persistantes :
  - Pipeline de traitement long (bulk-reanalyse, taxonomy batch, task-tree...)
  - Compteurs atomiques partagés entre plusieurs coroutines / workers
  - Watchdog zombie (détection de tâches bloquées)
  - Pipelines Redis (pipeline.set / pipeline.execute) pour écriture atomique multi-clés

La différence fondamentale : une erreur Redis dans une state machine est BLOQUANTE
(le job ne peut pas continuer sans connaître son état), contrairement au cache
applicatif où le fallback sans cache est acceptable.

## Règle d'usage

Utiliser `get_state_redis_client()` dans les classes *TaskState / *TaskManager :
  - BulkReanalyseTaskManager    (cv_api)
  - ReanalysisTaskState         (cv_api)
  - TreeTaskState               (cv_api)
  - MissionsBulkTaskState       (missions_api)
  - BulkTaskState               (competencies_api)

Ne PAS utiliser `get_state_redis_client()` pour du cache simple → utiliser shared.cache.

## URL Resolution

L'URL Redis est résolue via `_build_redis_url()` de shared.cache pour garantir
l'alignement avec le mapping SERVICE_NAME → DB number (source de vérité unique).
En mode test ou override explicite, REDIS_URL est prioritaire (comme dans shared.cache).
"""

import logging

import redis.asyncio as aioredis

from shared.cache import _build_redis_url

logger = logging.getLogger(__name__)

_state_redis_client: aioredis.Redis | None = None


def get_state_redis_client() -> aioredis.Redis:
    """Retourne le client Redis asyncio partagé pour les state machines.

    Lazy-init : l'URL est résolue au premier appel, garantissant que les
    variables d'environnement (SERVICE_NAME, REDIS_URL) sont lues après
    le démarrage du processus et non au chargement du module.

    Le client est un singleton par processus — partagé entre toutes les
    instances de *TaskState du même service.

    Returns:
        Instance redis.asyncio.Redis configurée avec le bon numéro de DB.
    """
    global _state_redis_client
    if _state_redis_client is None:
        url = _build_redis_url()
        _state_redis_client = aioredis.from_url(url, decode_responses=True)
        logger.debug("[shared.redis_state] Client Redis state machine initialisé → %s", url)
    return _state_redis_client
