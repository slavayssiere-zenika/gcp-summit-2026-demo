import asyncio
import json
import logging
import os

import httpx
from mcp.server import InitializationOptions, Server
from mcp.types import TextContent, Tool
from shared.mcp_server_utils import get_mcp_trace_headers, setup_mcp_tracer_provider

from tools.categories import get_categories_tools, handle_categories_tool
from tools.items import get_items_tools, handle_items_tool

logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s', handlers=[logging.NullHandler()])

API_BASE_URL = os.getenv("ITEMS_API_URL", "http://localhost:8001")
USERS_API_URL = os.getenv("USERS_API_URL", "http://localhost:8000")

tracer = setup_mcp_tracer_provider("items-api-mcp")
server = Server("items-api")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return get_categories_tools() + get_items_tools()


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    headers = get_mcp_trace_headers()

    async with httpx.AsyncClient(follow_redirects=True, headers=headers) as client:
        try:
            # Try categories tools first
            res = await handle_categories_tool(name, arguments, client, API_BASE_URL)
            if res is not None:
                return res

            # Try items tools
            res = await handle_items_tool(name, arguments, client, API_BASE_URL, USERS_API_URL)
            if res is not None:
                return res

            return [TextContent(type="text", text=f"Unknown tool: {name}")]

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 409:
                return [
                    TextContent(
                        type="text",
                        text=f"CONFLIT (409) : {
                            e.response.text}. Ne PAS réessayer l'outil avec les mêmes paramètres.")]
            return [TextContent(type="text", text=f"HTTP Error: {e.response.status_code} - {e.response.text}")]
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]


async def main():
    """Main entry point for the MCP server when run as a script."""
    from mcp.server.stdio import stdio_server
    options = InitializationOptions(
        server_name="items-api",
        server_version="1.0.0",
        capabilities={}
    )
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options)


if __name__ == "__main__":
    asyncio.run(main())
