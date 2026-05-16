"""
circuit_breaker.py — Circuit-breaker léger pour les appels MCP inter-services.

Implémente le pattern Circuit-Breaker (CLOSED → OPEN → HALF_OPEN) sans
dépendance externe (pas de tenacity, pas de circuitbreaker lib).

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
import logging
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


class CircuitBreaker:
    """
    Circuit-breaker thread-safe et asyncio-compatible.

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

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._lock = threading.Lock()

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

    async def call(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """Exécute *func* en respectant l'état du circuit-breaker."""
        with self._lock:
            current = self._current_state()

        if current == CircuitState.OPEN:
            retry_after = 0.0
            if self._last_failure_time is not None:
                elapsed = time.monotonic() - self._last_failure_time
                retry_after = max(0.0, self.recovery_timeout - elapsed)
            raise CircuitOpenError(self.name, retry_after)

        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            self._on_success()
            return result
        except CircuitOpenError:
            raise  # Ne pas compter les erreurs de circuit comme des pannes
        except Exception as exc:
            self._on_failure(exc)
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
