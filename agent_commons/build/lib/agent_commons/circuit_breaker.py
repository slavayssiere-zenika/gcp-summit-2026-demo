"""
circuit_breaker.py — Circuit-breaker léger pour les appels MCP inter-services.

Implémente le pattern Circuit-Breaker (CLOSED → OPEN → HALF_OPEN) sans
dépendance externe (pas de tenacity, pas de circuitbreaker lib).

Si la variable d'environnement REDIS_URL est définie, l'état du circuit est
persisté dans Redis (clés avec TTL 5 min), permettant à toutes les instances
Cloud Run de partager un état de panne commun (circuit breaker distribué).
En l'absence de REDIS_URL, ou en cas d'erreur Redis, le comportement est
identique au mode purement in-memory (fail-open sur Redis).

Utilisation :
    from circuit_breaker import CircuitBreaker, CircuitOpenError

    cb = CircuitBreaker(name="cv_mcp", failure_threshold=5, recovery_timeout=30.0)

    try:
        result = await cb.call(my_async_func, *args, **kwargs)
    except CircuitOpenError:
        # Circuit ouvert — le service est considéré down
        ...
    except Exception:
        # Erreur normale propagée depuis my_async_func
        ...
"""

import asyncio
import json
import logging
import os
import time
import threading
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "CLOSED"        # Fonctionnement normal
    OPEN = "OPEN"            # Service down — requêtes bloquées
    HALF_OPEN = "HALF_OPEN"  # Sonde — une requête de test autorisée


class CircuitOpenError(Exception):
    """Levée quand le circuit est OPEN et la requête est bloquée."""

    def __init__(self, name: str, retry_after: float) -> None:
        self.name = name
        self.retry_after = retry_after
        super().__init__(
            f"Circuit '{name}' OPEN — service considéré DOWN. "
            f"Réessai possible dans {retry_after:.1f}s."
        )


# ---------------------------------------------------------------------------
# Redis storage backend (optionnel — activé si REDIS_URL est défini)
# ---------------------------------------------------------------------------

# Clé Redis par circuit : "cb:{name}"
_CB_REDIS_TTL_S = 300  # 5 minutes — au-delà, l'état expire et retombe CLOSED


def _get_redis_client():
    """Retourne un client Redis asyncio (aioredis) si REDIS_URL est disponible.

    Import lazy pour que l'import du module ne force pas redis à être installé.
    Retourne None si REDIS_URL est absent ou si redis n'est pas disponible.
    """
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return None
    try:
        import redis.asyncio as aioredis
        return aioredis.from_url(redis_url, decode_responses=True, socket_timeout=1.0)
    except ImportError:
        logger.warning("[CircuitBreaker] redis non disponible — mode in-memory uniquement.")
        return None
    except Exception as exc:
        logger.warning("[CircuitBreaker] Impossible d'initialiser Redis (%s) — mode in-memory.", exc)
        return None


class _RedisStateBackend:
    """Backend Redis pour la persistence de l'état d'un circuit breaker.

    Chaque opération est best-effort : toute exception Redis est loggée
    et ignorée pour ne pas bloquer le circuit breaker lui-même.
    """

    def __init__(self, name: str) -> None:
        self._key = f"cb:{name}"
        self._client = None
        self._initialized = False

    def _ensure_client(self):
        if not self._initialized:
            self._client = _get_redis_client()
            self._initialized = True
        return self._client

    async def load(self) -> Optional[dict]:
        """Charge l'état depuis Redis. Retourne None en cas d'erreur ou de clé absente."""
        client = self._ensure_client()
        if client is None:
            return None
        try:
            raw = await client.get(self._key)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as exc:
            logger.debug("[CircuitBreaker] Redis load error (%s) — fallback in-memory.", exc)
            return None

    async def save(self, state: dict) -> None:
        """Persiste l'état dans Redis avec un TTL. Best-effort."""
        client = self._ensure_client()
        if client is None:
            return
        try:
            await client.set(self._key, json.dumps(state), ex=_CB_REDIS_TTL_S)
        except Exception as exc:
            logger.debug("[CircuitBreaker] Redis save error (%s) — état non persisté.", exc)

    async def delete(self) -> None:
        """Supprime la clé Redis (ex: réinitialisation du circuit)."""
        client = self._ensure_client()
        if client is None:
            return
        try:
            await client.delete(self._key)
        except Exception as exc:
            logger.debug("[CircuitBreaker] Redis delete error (%s).", exc)


