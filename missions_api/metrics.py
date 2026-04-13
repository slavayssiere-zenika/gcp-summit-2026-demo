from prometheus_client import Counter

MISSIONS_CREATED_TOTAL = Counter("missions_created_total", "Total number of missions processed by AI", ["status"])
