"""Observabilité partagée — logging JSON structuré avec OTEL et anti-flood.

Ce module remplace les fichiers `logger.py` locaux dupliqués dans chaque
service. Il suffit d'importer :

    from shared.observability import setup_logging, LoggingMiddleware

Différence vs les anciens logger.py :
- `SERVICE_NAME` lu dynamiquement depuis l'env (plus de valeur par défaut
  hardcodée différente par service).
- `ENVIRONMENT` idem.
"""
import logging
import os
import threading
import time
from collections import defaultdict

from opentelemetry import trace
from pythonjsonlogger import json
from starlette.types import ASGIApp, Receive, Scope, Send

# Chemins exclus des logs HTTP (health-check / instrumentation)
SILENT_PATHS: frozenset = frozenset({
    "/health", "/ready", "/metrics", "/docs",
    "/openapi.json", "/version", "/health/agents",
    "/api/health",
})


class HealthCheckFilter(logging.Filter):
    """Supprime les logs uvicorn.access pour les endpoints de supervision.

    Uvicorn formate ses access-logs ainsi :
        '127.0.0.1:PORT - "GET /health HTTP/1.1" 200'
    Ce filtre inspecte le message et supprime la ligne si le path appartient
    à SILENT_PATHS, quelle que soit l'ordre d'initialisation d'Uvicorn.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if not msg:
            req_line = getattr(record, "request_line", "")
            if req_line:
                msg = f'"{req_line}"'
        return not any(
            f'"GET {p} ' in msg or f'"POST {p} ' in msg
            or f'"HEAD {p} ' in msg or f'"OPTIONS {p} ' in msg
            for p in SILENT_PATHS
        )


class OpenTelemetryJsonFormatter(json.JsonFormatter):
    """Injecte trace_id/span_id + champs de service dans chaque log JSON."""

    def add_fields(
        self,
        log_record: dict,
        record: logging.LogRecord,
        message_dict: dict,
    ) -> None:
        super().add_fields(log_record, record, message_dict)
        # Lu dynamiquement — permet d'hériter du bon SERVICE_NAME au runtime
        log_record["service"] = os.getenv("SERVICE_NAME", "unknown-service")
        log_record["environment"] = os.getenv("ENVIRONMENT", "dev")
        span = trace.get_current_span()
        if span and span.is_recording():
            ctx = span.get_span_context()
            log_record["trace_id"] = format(ctx.trace_id, "032x")
            log_record["span_id"] = format(ctx.span_id, "016x")


class ThrottledHandler(logging.Handler):
    """Anti-flood : déduplique les logs identiques sur une fenêtre glissante.

    Un même message (level + module + message) n'est émis qu'une fois toutes
    `window_seconds` secondes. Lorsque la fenêtre expire, le message est
    réémis avec un suffixe indiquant le nombre de suppressions (ex: [×42]).
    """

    def __init__(self, delegate: logging.Handler, window_seconds: int = 60) -> None:
        super().__init__()
        self._delegate = delegate
        self._window = window_seconds
        self._counts: dict = defaultdict(int)
        self._last_seen: dict = {}
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        key = f"{record.levelno}:{record.module}:{record.getMessage()}"
        now = time.monotonic()
        with self._lock:
            last = self._last_seen.get(key, 0.0)
            count = self._counts[key]
            if now - last >= self._window:
                if count > 0:
                    record = logging.makeLogRecord(record.__dict__)
                    record.msg = f"[×{count + 1}] {record.msg}"
                    record.args = None
                self._last_seen[key] = now
                self._counts[key] = 0
                self._delegate.emit(record)
            else:
                self._counts[key] += 1


def setup_logging() -> logging.Logger:
    """Configure le logging JSON structuré avec filtre health-check et anti-flood."""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    root = logging.getLogger()
    root.setLevel(log_level)

    # Nettoyage des handlers existants (évite les doublons au rechargement)
    for h in root.handlers[:]:
        root.removeHandler(h)

    stream_handler = logging.StreamHandler()
    formatter = OpenTelemetryJsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    stream_handler.setFormatter(formatter)

    throttled = ThrottledHandler(stream_handler, window_seconds=60)
    root.addHandler(throttled)

    # Silence des loggers bruités
    noisy_loggers = [
        "httpcore", "httpx", "opentelemetry",
        "sqlalchemy.engine", "google.auth", "urllib3",
    ]
    for name in noisy_loggers:
        logging.getLogger(name).setLevel(logging.WARNING)

    # Filtre uvicorn.access : supprime les health-checks
    uv_access = logging.getLogger("uvicorn.access")
    uv_access.addFilter(HealthCheckFilter())
    if log_level != "DEBUG":
        uv_access.setLevel(logging.WARNING)
        logging.getLogger("uvicorn.error").setLevel(logging.WARNING)

    return root


class LoggingMiddleware:
    """Middleware HTTP structuré (ASGI pur — compatible Starlette ≥ 0.40 + Python 3.13).

    Implémenté comme middleware ASGI pur (sans BaseHTTPMiddleware) pour éviter
    le bug `RuntimeError: No response returned.` introduit par Starlette ≥ 0.40
    qui utilise les ExceptionGroup de Python 3.13 dans call_next().

    - Exclut les endpoints de supervision (SILENT_PATHS).
    - Log en WARNING pour les 4xx, ERROR pour les 5xx.
    - Utilise http.path (sans query string) pour éviter de loguer des données
      sensibles.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.time()
        _logger = logging.getLogger("middleware.http")
        path = scope.get("path", "")
        method = scope.get("method", "")
        status_code: int = 500

        async def send_wrapper(message: dict) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
            if path not in SILENT_PATHS:
                duration = round(time.time() - start, 4)
                level = logging.WARNING if status_code >= 400 else logging.INFO
                _logger.log(
                    level,
                    "HTTP Request Processed",
                    extra={
                        "http.method": method,
                        "http.path": path,
                        "http.status_code": status_code,
                        "http.duration_s": duration,
                    },
                )

        except Exception as exc:
            if path not in SILENT_PATHS:
                _logger.error(
                    "HTTP Request Failed",
                    extra={
                        "http.method": method,
                        "http.path": path,
                        "http.status_code": 500,
                        "http.duration_s": round(time.time() - start, 4),
                        "error": str(exc),
                    },
                    exc_info=True,
                )
            raise