class CircuitBreaker:
    """
    Circuit-breaker thread-safe, asyncio-compatible, avec backend Redis optionnel.

    En mode Redis (REDIS_URL défini) :
      - L'état est chargé depuis Redis à chaque appel à call()
      - L'état est persisté dans Redis après chaque transition
      - Permet la coordination entre plusieurs instances Cloud Run
      - Si Redis est indisponible → fallback transparent sur l'état in-memory

    Paramètres :
        name              : Identifiant (ex: "cv_mcp", "competencies_api").
        failure_threshold : Nombre d'échecs consécutifs avant ouverture (défaut: 5).
        recovery_timeout  : Secondes avant tentative HALF_OPEN (défaut: 30).
        success_threshold : Succès consécutifs en HALF_OPEN pour revenir CLOSED (défaut: 2).
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        success_threshold: int = 2,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold

        # État in-memory (source de vérité quand Redis est absent)
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._lock = threading.Lock()

        # Backend Redis (lazy-init dans call())
        self._redis = _RedisStateBackend(name)

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _to_dict(self) -> dict:
        return {
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "last_failure_time": self._last_failure_time,
        }

    def _from_dict(self, data: dict) -> None:
        """Applique l'état Redis sur l'état in-memory (avec merge optimiste)."""
        try:
            remote_state = CircuitState(data.get("state", "CLOSED"))
            remote_failures = int(data.get("failure_count", 0))
            remote_successes = int(data.get("success_count", 0))
            remote_last = data.get("last_failure_time")
            # On prend le pire cas : l'état le plus dégradé gagne
            state_priority = {
                CircuitState.OPEN: 2,
                CircuitState.HALF_OPEN: 1,
                CircuitState.CLOSED: 0,
            }
            if state_priority[remote_state] >= state_priority[self._state]:
                self._state = remote_state
                self._failure_count = max(self._failure_count, remote_failures)
                self._success_count = remote_successes
                if remote_last is not None:
                    if self._last_failure_time is None or remote_last > self._last_failure_time:
                        self._last_failure_time = float(remote_last)
        except Exception as exc:
            logger.debug("[CircuitBreaker] _from_dict parse error (%s) — ignoré.", exc)

    # ------------------------------------------------------------------
    # State transitions (in-memory, protégées par _lock)
    # ------------------------------------------------------------------

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._current_state()

    def _current_state(self) -> CircuitState:
        """Calcule l'état courant (avec transition OPEN → HALF_OPEN si timeout écoulé)."""
        if self._state == CircuitState.OPEN:
            if (
                self._last_failure_time is not None
                and time.monotonic() - self._last_failure_time >= self.recovery_timeout
            ):
                # Transition automatique OPEN → HALF_OPEN
                self._state = CircuitState.HALF_OPEN
                self._success_count = 0
                logger.info(
                    "[CircuitBreaker] '%s' OPEN → HALF_OPEN (%.1fs écoulées)",
                    self.name, self.recovery_timeout,
                )
        return self._state

    def _on_success(self) -> None:
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
                    logger.info(
                        "[CircuitBreaker] '%s' HALF_OPEN → CLOSED (%d succès consécutifs).",
                        self.name, self.success_threshold,
                    )
            elif self._state == CircuitState.CLOSED:
                # Réinitialise le compteur d'échecs sur succès
                self._failure_count = 0

    def _on_failure(self, exc: Exception) -> None:
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._state == CircuitState.HALF_OPEN:
                # Échec en sonde → retour OPEN immédiat
                self._state = CircuitState.OPEN
                self._success_count = 0
                logger.warning(
                    "[CircuitBreaker] '%s' HALF_OPEN → OPEN (échec sonde: %s).",
                    self.name, exc,
                )
            elif (
                self._state == CircuitState.CLOSED
                and self._failure_count >= self.failure_threshold
            ):
                self._state = CircuitState.OPEN
                logger.error(
                    "[CircuitBreaker] '%s' CLOSED → OPEN après %d échecs consécutifs. "
                    "Dernier: %s. Réessai dans %.0fs.",
                    self.name, self._failure_count, exc, self.recovery_timeout,
                )

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def call(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """Exécute *func* en respectant l'état du circuit-breaker.

        1. Charge l'état Redis (si disponible) pour synchroniser l'état distribué.
        2. Bloque si OPEN (lève CircuitOpenError).
        3. Exécute func, met à jour l'état en cas de succès ou d'échec.
        4. Persiste l'état dans Redis si une transition a eu lieu.
        """
        # Synchronisation Redis (best-effort)
        remote = await self._redis.load()
        if remote is not None:
            with self._lock:
                self._from_dict(remote)

        with self._lock:
            current = self._current_state()

        if current == CircuitState.OPEN:
            retry_after = 0.0
            if self._last_failure_time is not None:
                elapsed = time.monotonic() - self._last_failure_time
                retry_after = max(0.0, self.recovery_timeout - elapsed)
            raise CircuitOpenError(self.name, retry_after)

        state_before = self._state
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            self._on_success()
            # Persiste si l'état a changé
            if self._state != state_before:
                await self._redis.save(self._to_dict())
            return result
        except CircuitOpenError:
            raise  # Ne pas compter les erreurs de circuit comme des pannes
        except Exception as exc:
            self._on_failure(exc)
            # Persiste toujours sur échec (compteur mis à jour)
            await self._redis.save(self._to_dict())
            raise


# ---------------------------------------------------------------------------
# Registre global — un circuit-breaker par URL MCP (partagé entre instances)
# ---------------------------------------------------------------------------
_registry: dict[str, CircuitBreaker] = {}
_registry_lock = threading.Lock()


def get_circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 30.0,
) -> CircuitBreaker:
    """Retourne (ou crée) le circuit-breaker pour un service donné."""
    with _registry_lock:
        if name not in _registry:
            _registry[name] = CircuitBreaker(
                name=name,
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
            )
        return _registry[name]
