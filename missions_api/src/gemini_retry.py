"""
gemini_retry.py — Wrappers async avec retry exponentiel pour les appels Gemini.

Gère les erreurs transitoires :
  - 429 ResourceExhausted ("Our servers experienced high traffic...")
  - 503 ServiceUnavailable (surcharge serveur)
"""
import logging
from tenacity import AsyncRetrying, wait_exponential, stop_after_attempt, retry_if_exception, before_sleep_log

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 6
_MIN_WAIT_SEC = 5
_MAX_WAIT_SEC = 60


def _is_retryable(exc: BaseException) -> bool:
    """Retourne True pour les erreurs Gemini transitoires (429, 503, surcharge)."""
    exc_str = str(exc).lower()
    # Détection textuelle (portable entre versions du SDK)
    if any(k in exc_str for k in ("429", "resource exhausted", "high traffic", "503", "service unavailable", "overloaded")):
        return True
    # google.api_core (présent via google-genai)
    try:
        from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable
        if isinstance(exc, (ResourceExhausted, ServiceUnavailable)):
            return True
    except ImportError:
        pass
    # google.genai.errors (SDK >=1.x)
    try:
        from google.genai import errors as genai_errors
        if hasattr(genai_errors, "ServerError") and isinstance(exc, genai_errors.ServerError):
            return True
        if hasattr(genai_errors, "ClientError") and isinstance(exc, genai_errors.ClientError):
            return "429" in str(exc)
    except ImportError:
        pass
    return False


async def generate_content_with_retry(client, **kwargs):
    """
    Appelle client.aio.models.generate_content(**kwargs) avec retry exponentiel.

    En cas de 429 / 503 / surcharge Gemini, attend entre {MIN}s et {MAX}s avant
    chaque nouvel essai (jusqu'à {MAX_ATTEMPTS} tentatives).
    """.format(MIN=_MIN_WAIT_SEC, MAX=_MAX_WAIT_SEC, MAX_ATTEMPTS=_MAX_ATTEMPTS)
    async for attempt in AsyncRetrying(
        wait=wait_exponential(multiplier=2, min=_MIN_WAIT_SEC, max=_MAX_WAIT_SEC),
        stop=stop_after_attempt(_MAX_ATTEMPTS),
        retry=retry_if_exception(_is_retryable),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    ):
        with attempt:
            return await client.aio.models.generate_content(**kwargs)


async def embed_content_with_retry(client, **kwargs):
    """
    Appelle client.aio.models.embed_content(**kwargs) avec retry exponentiel.

    Même politique de retry que generate_content_with_retry.
    """
    async for attempt in AsyncRetrying(
        wait=wait_exponential(multiplier=2, min=_MIN_WAIT_SEC, max=_MAX_WAIT_SEC),
        stop=stop_after_attempt(_MAX_ATTEMPTS),
        retry=retry_if_exception(_is_retryable),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    ):
        with attempt:
            return await client.aio.models.embed_content(**kwargs)
