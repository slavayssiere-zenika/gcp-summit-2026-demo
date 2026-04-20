"""
mcp_proxy.py — Dynamic MCP-to-ADK tool proxy factory + cached tool loader.

Extracted from the three agent.py files (create_mcp_tool_proxy and
_get_cached_tools were strictly identical in HR, Ops, and Missions agents).

Key exports:
  - create_mcp_tool_proxy(client, tool_def)
      Build a Python async function wrapping a remote MCP tool so that the
      Google ADK can validate and call it as a native function.

  - get_cached_tools(clients_map, agent_prefix, ttl)
      Fetch, cache, deduplicate, and filter MCP tool definitions from a list
      of MCP clients.  Returns a list of proxy functions ready to pass to
      google.adk.agents.Agent(tools=...).
"""

import inspect
import logging
import time
from typing import Any

from agent_commons.mcp_client import MCPHttpClient

logger = logging.getLogger(__name__)

# Infrastructure tools that must never be exposed to the LLM.
NON_BUSINESS_TOOLS: frozenset[str] = frozenset({
    "health_check", "ping", "healthcheck", "health", "status"
})


def create_mcp_tool_proxy(client: MCPHttpClient, tool_def: dict) -> Any:
    """Build a Python async function wrapping a remote MCP tool.

    The returned callable has:
      - ``__name__``      → tool name (used by ADK as the function declaration name)
      - ``__doc__``       → tool description (used by the LLM to choose the tool)
      - ``__signature__`` → reconstructed from the JSON Schema (used by ADK for
                            parameter validation before calling Gemini)

    Type-mapping rules (JSON Schema → Python):
      - string  → str
      - integer → int
      - number  → float
      - boolean → bool
      - array / object → ``object``  (NEVER ``list`` — Gemini rejects arrays
        without an ``items`` field and would return 400 INVALID_ARGUMENT)

    Args:
        client:   MCPHttpClient pointing to the target MCP sidecar.
        tool_def: Tool definition dict as returned by ``client.list_tools()``.

    Returns:
        An async callable passable to ``Agent(tools=[...])``.
    """
    name = tool_def["name"]
    desc = tool_def.get("description", "No description")
    schema = tool_def.get("parameters", tool_def.get("inputSchema", {}))

    async def mcp_tool_wrapper(**kwargs):
        return await client.call_tool(name, kwargs)

    mcp_tool_wrapper.__name__ = name
    mcp_tool_wrapper.__doc__ = desc

    params = []
    properties = schema.get("properties", {})
    required = schema.get("required", [])

    for p_name, p_def in properties.items():
        # IMPORTANT: Use `object` (not `Any`) as the fallback type.
        # ADK calls isinstance(default_value, annotation) to validate optional
        # params.  isinstance(None, typing.Any) raises TypeError — whereas
        # isinstance(None, object) returns True.
        p_type = object
        js_type = p_def.get("type")
        if js_type == "string":
            p_type = str
        elif js_type == "integer":
            p_type = int
        elif js_type == "number":
            p_type = float
        elif js_type == "boolean":
            p_type = bool
        # array / object → falls through to `object` (safe fallback)

        default = inspect.Parameter.empty
        if p_name not in required:
            default = p_def.get("default", None)

        params.append(inspect.Parameter(
            p_name,
            inspect.Parameter.KEYWORD_ONLY,
            default=default,
            annotation=p_type,
        ))

    mcp_tool_wrapper.__signature__ = inspect.Signature(params)
    return mcp_tool_wrapper


async def get_cached_tools(
    clients_map: list[tuple[str, MCPHttpClient]],
    agent_prefix: str,
    ttl: int = 300,
    *,
    _cache: dict = {},
) -> list:
    """Fetch, cache, deduplicate, and filter MCP tool proxies.

    Args:
        clients_map:   Ordered list of ``(service_name, MCPHttpClient)`` pairs.
        agent_prefix:  Short label used in log messages (e.g. ``"[HR]"``).
        ttl:           Cache TTL in seconds (default: 300 s / 5 min).
        _cache:        Internal mutable default used as a per-call-site cache.
                       Pass a dedicated ``{}`` if you need independent caches
                       for different agents in the same process.

    Returns:
        List of async callables (MCP tool proxies) after deduplication and
        infrastructure-tool filtering.

    Note:
        ``_cache`` uses a mutable default dict deliberately so that each
        *call site* (i.e. each agent module) that passes its own ``_cache``
        dict gets an isolated cache.  The module-level default is shared only
        when no explicit cache is passed — which is intentional for single-
        agent processes.
    """
    now = time.time()
    cache_key = id(clients_map)

    if _cache.get("tools") and (now - _cache.get("ts", 0)) < ttl:
        logger.info("%s Using cached MCP tool definitions (%d tools).", agent_prefix, len(_cache["tools"]))
        return _cache["tools"]

    logger.info("%s Fetching MCP tool definitions from MCP sidecars...", agent_prefix)

    raw_tools: list = []
    for svc_name, client in clients_map:
        logger.info("%s Connecting to %s at %s ...", agent_prefix, svc_name, client.url)
        try:
            service_tools = await client.list_tools()
            count = 0
            for t in service_tools:
                try:
                    proxy = create_mcp_tool_proxy(client, t)
                    raw_tools.append(proxy)
                    count += 1
                except Exception as te:
                    logger.error("%s Failed to proxy tool %s: %s", agent_prefix, t.get("name"), te)
            logger.info("%s ✅ Loaded %d tools from %s.", agent_prefix, count, svc_name)
        except Exception as e:
            logger.error(
                "%s ❌ Could NOT load tools from %s (%s): %s — agent will have REDUCED capabilities",
                agent_prefix, svc_name, client.url, e,
            )

    # Deduplicate by function name (Gemini rejects duplicate function declarations
    # with 400 INVALID_ARGUMENT) and filter out non-business infrastructure tools.
    seen_names: set[str] = set()
    tools: list = []
    for proxy in raw_tools:
        fn_name = proxy.__name__
        if fn_name in NON_BUSINESS_TOOLS:
            logger.debug("%s Skipping non-business tool: %s", agent_prefix, fn_name)
            continue
        if fn_name in seen_names:
            logger.warning("%s Duplicate tool name '%s' skipped (kept first).", agent_prefix, fn_name)
            continue
        seen_names.add(fn_name)
        tools.append(proxy)

    if not tools:
        # Ne pas mettre en cache un résultat vide : cela arrive typiquement au démarrage
        # quand auth_header_var est None (pas de requête HTTP en cours) → les APIs
        # data retournent 401 → list_tools() échoue → 0 tools chargés.
        # Sans ce guard, le cache vide est conservé pendant `ttl` secondes, rendant
        # l'agent incapable d'appeler des outils pendant toute cette durée.
        logger.warning(
            "%s ⚠️ 0 tools loaded — cache NOT persisted so the next real request "
            "(with a valid JWT) will trigger a fresh fetch.",
            agent_prefix,
        )
    else:
        _cache["tools"] = tools
        _cache["ts"] = now
        logger.info("%s Cached %d unique business MCP tools (TTL=%ds).", agent_prefix, len(tools), ttl)
    return tools
