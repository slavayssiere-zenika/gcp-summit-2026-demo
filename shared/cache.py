"""
cache.py — Utilitaire centralisé de cache Redis asynchrone pour les conteneurs.

Gère la connexion à Redis, la sérialisation JSON, et assure un fallback
gracieux (retourne None sans crasher) en cas de défaillance du serveur Redis.

Usage recommandé :
    # Chaque service passe son nom pour obtenir automatiquement la bonne DB Redis.
    # La variable d'environnement REDIS_URL est prioritaire si définie.
    from shared.cache import get_cache, set_cache, RedisServiceDB

    # Connexion via SERVICE_NAME (recommandé) :
    #   SERVICE_NAME=cv_api → DB 4 → redis://redis:6379/4
    # Connexion via REDIS_URL explicite (override complet) :
    #   REDIS_URL=redis://custom-host:6379/0
"""

import enum
import json
import logging
import os
from typing import Any, Optional

import redis.asyncio as redis
from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

# ── Mapping canonique Service → DB Redis ─────────────────────────────────────
# Correspond exactement à la configuration docker-compose.yml et Cloud Run.
# Modifier UNIQUEMENT ici — la source de vérité unique pour les numéros de DB.


class RedisServiceDB(enum.IntEnum):
    """Enum de mapping Service → numéro de base de données Redis.

    Chaque service de la plateforme Zenika dispose d'une DB Redis dédiée,
    garantissant l'isolation des namespaces et la sécurité opérationnelle.

    Usage :
        db_number = RedisServiceDB.cv_api           # → 4
        url = f"redis://redis:6379/{db_number}"     # → "redis://redis:6379/4"
    """
    users_api = 0
    items_api = 1
    agent_router_api = 2
    competencies_api = 3
    cv_api = 4
    prompts_api = 5
    drive_api = 6
    analytics_mcp = 7
    missions_api = 8
    monitoring_mcp = 9
    agent_hr_api = 10
    agent_ops_api = 11
    agent_missions_api = 12


def _build_redis_url() -> str:
    """Construit l'URL Redis à utiliser pour ce service.

    Priorité :
    1. Variable d'environnement REDIS_URL (override explicite — tests, Cloud Run custom)
    2. Variable SERVICE_NAME → lookup dans RedisServiceDB → URL avec DB correcte
    3. Fallback sur redis://redis:6379/0 (fail-safe développement)

    Returns:
        URL Redis complète avec le numéro de DB correct.

    Raises:
        ValueError: si SERVICE_NAME est défini mais absent de RedisServiceDB.
    """
    explicit_url = os.getenv("REDIS_URL")
    if explicit_url:
        return explicit_url

    service_name = os.getenv("SERVICE_NAME")
    if service_name:
        try:
            db_number = RedisServiceDB[service_name].value
        except KeyError:
            raise ValueError(
                f"[shared.cache] SERVICE_NAME='{service_name}' inconnu. "
                f"Valeurs autorisées : {[m.name for m in RedisServiceDB]}"
            )
        redis_host = os.getenv("REDIS_HOST", "redis")
        redis_port = os.getenv("REDIS_PORT", "6379")
        return f"redis://{redis_host}:{redis_port}/{db_number}"

    logger.warning(
        "[shared.cache] Ni REDIS_URL ni SERVICE_NAME définis — fallback redis://redis:6379/0. "
        "Définissez SERVICE_NAME=<nom_service> dans les variables d'environnement."
    )
    return "redis://redis:6379/0"


# Pool de connexion global — initialisé lazily pour respecter REDIS_URL au runtime
_redis_pool: Optional[redis.Redis] = None


def _get_redis() -> redis.Redis:
    """Récupère ou initialise le client Redis (lazy init thread-safe).

    L'URL est résolue au premier appel via _build_redis_url() pour garantir
    que les variables d'environnement sont lues APRÈS le démarrage du service
    (et non capturées au chargement du module).
    """
    global _redis_pool
    if _redis_pool is None:
        url = _build_redis_url()
        _redis_pool = redis.from_url(url, decode_responses=True)
        logger.debug("[shared.cache] Pool Redis initialisé → %s", url)
    return _redis_pool


async def get_cache(key: str) -> Optional[Any]:
    """Récupère et désérialise une valeur du cache Redis.

    En cas d'erreur de connexion ou de valeur non-JSON, log un avertissement
    et retourne None (fail-open — ne jamais crasher le service appelant).

    Args:
        key: Clé Redis (ex: "cv_api:profile:42")

    Returns:
        Valeur Python désérialisée, ou None si absente/erreur.
    """
    client = _get_redis()
    with tracer.start_as_current_span("cache.get", attributes={"cache.key": key}) as span:
        try:
            raw = await client.get(key)
            if raw is None:
                span.set_attribute("cache.hit", False)
                return None
            span.set_attribute("cache.hit", True)
            return json.loads(raw)
        except json.JSONDecodeError as e:
            span.record_exception(e)
            logger.warning(
                "[shared.cache] Valeur non-JSON pour '%s' (source externe ?) : %s", key, e
            )
            return None
        except Exception as e:
            span.record_exception(e)
            logger.warning("[shared.cache] Erreur de lecture pour '%s': %s", key, e)
            return None


