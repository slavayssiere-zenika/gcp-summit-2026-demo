"""
mcp_proxy.py — Dynamic MCP-to-ADK tool proxy factory + cached tool loader.

Extracted from the three agent.py files (create_mcp_tool_proxy and
_get_cached_tools were strictly identical in HR, Ops, and Missions agents).

Key exports:
  - create_mcp_tool_proxy(client, tool_def)
      Build a native ADK McpTool wrapping a remote MCP tool so that the
      Google ADK can validate and call it natively.

  - get_cached_tools(clients_map, agent_prefix, ttl)
      Fetch, cache, deduplicate, and filter MCP tool definitions from a list
      of MCP clients.  Returns a list of McpTool instances ready to pass to
      google.adk.agents.Agent(tools=...).
"""

import logging
import time

from mcp.types import CallToolResult, TextContent, Tool
from google.adk.tools.mcp_tool import McpTool

from agent_commons.mcp_client import MCPHttpClient, auth_header_var

logger = logging.getLogger(__name__)

# Infrastructure tools that must never be exposed to the LLM.
NON_BUSINESS_TOOLS: frozenset[str] = frozenset({
    "health_check", "ping", "healthcheck", "health", "status"
})

# Tools reserved for admin users only — must NEVER be callable by any agent.
# These trigger LLM calls or heavy reprocessing on the entire CV corpus.
# Agents must not initiate these operations; only admins via the API/frontend.
ADMIN_ONLY_TOOLS: frozenset[str] = frozenset({
    "analyze_cv",            # POST /api/cv/import — LLM extraction unitaire
    "global_reanalyze_cvs",  # POST /api/cv/reanalyze — ré-analyse (limité à 1 CV, mais tool inéligible)
    "reindex_cv_embeddings",  # POST /api/cv/reindex-embeddings — recompute tous embeddings
    "reindex_mission_chunks",  # POST /api/cv/bulk-reanalyse/reindex-mission-chunks — reindex batch
})


class StatelessMcpSession:
    """Bridges a single MCPHttpClient REST call into the ADK MCP session protocol."""

    def __init__(self, client: MCPHttpClient) -> None:
        self._client = client

    async def call_tool(
        self,
        name: str,
        arguments: dict,
        progress_callback=None,
        meta=None,
    ) -> CallToolResult:
        """Delegate to MCPHttpClient and normalise the result into a CallToolResult.

        MCPHttpClient.call_tool may return:
          - A list of dicts  → {"text": "..."}
          - A dict with "content" key → MCP standard format
          - A dict with "result" key → {"result": "json-string", "success": True}
          - Any other scalar/dict → serialised as text
        """
        result_data = await self._client.call_tool(name, arguments)
        content: list[TextContent] = []

        if isinstance(result_data, list):
            for item in result_data:
                text = item.get("text", str(item)) if isinstance(item, dict) else str(item)
                content.append(TextContent(type="text", text=text))
        elif isinstance(result_data, dict) and "content" in result_data:
            # Standard MCP envelope
            for item in result_data["content"]:
                content.append(TextContent(
                    type=item.get("type", "text"),
                    text=item.get("text", ""),
                ))
        elif isinstance(result_data, dict) and "result" in result_data:
            # MCPHttpClient-specific envelope: {"result": "<json-string>", "success": True}
            content.append(TextContent(type="text", text=str(result_data["result"])))
        else:
            content.append(TextContent(type="text", text=str(result_data)))

        return CallToolResult(content=content)


class StatelessMcpSessionManager:
    """Provides a fresh StatelessMcpSession per ADK invocation (no persistent connection)."""

    def __init__(self, client: MCPHttpClient) -> None:
        self._client = client  # retained for create_session delegation

    async def create_session(self, headers: dict | None = None) -> StatelessMcpSession:
        return StatelessMcpSession(self._client)


def sanitize_input_schema(schema: dict) -> dict:
    """Supprime récursivement les entrées de `required` absentes de `properties`.

    Le SDK Google GenAI ignore silencieusement les champs de propriétés qu'il ne
    reconnaît pas (ex: `description` dans un items d'array imbriqué), mais conserve
    les `required` — ce qui produit une `FunctionDeclaration` invalide rejetée par
    l'API Gemini avec : 400 INVALID_ARGUMENT "property is not defined".

    Ce sanitizer nettoie le schéma *avant* la conversion SDK pour garantir que
    tout champ listé dans `required` existe bien dans `properties`.
    """
    if not isinstance(schema, dict):
        return schema

    schema = dict(schema)  # shallow copy pour ne pas muter l'original

    # Nettoyer required vs properties au niveau courant
    props = schema.get("properties", {})
    if "required" in schema and isinstance(schema["required"], list):
        filtered = [r for r in schema["required"] if r in props]
        if len(filtered) != len(schema["required"]):
            dropped = set(schema["required"]) - set(filtered)
            logger.debug(
                "[schema_sanitizer] Dropped from required (not in properties): %s", dropped
            )
        if filtered:
            schema["required"] = filtered
        else:
            schema.pop("required", None)

    # Récursion sur properties
    if "properties" in schema:
        schema["properties"] = {
            k: sanitize_input_schema(v) for k, v in schema["properties"].items()
        }

    # Récursion sur items (array schemas)
    if "items" in schema and isinstance(schema["items"], dict):
        schema["items"] = sanitize_input_schema(schema["items"])

    # Récursion sur anyOf / oneOf / allOf
    for key in ("anyOf", "oneOf", "allOf"):
        if key in schema and isinstance(schema[key], list):
            schema[key] = [
                sanitize_input_schema(s) if isinstance(s, dict) else s
                for s in schema[key]
            ]

    return schema


