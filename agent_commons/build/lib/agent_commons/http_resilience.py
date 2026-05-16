"""
http_resilience.py — Utilitaires de résilience HTTP partagés.

Fournit :
  - retry_on_transient()   : décorateur async avec backoff exponentiel + jitter
  - http_call_with_retry() : wrapper httpx avec gestion 4xx/429/5xx
  - RetryAfterError        : exception levée si 429 et Retry-After > seuil
  - is_retryable_status()  : prédicat sur le code HTTP

Politique standardisée de la plateforme Zenika :
  ┌─────────────────────┬─────────────────────────────┐
  │ Code HTTP           │ Comportement                │
  ├─────────────────────┼─────────────────────────────┤
  │ 429                 │ Retry avec Retry-After ou   │
  │                     │ backoff exponentiel (≤ 60s) │
  │ 500, 502, 503, 504  │ Retry avec backoff           │
  │ 401                 │ Fail-fast (token expiré)    │
  │ 403                 │ Fail-fast (droits refusés)  │
  │ 404                 │ Fail-fast (resource absente)│
  │ 400, 409, 422       │ Fail-fast (données invalides│
  └─────────────────────┴─────────────────────────────┘
"""

import asyncio
import logging
import random
import time
from typing import Any, Callable, Optional, Set

import httpx

logger = logging.getLogger(__name__)

# Codes HTTP retryables (transitoires)
RETRYABLE_STATUS_CODES: Set[int] = {429, 500, 502, 503, 504}

# Codes HTTP fail-fast (non retryables — erreur client ou ressource)
NON_RETRYABLE_STATUS_CODES: Set[int] = {400, 401, 403, 404, 409, 410, 422}


def is_retryable_status(status_code: int) -> bool:
    """Retourne True si le code HTTP indique une erreur transitoire (retryable)."""
    return status_code in RETRYABLE_STATUS_CODES


class RetryExhaustedError(Exception):
    """Levée quand toutes les tentatives ont échoué."""

    def __init__(self, method: str, url: str, attempts: int, last_status: Optional[int] = None) -> None:
        self.method = method
        self.url = url
        self.attempts = attempts
        self.last_status = last_status
        msg = f"[retry] {method.upper()} {url} — {attempts} tentatives échouées"
        if last_status:
            msg += f" (dernier HTTP {last_status})"
        super().__init__(msg)


def _parse_retry_after(response: httpx.Response) -> Optional[float]:
    """Extrait le délai en secondes depuis le header Retry-After (si présent).

    Supporte les deux formats RFC 7231 :
      - Retry-After: 30          (secondes)
      - Retry-After: Wed, 21 Oct 2025 07:28:00 GMT  (date HTTP — non supporté ici)
    """
    header = response.headers.get("Retry-After", "").strip()
    if not header:
        return None
    try:
        return float(header)
    except ValueError:
        return None


