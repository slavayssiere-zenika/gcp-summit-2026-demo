"""
context.py — Variables de contexte partagées entre mcp_server.py et les tools.

Centralise le ContextVar `mcp_auth_header_var` pour éviter les imports circulaires
entre mcp_server.py (qui définit le serveur MCP) et tools/ (qui consomment le header).
"""

import contextvars

# Propagé depuis mcp_app.py lors de chaque appel MCP entrant
mcp_auth_header_var = contextvars.ContextVar("mcp_auth_header", default=None)