async def set_cache(key: str, value: Any, ttl_seconds: int = 60) -> bool:
    """Sérialise et stocke une valeur dans le cache Redis avec un TTL.

    En cas d'erreur de connexion, log un avertissement et retourne False.

    Args:
        key:         Clé Redis.
        value:       Valeur Python sérialisable en JSON.
        ttl_seconds: Durée de vie en secondes. Doit être >= 1.

    Returns:
        True si stocké avec succès, False sinon.

    Raises:
        ValueError: Si ttl_seconds < 1 (Redis n'accepte pas ex=0).
    """
    if ttl_seconds < 1:
        raise ValueError(
            f"[shared.cache] ttl_seconds doit être >= 1 (reçu: {ttl_seconds}). "
            "Redis rejette ex=0 avec ResponseError."
        )
    client = _get_redis()
    with tracer.start_as_current_span(
        "cache.set", attributes={"cache.key": key, "cache.ttl": ttl_seconds}
    ) as span:
        try:
            raw = json.dumps(value, default=str)
            await client.set(key, raw, ex=ttl_seconds)
            span.set_attribute("cache.operation", "setex")
            return True
        except Exception as e:
            span.record_exception(e)
            logger.warning("[shared.cache] Erreur d'écriture pour '%s': %s", key, e)
            return False


async def delete_cache(key: str) -> bool:
    """Supprime une clé du cache Redis.

    En cas d'erreur de connexion, log un avertissement et retourne False.

    Args:
        key: Clé Redis à supprimer.

    Returns:
        True si supprimé (ou clé absente), False en cas d'erreur.
    """
    client = _get_redis()
    with tracer.start_as_current_span("cache.delete", attributes={"cache.key": key}) as span:
        try:
            await client.delete(key)
            return True
        except Exception as e:
            span.record_exception(e)
            logger.warning("[shared.cache] Erreur de suppression pour '%s': %s", key, e)
            return False


async def clear_namespace(prefix: str) -> int:
    """Supprime toutes les clés commençant par un certain préfixe (ex: 'cv_api:').

    Utilise SCAN pour itérer sans bloquer le serveur Redis (O(N) non-bloquant).
    Retourne le nombre de clés supprimées.

    Args:
        prefix: Préfixe des clés à supprimer (ex: 'competencies:'). NE PEUT PAS
                être vide — un préfixe vide efface TOUTE la base de données.

    Returns:
        Nombre de clés supprimées (0 si aucune ou erreur).

    Raises:
        ValueError: Si prefix est vide ou None.
    """
    if not prefix or not prefix.strip():
        raise ValueError(
            "[shared.cache] clear_namespace() requiert un préfixe non-vide. "
            "Un préfixe vide supprimerait TOUTE la base de données Redis."
        )
    client = _get_redis()
    with tracer.start_as_current_span(
        "cache.delete_pattern", attributes={"cache.pattern": f"{prefix}*"}
    ) as span:
        try:
            cursor = 0
            deleted_count = 0
            while True:
                cursor, keys = await client.scan(cursor=cursor, match=f"{prefix}*")
                if keys:
                    await client.delete(*keys)
                    deleted_count += len(keys)
                if cursor == 0:
                    break
            span.set_attribute("cache.deleted_count", deleted_count)
            return deleted_count
        except Exception as e:
            span.record_exception(e)
            logger.warning("[shared.cache] Erreur clear_namespace pour '%s': %s", prefix, e)
            return 0


async def key_exists(key: str) -> bool:
    """Vérifie si une clé existe dans Redis sans en lire la valeur.

    Utilisation typique : vérification de blacklist JWT
    (ex: `jwt:blacklist:user:{username}` → compte suspendu).

    En cas d'erreur de connexion, log un avertissement et retourne False
    (fail-open — ne jamais bloquer l'accès si Redis est indisponible).

    Args:
        key: Clé Redis à vérifier.

    Returns:
        True si la clé existe, False sinon ou en cas d'erreur.
    """
    client = _get_redis()
    with tracer.start_as_current_span("cache.exists", attributes={"cache.key": key}) as span:
        try:
            result = await client.exists(key)
            span.set_attribute("cache.hit", bool(result))
            return bool(result)
        except Exception as e:
            span.record_exception(e)
            logger.warning("[shared.cache] Erreur exists pour '%s': %s", key, e)
            return False  # Fail-open
