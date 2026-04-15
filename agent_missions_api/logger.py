import logging
import os
import time

from fastapi import Request
from opentelemetry import trace
from pythonjsonlogger import jsonlogger
from starlette.middleware.base import BaseHTTPMiddleware


class OpenTelemetryJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        span = trace.get_current_span()
        if span and span.is_recording():
            ctx = span.get_span_context()
            log_record["trace_id"] = format(ctx.trace_id, "032x")
            log_record["span_id"] = format(ctx.span_id, "016x")


def setup_logging():
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler()
    formatter = OpenTelemetryJsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    if log_level != "DEBUG":
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("opentelemetry").setLevel(logging.WARNING)

    return root_logger


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        mw_logger = logging.getLogger("middleware.http")

        try:
            response = await call_next(request)
            if not request.url.path.endswith(("/health", "/metrics", "/docs", "/openapi.json")):
                duration = time.time() - start_time
                mw_logger.info(
                    "HTTP Request Processed",
                    extra={
                        "http.method": request.method,
                        "http.url": str(request.url),
                        "http.status_code": response.status_code,
                        "http.duration_s": round(duration, 4),
                    }
                )
            return response
        except Exception as e:
            duration = time.time() - start_time
            mw_logger.error(
                "HTTP Request Failed",
                extra={
                    "http.method": request.method,
                    "http.url": str(request.url),
                    "http.status_code": 500,
                    "http.duration_s": round(duration, 4),
                    "error": str(e),
                },
                exc_info=True
            )
            raise
