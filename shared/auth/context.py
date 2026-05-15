import contextvars

# Variable de contexte pour propager le header Authorization (Bearer JWT)
# Utilisée par:
# - Les agents (MCP clients) lors des appels vers les APIs
# - Les serveurs MCP (Data APIs) pour l'authentification interne
auth_header_var = contextvars.ContextVar("mcp_auth_header", default=None)
