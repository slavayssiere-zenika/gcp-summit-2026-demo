from prometheus_client import Counter

USER_LOGINS_TOTAL = Counter("user_logins_total", "Total number of login attempts", ["status"])
USER_CREATIONS_TOTAL = Counter("user_creations_total", "Total number of user accounts created")
