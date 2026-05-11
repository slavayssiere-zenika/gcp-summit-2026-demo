import logging

SILENT_PATHS = frozenset({"/health", "/ready", "/metrics", "/docs", "/openapi.json", "/version", "/health/agents"})

class HealthCheckFilter(logging.Filter):
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

logger = logging.getLogger("test")
logger.addFilter(HealthCheckFilter())
handler = logging.StreamHandler()
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Simulate uvicorn
logger.info('', extra={'client_addr': '169.254.169.126:29497', 'request_line': 'GET /health HTTP/1.1', 'status_code': 200})
logger.info('', extra={'client_addr': '169.254.169.126:29497', 'request_line': 'GET /api/v1/data HTTP/1.1', 'status_code': 200})

