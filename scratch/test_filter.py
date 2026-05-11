import logging

SILENT_PATHS = frozenset({"/health", "/ready", "/metrics", "/docs", "/openapi.json", "/version", "/health/agents"})

class HealthCheckFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
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

# Uvicorn 0.22+ access log format
logger.info('%s:%s - "%s %s HTTP/%s" %d', '169.254.169.126', '29497', 'GET', '/health', '1.1', 200)

