"""
mcp_client.py — HTTP and SSE MCP client classes shared across all ADK agents.

Extracted from agent_hr_api/mcp_client.py (identical in agent_ops_api and agent_missions_api).

Key exports:
  - auth_header_var    : ContextVar propagating the JWT Authorization header
  - MCPHttpClient      : Stateless HTTP-based MCP client (preferred)
  - MCPSseClient       : SSE-based MCP client (legacy/fallback)
  - LONG_RUNNING_TOOLS : Set of tools that require a 120s timeout
"""

import asyncio
import contextvars
import logging
import os
import time
import threading
from typing import Any, List, Optional

import httpx
from opentelemetry.propagate import inject
from prometheus_client import Counter

# ---------------------------------------------------------------------------
# Prometheus metric — defined here so it is imported from a single location
# and does not clash with per-service metrics.py registries.
# ---------------------------------------------------------------------------
try:
    AGENT_TOOL_CALLS_TOTAL = Counter(
        "agent_tool_calls_total",
        "Total number of tool calls made by the agent",
        ["tool_name"],
    )
except ValueError:
    # Already registered — happens when multiple agents share the same
    # CollectorRegistry in a test environment (parallel test_env imports).
    from prometheus_client import REGISTRY
    AGENT_TOOL_CALLS_TOTAL = REGISTRY._names_to_collectors.get(  # type: ignore[attr-defined]
        "agent_tool_calls_total",
        Counter("agent_tool_calls_total_fallback", "fallback", ["tool_name"]),
    )

# ---------------------------------------------------------------------------
# Context variable — propagates Authorization header across async boundaries.
# ---------------------------------------------------------------------------
auth_header_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "auth_header", default=None
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tools that are known to exceed the standard 30 s timeout.
# These involve LLM calls, vector search, or large data processing.
# ---------------------------------------------------------------------------
LONG_RUNNING_TOOLS: set[str] = {
    "analyze_cv",
    "search_best_candidates",
    "reanalyze_mission",
    "global_reanalyze_cvs",
    "recalculate_competencies_tree",
    "get_infrastructure_topology",
    "get_candidate_rag_context",
    "get_aiops_dashboard_data",
}


# ---------------------------------------------------------------------------
# MCPHttpClient — stateless HTTP MCP client (preferred over SSE)
# ---------------------------------------------------------------------------
class MCPHttpClient:
    """Stateless HTTP client for MCP sidecars.

    Endpoints called:
      GET  {url}/mcp/tools  → list available tools
      POST {url}/mcp/call   → invoke a tool
    """

    def __init__(self, url: str) -> None:
        self.url = url
        self._initialized = True  # HTTP is inherently stateless

    async def connect(self) -> None:
        """No-op — HTTP is connectionless."""

    async def list_tools(self) -> List[Any]:
        """Return the list of tool definitions from the MCP sidecar."""
        headers: dict[str, str] = {}
        inject(headers)
        auth = auth_header_var.get(None)
        if auth:
            headers["Authorization"] = auth
        async with httpx.AsyncClient(headers=headers) as client:
            res = await client.get(f"{self.url.rstrip('/')}/mcp/tools")
            res.raise_for_status()
            return res.json()

    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        """Invoke *tool_name* with *arguments* on the remote MCP sidecar."""
        AGENT_TOOL_CALLS_TOTAL.labels(tool_name=tool_name).inc()
        logger.info("[MCP-HTTP] Calling tool '%s' on %s with args: %s", tool_name, self.url, arguments)
        start_time = time.time()

        headers: dict[str, str] = {}
        inject(headers)
        auth = auth_header_var.get(None)
        if auth:
            headers["Authorization"] = auth

        async with httpx.AsyncClient(headers=headers) as client:
            try:
                timeout = 120.0 if tool_name in LONG_RUNNING_TOOLS else 30.0
                res = await client.post(
                    f"{self.url.rstrip('/')}/mcp/call",
                    json={"name": tool_name, "arguments": arguments},
                    timeout=timeout,
                )
                res.raise_for_status()
                # Sidecar returns {"result": [{"text": "...", "type": "text"}]}
                result_data = res.json().get("result", [])
                logger.info("[MCP-HTTP] Tool '%s' completed in %.2fs", tool_name, time.time() - start_time)
                return result_data
            except Exception as e:
                logger.error("[MCP-HTTP] Tool '%s' FAILED after %.2fs: %s", tool_name, time.time() - start_time, e)
                raise

    async def stop(self) -> None:
        """No-op."""


