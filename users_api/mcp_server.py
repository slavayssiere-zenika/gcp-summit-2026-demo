import asyncio
import logging

import httpx
from mcp.server import InitializationOptions, Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
from shared.mcp_server_utils import get_mcp_trace_headers, setup_mcp_tracer_provider
# Importer les outils refactorisés
from src.mcp_tools.tools_handlers import handle_tool_call
from src.mcp_tools.tools_registry import get_mcp_tools

logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s', handlers=[logging.NullHandler()])

tracer = setup_mcp_tracer_provider("users-api-mcp")
server = Server("users-api")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return get_mcp_tools()


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    headers = get_mcp_trace_headers()

    async with httpx.AsyncClient(follow_redirects=True, headers=headers) as client:
        return await handle_tool_call(name, arguments, headers, client)


async def main():
    """Main entry point for the MCP server when run as a script."""
    options = InitializationOptions(
        server_name="users-api",
        server_version="1.0.0",
        capabilities={}
    )
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options)

if __name__ == "__main__":
    asyncio.run(main())
