import httpx
from typing import List, Any, Optional
import logging
import asyncio
import threading
import os
import contextvars
from opentelemetry.propagate import inject

auth_header_var = contextvars.ContextVar("auth_header", default=None)

logger = logging.getLogger(__name__)

class MCPHttpClient:
    def __init__(self, url: str):
        self.url = url
        self._initialized = True # HTTP is inherently stateless, no active stream to initialize

    async def connect(self):
        # No-op since we don't hold connection streams
        pass

    async def list_tools(self) -> List[Any]:
        headers = {}
        inject(headers)
        auth = auth_header_var.get(None)
        if auth:
            headers["Authorization"] = auth
        async with httpx.AsyncClient(headers=headers) as client:
            res = await client.get(f"{self.url}/mcp/tools")
            res.raise_for_status()
            return res.json()

    async def call_tool(self, tool_name: str, arguments: dict) -> List[Any]:
        import time
        logger.info(f"[MCP-HTTP] Calling tool '{tool_name}' on {self.url} with args: {arguments}")
        start_time = time.time()
        
        headers = {}
        inject(headers)
        auth = auth_header_var.get(None)
        if auth:
            headers["Authorization"] = auth
        
        async with httpx.AsyncClient(headers=headers) as client:
            try:
                res = await client.post(
                    f"{self.url}/mcp/call", 
                    json={"name": tool_name, "arguments": arguments},
                    timeout=30.0 # Define a reasonable HTTP timeout
                )
                res.raise_for_status()
                # The sidecar will return {"result": [{"text": "...", "type": "text"}]}
                result_data = res.json().get("result", [])
                
                duration = time.time() - start_time
                logger.info(f"[MCP-HTTP] Tool '{tool_name}' completed in {duration:.2f}s")
                return result_data
            except Exception as e:
                duration = time.time() - start_time
                logger.error(f"[MCP-HTTP] Tool '{tool_name}' FAILED after {duration:.2f}s: {str(e)}")
                raise

    async def stop(self):
        pass


class MCPSseClient:
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
            return [{"name": t.name, "description": t.description, "inputSchema": t.inputSchema} for t in res.tools]

    async def call_tool(self, tool_name: str, arguments: dict) -> List[Any]:
        from mcp.client.sse import sse_client
        from mcp.client.session import ClientSession
        from contextlib import AsyncExitStack
        
        import time
        logger.info(f"[MCP-SSE] Calling tool '{tool_name}' on {self.url} with args: {arguments}")
        start_time = time.time()
        
        try:
            async with AsyncExitStack() as stack:
                streams = await stack.enter_async_context(sse_client(self.url))
                session = await stack.enter_async_context(ClientSession(*streams))
                await session.initialize()
                res = await session.call_tool(tool_name, arguments)
                
                duration = time.time() - start_time
                logger.info(f"[MCP-SSE] Tool '{tool_name}' completed in {duration:.2f}s")
                return [c.model_dump() for c in res.content]
        except Exception as e:
            duration = time.time() - start_time
            err_msg = str(e)
            # Unwrap ExceptionGroup if present (Python 3.11+)
            if hasattr(e, 'exceptions'):
                sub_errs = []
                for sub_e in e.exceptions:
                    if hasattr(sub_e, 'exceptions'):
                        sub_errs.extend(str(s) for s in sub_e.exceptions)
                    else:
                        sub_errs.append(str(sub_e))
                err_msg = f"{err_msg} -> " + " | ".join(sub_errs)
                
            logger.error(f"[MCP-SSE] Tool '{tool_name}' FAILED after {duration:.2f}s: {err_msg}")
            raise RuntimeError(f"Loki MCP error: {err_msg}")
# Global clients
users_mcp_client: Optional[MCPHttpClient] = None
items_mcp_client: Optional[MCPHttpClient] = None
competencies_mcp_client: Optional[MCPHttpClient] = None
cv_mcp_client: Optional[MCPHttpClient] = None
loki_mcp_client: Optional[MCPSseClient] = None
_mcp_lock = threading.Lock()

def init_mcp_clients():
    global users_mcp_client, items_mcp_client, competencies_mcp_client, cv_mcp_client
    import os
    
    users_url = os.getenv("USERS_MCP_URL", os.getenv("USERS_API_URL", "http://users_mcp:8000"))
    items_url = os.getenv("ITEMS_MCP_URL", os.getenv("ITEMS_API_URL", "http://items_mcp:8000"))
    comps_url = os.getenv("COMPETENCIES_MCP_URL", os.getenv("COMPETENCIES_API_URL", "http://competencies_mcp:8000"))
    cv_url = os.getenv("CV_MCP_URL", os.getenv("CV_API_URL", "http://cv_mcp:8000"))
    loki_url = os.getenv("LOKI_MCP_URL", "http://loki_mcp:8080/sse")

    with _mcp_lock:
        global loki_mcp_client
        if users_mcp_client is None:
            users_mcp_client = MCPHttpClient(users_url)
        if items_mcp_client is None:
            items_mcp_client = MCPHttpClient(items_url)
        if competencies_mcp_client is None:
            competencies_mcp_client = MCPHttpClient(comps_url)
        if cv_mcp_client is None:
            cv_mcp_client = MCPHttpClient(cv_url)
        if loki_mcp_client is None:
            loki_mcp_client = MCPSseClient(loki_url)

async def get_users_mcp() -> MCPHttpClient:
    init_mcp_clients()
    return users_mcp_client

async def get_items_mcp() -> MCPHttpClient:
    init_mcp_clients()
    return items_mcp_client

async def get_competencies_mcp() -> MCPHttpClient:
    init_mcp_clients()
    return competencies_mcp_client

async def get_loki_mcp() -> MCPSseClient:
    init_mcp_clients()
    return loki_mcp_client

async def get_cv_mcp() -> MCPHttpClient:
    init_mcp_clients()
    return cv_mcp_client
