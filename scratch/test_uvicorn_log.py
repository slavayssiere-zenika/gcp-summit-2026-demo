import logging

class HealthCheckFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        print("Message evaluated as:", repr(msg))
        return True

logger = logging.getLogger("test")
logger.addFilter(HealthCheckFilter())
handler = logging.StreamHandler()
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Simulate what uvicorn might do
logger.info('', extra={'client_addr': '169.254.169.126:29497', 'request_line': 'GET /health HTTP/1.1', 'status_code': 200})