async def http_call_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    max_attempts: int = 4,
    base_delay_s: float = 1.0,
    max_delay_s: float = 60.0,
    log_prefix: str = "[http_retry]",
    non_retryable: Set[int] = NON_RETRYABLE_STATUS_CODES,
    **kwargs: Any,
) -> httpx.Response:
    """Exécute une requête httpx avec retry exponentiel + jitter.

    Politique :
      - 429 : respect du header Retry-After si présent, sinon backoff exponentiel
      - 5xx : backoff exponentiel avec jitter (thundering-herd prevention)
      - 4xx non-retryable : fail-fast immédiat
      - Timeout / ConnectError : retry avec backoff
      - Toutes les tentatives échouées : lève RetryExhaustedError

    Args:
        client       : AsyncClient httpx (déjà ouvert).
        method       : Méthode HTTP (get/post/put/patch/delete).
        url          : URL complète de la requête.
        max_attempts : Nombre maximum de tentatives (défaut: 4).
        base_delay_s : Délai de base pour le backoff (défaut: 1s).
        max_delay_s  : Délai maximum entre tentatives (défaut: 60s).
        log_prefix   : Préfixe pour les logs.
        non_retryable: Ensemble des codes HTTP fail-fast.
        **kwargs     : Paramètres httpx (json, headers, timeout...).

    Returns:
        La réponse httpx si succès.

    Raises:
        RetryExhaustedError : Si toutes les tentatives échouent sur erreurs retryables.
        httpx.HTTPStatusError : Si une erreur non-retryable est rencontrée (4xx).
    """
    last_status: Optional[int] = None

    for attempt in range(max_attempts):
        try:
            resp = await getattr(client, method)(url, **kwargs)
            last_status = resp.status_code

            # Succès ou erreur non-retryable → retour immédiat
            if resp.status_code not in RETRYABLE_STATUS_CODES:
                if resp.status_code in non_retryable:
                    logger.warning(
                        "%s %s %s → HTTP %d (fail-fast, non-retryable).",
                        log_prefix, method.upper(), url, resp.status_code,
                    )
                    resp.raise_for_status()
                return resp

            # Erreur retryable
            if attempt >= max_attempts - 1:
                break

            # 429 : Retry-After en priorité
            if resp.status_code == 429:
                retry_after = _parse_retry_after(resp)
                if retry_after is not None:
                    wait = min(retry_after, max_delay_s)
                    logger.warning(
                        "%s %s %s → 429 (Retry-After=%.1fs) — retry %d/%d dans %.1fs.",
                        log_prefix, method.upper(), url, retry_after,
                        attempt + 1, max_attempts, wait,
                    )
                    await asyncio.sleep(wait)
                    continue

            # Backoff exponentiel + jitter
            wait = min(base_delay_s * (2 ** attempt) + random.uniform(0, 1), max_delay_s)
            logger.warning(
                "%s %s %s → HTTP %d — retry %d/%d dans %.1fs.",
                log_prefix, method.upper(), url, resp.status_code,
                attempt + 1, max_attempts, wait,
            )
            await asyncio.sleep(wait)

        except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as exc:
            if attempt >= max_attempts - 1:
                raise RetryExhaustedError(method, url, max_attempts, last_status) from exc
            wait = min(base_delay_s * (2 ** attempt) + random.uniform(0, 1), max_delay_s)
            logger.warning(
                "%s %s %s → %s — retry %d/%d dans %.1fs.",
                log_prefix, method.upper(), url, type(exc).__name__,
                attempt + 1, max_attempts, wait,
            )
            await asyncio.sleep(wait)

    raise RetryExhaustedError(method, url, max_attempts, last_status)


def build_retry_after_headers(retry_after_s: int = 5) -> dict:
    """Génère les headers de rate-limit standard pour les réponses 429.

    Usage côté serveur (APIs data) :
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit"},
            headers=build_retry_after_headers(30),
        )
    """
    return {
        "Retry-After": str(retry_after_s),
        "X-RateLimit-Reset": str(int(time.time()) + retry_after_s),
    }


async def retry_on_transient(
    func: Callable,
    *args: Any,
    max_attempts: int = 3,
    base_delay_s: float = 1.0,
    max_delay_s: float = 30.0,
    log_prefix: str = "[retry]",
    **kwargs: Any,
) -> Any:
    """Exécute une coroutine async avec retry sur les exceptions transitoires.

    Utile pour les appels qui ne passent pas par httpx directement
    (ex: google-cloud SDK, BigQuery client, etc.).

    Les exceptions retryées : httpx.TimeoutException, httpx.ConnectError,
    ConnectionError, asyncio.TimeoutError.
    Toutes les autres exceptions sont propagées immédiatement.
    """
    retryable_exc = (
        httpx.TimeoutException,
        httpx.ConnectError,
        httpx.RemoteProtocolError,
        ConnectionError,
        asyncio.TimeoutError,
    )

    for attempt in range(max_attempts):
        try:
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            return func(*args, **kwargs)
        except retryable_exc as exc:
            if attempt >= max_attempts - 1:
                raise
            wait = min(base_delay_s * (2 ** attempt) + random.uniform(0, 1), max_delay_s)
            logger.warning(
                "%s %s — retry %d/%d dans %.1fs.",
                log_prefix, type(exc).__name__, attempt + 1, max_attempts, wait,
            )
            await asyncio.sleep(wait)
