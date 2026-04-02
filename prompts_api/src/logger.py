import logging
import os
import time
from pythonjsonlogger import jsonlogger
from opentelemetry import trace
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

class OpenTelemetryJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super(OpenTelemetryJsonFormatter, self).add_fields(log_record, record, message_dict)
        span = trace.get_current_span()
        if span and span.is_recording():
            ctx = span.get_span_context()
            log_record['trace_id'] = format(ctx.trace_id, '032x')
            log_record['span_id'] = format(ctx.span_id, '016x')

def setup_logging():
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logger = logging.getLogger()
    logger.setLevel(log_level)

    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    logHandler = logging.StreamHandler()
    formatter = OpenTelemetryJsonFormatter('%(asctime)s %(levelname)s %(name)s %(message)s')
    logHandler.setFormatter(formatter)
    logger.addHandler(logHandler)

    if log_level != "DEBUG":
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("opentelemetry").setLevel(logging.WARNING)
        
    return logger

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        logger = logging.getLogger("middleware.http")
        skip_paths = ["/health", "/metrics", "/docs", "/openapi.json"]
        
        try:
            response = await call_next(request)
            if request.url.path not in skip_paths:
                process_time = time.time() - start_time
                logger.info(
                    "HTTP Request Processed",
                    extra={
                        "http.method": request.method,
                        "http.url": str(request.url),
                        "http.status_code": response.status_code,
                        "http.duration_s": round(process_time, 4),
                    }
                )
            return response
        except Exception as e:
            process_time = time.time() - start_time
            logger.error(
                "HTTP Request Failed",
                extra={
                    "http.method": request.method,
                    "http.url": str(request.url),
                    "http.status_code": 500,
                    "http.duration_s": round(process_time, 4),
                    "error": str(e)
                },
                exc_info=True
            )
            raise
