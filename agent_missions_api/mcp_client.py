import httpx
import logging
import asyncio
import threading
import time
import os
import contextvars
from typing import Any, List, Optional

from opentelemetry.propagate import inject
from metrics import AGENT_TOOL_CALLS_TOTAL


auth_header_var = contextvars.ContextVar("auth_header", default=None)

logger = logging.getLogger(__name__)

# Outils avec des temps d'exécution longs (> 30s)
# LLM calls, vector search, reanalyse IA, RAG context building
LONG_RUNNING_TOOLS = {
    "search_best_candidates",
    "reanalyze_mission",
    "get_candidate_rag_context",
    "analyze_cv",
    "global_reanalyze_cvs",
}


class MCPHttpClient:
    def __init__(self, url: str):
        self.url = url
        self._initialized = True  # HTTP stateless — pas de stream à initialiser

    async def connect(self):
        pass  # No-op

    async def list_tools(self) -> List[Any]:
        headers: dict = {}
        inject(headers)
        auth = auth_header_var.get(None)
        if auth:
            headers["Authorization"] = auth
        async with httpx.AsyncClient(headers=headers) as client:
            res = await client.get(f"{self.url.rstrip('/')}/mcp/tools")
            res.raise_for_status()
            return res.json()

    async def call_tool(self, tool_name: str, arguments: dict) -> List[Any]:
        AGENT_TOOL_CALLS_TOTAL.labels(tool_name=tool_name).inc()
        logger.info("[MCP-HTTP] Calling tool '%s' on %s with args: %s", tool_name, self.url, arguments)
        start_time = time.time()

        headers: dict = {}
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
                    timeout=timeout
                )
                res.raise_for_status()
                result_data = res.json().get("result", [])
                duration = time.time() - start_time
                logger.info("[MCP-HTTP] Tool '%s' completed in %.2fs", tool_name, duration)
                return result_data
            except Exception as e:
                duration = time.time() - start_time
                logger.error("[MCP-HTTP] Tool '%s' FAILED after %.2fs: %s", tool_name, duration, e)
                raise

    async def stop(self):
        pass


class MCPSseClient:
    """Client SSE — conservé pour compatibilité avec les MCPs legacy."""

    def __init__(self, url: str):
        self.url = url

    async def list_tools(self) -> List[Any]:
        from mcp.client.sse import sse_client
        from mcp.client.session import ClientSession
        from contextlib import AsyncExitStack

        async with AsyncExitStack() as stack:
            streams = await stack.enter_async_context(sse_client(self.url))
            session = await stack.enter_async_context(ClientSession(*streams))
            await session.initialize()
            res = await session.list_tools()
            return [
                {"name": t.name, "description": t.description, "inputSchema": t.inputSchema}
                for t in res.tools
            ]

    async def call_tool(self, tool_name: str, arguments: dict) -> List[Any]:
        from mcp.client.sse import sse_client
        from mcp.client.session import ClientSession
        from contextlib import AsyncExitStack

        AGENT_TOOL_CALLS_TOTAL.labels(tool_name=tool_name).inc()
        logger.info("[MCP-SSE] Calling tool '%s' on %s", tool_name, self.url)
        start_time = time.time()

        try:
            async with AsyncExitStack() as stack:
                headers: dict = {}
                inject(headers)
                auth = auth_header_var.get(None)
                if auth:
                    headers["Authorization"] = auth
                streams = await stack.enter_async_context(sse_client(self.url, headers=headers))
                session = await stack.enter_async_context(ClientSession(*streams))
                await session.initialize()
                res = await session.call_tool(tool_name, arguments)
                duration = time.time() - start_time
                logger.info("[MCP-SSE] Tool '%s' completed in %.2fs", tool_name, duration)
                return [c.model_dump() for c in res.content]
        except Exception as e:
            duration = time.time() - start_time
            logger.error("[MCP-SSE] Tool '%s' FAILED after %.2fs: %s", tool_name, duration, e)
            raise


# Singletons (missions_mcp n'a besoin que de ses 4 clients)
_missions_mcp_client: Optional[MCPHttpClient] = None
_cv_mcp_client: Optional[MCPHttpClient] = None
_users_mcp_client: Optional[MCPHttpClient] = None
_competencies_mcp_client: Optional[MCPHttpClient] = None
_mcp_lock = threading.Lock()


def init_mcp_clients():
    global _missions_mcp_client, _cv_mcp_client, _users_mcp_client, _competencies_mcp_client

    missions_url = os.getenv("MISSIONS_MCP_URL", "http://missions_mcp:8000")
    cv_url = os.getenv("CV_MCP_URL", "http://cv_mcp:8000")
    users_url = os.getenv("USERS_MCP_URL", "http://users_mcp:8000")
    comps_url = os.getenv("COMPETENCIES_MCP_URL", "http://competencies_mcp:8000")

    with _mcp_lock:
        if _missions_mcp_client is None:
            _missions_mcp_client = MCPHttpClient(missions_url)
        if _cv_mcp_client is None:
            _cv_mcp_client = MCPHttpClient(cv_url)
        if _users_mcp_client is None:
            _users_mcp_client = MCPHttpClient(users_url)
        if _competencies_mcp_client is None:
            _competencies_mcp_client = MCPHttpClient(comps_url)


async def get_missions_mcp() -> MCPHttpClient:
    init_mcp_clients()
    return _missions_mcp_client


async def get_cv_mcp() -> MCPHttpClient:
    init_mcp_clients()
    return _cv_mcp_client


async def get_users_mcp() -> MCPHttpClient:
    init_mcp_clients()
    return _users_mcp_client


async def get_competencies_mcp() -> MCPHttpClient:
    init_mcp_clients()
    return _competencies_mcp_client