def create_mcp_tool_proxy(client: MCPHttpClient, tool_def: dict) -> McpTool:
    """Build a native ADK McpTool wrapping a remote MCP tool.

    Args:
        client:   MCPHttpClient pointing to the target MCP sidecar.
        tool_def: Tool definition dict as returned by ``client.list_tools()``
                  (plain Python dict from JSON, NOT a Pydantic object).

    Returns:
        A native ADK McpTool passable to ``Agent(tools=[])``.
    """
    # ADK McpTool expects the MCP standard "inputSchema" key.
    # MCPHttpClient may return the schema under "parameters" (legacy key).
    if "inputSchema" not in tool_def and "parameters" in tool_def:
        tool_def["inputSchema"] = tool_def["parameters"]

    # Sanitize before SDK conversion — prevents 400 INVALID_ARGUMENT from Gemini
    # when required[] references properties dropped by the SDK's JSON Schema conversion.
    if "inputSchema" in tool_def and isinstance(tool_def["inputSchema"], dict):
        tool_def["inputSchema"] = sanitize_input_schema(tool_def["inputSchema"])

    mcp_tool = Tool.model_validate(tool_def)
    session_manager = StatelessMcpSessionManager(client)

    def header_provider(ctx) -> dict:
        """Dynamically inject the current request's JWT into each MCP call."""
        auth = auth_header_var.get(None)
        return {"Authorization": auth} if auth else {}

    return McpTool(
        mcp_tool=mcp_tool,
        mcp_session_manager=session_manager,
        header_provider=header_provider,
    )


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
        List of ``McpTool`` instances (MCP tool proxies) after deduplication and
        infrastructure-tool filtering.

    Note:
        ``_cache`` uses a mutable default dict deliberately so that each
        *call site* (i.e. each agent module) that passes its own ``_cache``
        dict gets an isolated cache.  The module-level default is shared only
        when no explicit cache is passed — which is intentional for single-
        agent processes.
    """
    now = time.time()

    if _cache.get("tools") and (now - _cache.get("ts", 0)) < ttl:
        logger.info("%s Using cached MCP tool definitions (%d tools).", agent_prefix, len(_cache["tools"]))
        return _cache["tools"]

    logger.info("%s Fetching MCP tool definitions from MCP sidecars...", agent_prefix)

    raw_tools: list[McpTool] = []
    for svc_name, client in clients_map:
        logger.info("%s Connecting to %s at %s ...", agent_prefix, svc_name, client.url)
        try:
            service_tools = await client.list_tools()
            count = 0
            for t in service_tools:
                tool_name = t.get("name", "<unknown>") if isinstance(t, dict) else getattr(t, "name", "<unknown>")
                try:
                    proxy = create_mcp_tool_proxy(client, t)
                    raw_tools.append(proxy)
                    count += 1
                except Exception as te:
                    logger.error("%s Failed to proxy tool %s: %s", agent_prefix, tool_name, te)
            logger.info("%s ✅ Loaded %d tools from %s.", agent_prefix, count, svc_name)
        except Exception as e:
            logger.error(
                "%s ❌ Could NOT load tools from %s (%s): %s — agent will have REDUCED capabilities",
                agent_prefix, svc_name, client.url, e,
            )

    # Deduplicate by tool name (Gemini rejects duplicate function declarations
    # with 400 INVALID_ARGUMENT) and filter out non-business infrastructure tools
    # and admin-only tools (CV analysis triggers reserved for human admins).
    # NOTE: McpTool exposes `.name` (not `.__name__` which is a callable-only attr).
    seen_names: set[str] = set()
    tools: list[McpTool] = []
    for proxy in raw_tools:
        fn_name = proxy.name  # McpTool.name == mcp_tool.name (str) — NOT proxy.__name__
        if fn_name in NON_BUSINESS_TOOLS:
            logger.debug("%s Skipping non-business tool: %s", agent_prefix, fn_name)
            continue
        if fn_name in ADMIN_ONLY_TOOLS:
            logger.info(
                "%s Blocking admin-only tool '%s' — reserved for human admins via API/frontend.",
                agent_prefix, fn_name,
            )
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
