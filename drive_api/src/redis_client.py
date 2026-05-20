"""
redis_client.py — SUPPRIMÉ — Remplacé par shared.cache et shared.semaphore_utils.

Ce fichier est conservé uniquement pour éviter les imports cassés pendant la transition.
Il redirige get_redis() vers shared.cache.

MIGRATION RÉALISÉE (2026-05-19) :
  - drive_api utilisait redis.Redis (synchrone, blocking) dans l'event loop asyncio.
  - Chaque appel Redis bloquait le thread de l'event loop pendant l'I/O réseau.
  - Remplacé par les fonctions async de shared.cache (get_cache, set_cache, delete_cache).
  - Les appels .pipeline() ont été remplacés par gather() d'appels set_cache individuels.
  - Ce module est désormais une coquille vide : ne PAS le réintroduire.
"""

# Fichier volontairement vide — tous les imports vers get_redis() ont été supprimés.
# Conserver uniquement pour prévenir les ImportError résiduels lors d'un déploiement partiel.
