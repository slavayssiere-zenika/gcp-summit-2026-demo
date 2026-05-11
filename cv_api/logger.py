import logging
import os
import threading
import time
from collections import defaultdict

from fastapi import Request
from opentelemetry import trace
from pythonjsonlogger import jsonlogger
from starlette.middleware.base import BaseHTTPMiddleware

# ─────────────────────────────────────────────────────────────────────────────
# Chemins exclus des logs HTTP (health-check / instrumentation)
# ─────────────────────────────────────────────────────────────────────────────
SILENT_PATHS: frozenset = frozenset({
    "/health", "/ready", "/metrics", "/docs",
    "/openapi.json", "/version", "/health/agents",
})


class HealthCheckFilter(logging.Filter):
    """
    Supprime les logs uvicorn.access pour les endpoints de supervision.

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
            f'"GET {p} ' in msg or f'"POST {p} ' in msg or
            f'"HEAD {p} ' in msg or f'"OPTIONS {p} ' in msg
            for p in SILENT_PATHS
        )


class OpenTelemetryJsonFormatter(jsonlogger.JsonFormatter):
    """Injecte trace_id/span_id + champs de service dans chaque log JSON."""

    _service_name: str = os.getenv("SERVICE_NAME", "cv-api")
    _environment: str = os.getenv("ENVIRONMENT", "dev")

    def add_fields(self, log_record: dict, record: logging.LogRecord, message_dict: dict) -> None:
        super().add_fields(log_record, record, message_dict)
        log_record["service"] = self._service_name
        log_record["environment"] = self._environment
        span = trace.get_current_span()
        if span and span.is_recording():
            ctx = span.get_span_context()
            log_record["trace_id"] = format(ctx.trace_id, "032x")
            log_record["span_id"] = format(ctx.span_id, "016x")


class ThrottledHandler(logging.Handler):
    """
    Anti-flood : déduplique les logs identiques sur une fenêtre glissante.

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

    for h in root.handlers[:]:
        root.removeHandler(h)

    stream_handler = logging.StreamHandler()
    formatter = OpenTelemetryJsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    stream_handler.setFormatter(formatter)

    throttled = ThrottledHandler(stream_handler, window_seconds=60)
    root.addHandler(throttled)

    noisy_loggers = [
        "httpcore", "httpx", "opentelemetry",
        "sqlalchemy.engine", "google.auth", "urllib3",
    ]
    for name in noisy_loggers:
        logging.getLogger(name).setLevel(logging.WARNING)

    uv_access = logging.getLogger("uvicorn.access")
    uv_access.addFilter(HealthCheckFilter())
    if log_level != "DEBUG":
        uv_access.setLevel(logging.WARNING)
        logging.getLogger("uvicorn.error").setLevel(logging.WARNING)

    return root


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware HTTP structuré.

    - Exclut les endpoints de supervision (SILENT_PATHS).
    - Log en WARNING pour les 4xx, ERROR pour les 5xx.
    - Utilise http.path (sans query string) pour éviter de loguer des données sensibles.
    """

    async def dispatch(self, request: Request, call_next):
        start = time.time()
        logger = logging.getLogger("middleware.http")
        path = request.url.path

        try:
            response = await call_next(request)
            if path not in SILENT_PATHS:
                duration = round(time.time() - start, 4)
                level = logging.WARNING if response.status_code >= 400 else logging.INFO
                logger.log(
                    level,
                    "HTTP Request Processed",
                    extra={
                        "http.method": request.method,
                        "http.path": path,
                        "http.status_code": response.status_code,
                        "http.duration_s": duration,
                    },
                )
            return response

        except Exception as exc:
            if path not in SILENT_PATHS:
                logger.error(
                    "HTTP Request Failed",
                    extra={
                        "http.method": request.method,
                        "http.path": path,
                        "http.status_code": 500,
                        "http.duration_s": round(time.time() - start, 4),
                        "error": str(exc),
                    },
                    exc_info=True,
                )
            raise