# ---------------------------------------------------------------------------
# MCPSseClient — SSE-based MCP client (legacy/fallback)
# ---------------------------------------------------------------------------
class MCPSseClient:
    """SSE-based MCP client. Use MCPHttpClient when possible (stateless)."""

    def __init__(self, url: str) -> None:
        self.url = url

    async def list_tools(self) -> List[Any]:
        from contextlib import AsyncExitStack

        from mcp.client.session import ClientSession
        from mcp.client.sse import sse_client

        async with AsyncExitStack() as stack:
            streams = await stack.enter_async_context(sse_client(self.url))
            session = await stack.enter_async_context(ClientSession(*streams))
            await session.initialize()
            res = await session.list_tools()
            return [{"name": t.name, "description": t.description, "inputSchema": t.inputSchema} for t in res.tools]

    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        from contextlib import AsyncExitStack

        from mcp.client.session import ClientSession
        from mcp.client.sse import sse_client

        AGENT_TOOL_CALLS_TOTAL.labels(tool_name=tool_name).inc()
        logger.info("[MCP-SSE] Calling tool '%s' on %s", tool_name, self.url)
        start_time = time.time()

        try:
            async with AsyncExitStack() as stack:
                headers: dict[str, str] = {}
                inject(headers)
                auth = auth_header_var.get(None)
                if auth:
                    headers["Authorization"] = auth

                streams = await stack.enter_async_context(sse_client(self.url, headers=headers))
                session = await stack.enter_async_context(ClientSession(*streams))
                await session.initialize()
                res = await session.call_tool(tool_name, arguments)
                logger.info("[MCP-SSE] Tool '%s' completed in %.2fs", tool_name, time.time() - start_time)
                return [c.model_dump() for c in res.content]
        except Exception as e:
            err_msg = str(e)
            # Unwrap ExceptionGroup (Python 3.11+)
            if hasattr(e, "exceptions"):
                sub_errs = []
                for sub_e in e.exceptions:
                    if hasattr(sub_e, "exceptions"):
                        sub_errs.extend(str(s) for s in sub_e.exceptions)
                    else:
                        sub_errs.append(str(sub_e))
                err_msg = f"{err_msg} -> " + " | ".join(sub_errs)
            logger.error("[MCP-SSE] Tool '%s' FAILED after %.2fs: %s", tool_name, time.time() - start_time, err_msg)
            raise


# ---------------------------------------------------------------------------
# Singleton MCP client factory (optional — agents may instantiate directly)
# ---------------------------------------------------------------------------
_mcp_lock = threading.Lock()
_clients: dict[str, Optional[MCPHttpClient]] = {
    "users": None,
    "items": None,
    "competencies": None,
    "cv": None,
    "drive": None,
    "missions": None,
    "market": None,
    "monitoring": None,
}


def init_mcp_clients() -> None:
    """Lazily initialise all known MCP clients from environment variables."""
    with _mcp_lock:
        if _clients["users"] is None:
            _clients["users"] = MCPHttpClient(os.getenv("USERS_MCP_URL", os.getenv("USERS_API_URL", "http://users_mcp:8000")))
        if _clients["items"] is None:
            _clients["items"] = MCPHttpClient(os.getenv("ITEMS_MCP_URL", os.getenv("ITEMS_API_URL", "http://items_mcp:8000")))
        if _clients["competencies"] is None:
            _clients["competencies"] = MCPHttpClient(os.getenv("COMPETENCIES_MCP_URL", os.getenv("COMPETENCIES_API_URL", "http://competencies_mcp:8000")))
        if _clients["cv"] is None:
            _clients["cv"] = MCPHttpClient(os.getenv("CV_MCP_URL", os.getenv("CV_API_URL", "http://cv_mcp:8000")))
        if _clients["drive"] is None:
            _clients["drive"] = MCPHttpClient(os.getenv("DRIVE_MCP_URL", "http://drive_mcp:8000"))
        if _clients["missions"] is None:
            _clients["missions"] = MCPHttpClient(os.getenv("MISSIONS_MCP_URL", os.getenv("MISSIONS_API_URL", "http://missions_mcp:8009")))
        if _clients["market"] is None:
            _clients["market"] = MCPHttpClient(os.getenv("MARKET_MCP_URL", "http://market_mcp:8008"))
        if _clients["monitoring"] is None:
            _clients["monitoring"] = MCPHttpClient(os.getenv("MONITORING_MCP_URL", "http://monitoring_mcp:8010"))


async def get_users_mcp() -> MCPHttpClient:
    init_mcp_clients()
    return _clients["users"]  # type: ignore[return-value]


async def get_items_mcp() -> MCPHttpClient:
    init_mcp_clients()
    return _clients["items"]  # type: ignore[return-value]


async def get_competencies_mcp() -> MCPHttpClient:
    init_mcp_clients()
    return _clients["competencies"]  # type: ignore[return-value]


async def get_cv_mcp() -> MCPHttpClient:
    init_mcp_clients()
    return _clients["cv"]  # type: ignore[return-value]


async def get_drive_mcp() -> MCPHttpClient:
    init_mcp_clients()
    return _clients["drive"]  # type: ignore[return-value]


async def get_market_mcp() -> MCPHttpClient:
    init_mcp_clients()
    return _clients["market"]  # type: ignore[return-value]


async def get_missions_mcp() -> MCPHttpClient:
    init_mcp_clients()
    return _clients["missions"]  # type: ignore[return-value]

async def get_monitoring_mcp() -> MCPHttpClient:
    init_mcp_clients()
    return _clients["monitoring"]  # type: ignore[return-value]
