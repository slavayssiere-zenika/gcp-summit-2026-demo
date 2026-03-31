import asyncio
import json
import threading
import os
import logging
import contextvars

mcp_auth_header_var = contextvars.ContextVar("mcp_auth_header", default=None)

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.server import InitializationOptions
from mcp.types import Tool, TextContent
from opentelemetry import trace, propagate
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.propagate import inject, extract
import httpx

propagate.set_global_textmap(TraceContextTextMapPropagator())

logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s', handlers=[logging.NullHandler()])

API_BASE_URL = os.getenv("COMPETENCIES_API_URL", "http://localhost:8003")

provider = TracerProvider(
    resource=Resource.create({
        ResourceAttributes.SERVICE_NAME: "competencies-api-mcp",
        ResourceAttributes.SERVICE_VERSION: "1.0.0",
    })
)
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(insecure=True)))
trace.set_tracer_provider(provider)

tracer = trace.get_tracer(__name__)

server = Server("competencies-api")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="list_competencies",
            description="List all available competencies in the system",
            inputSchema={
                "type": "object",
                "properties": {
                    "skip": {"type": "integer", "description": "Number of items to skip", "default": 0},
                    "limit": {"type": "integer", "description": "Maximum number of items to return", "default": 10}
                }
            }
        ),
        Tool(
            name="get_competency",
            description="Get details of a specific competency by ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "competency_id": {"type": "integer", "description": "The competency ID"}
                },
                "required": ["competency_id"]
            }
        ),
        Tool(
            name="create_competency",
            description="Create a new skill/competency (Idempotent: returns existing definition if duplicate name is found).",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name of the competency"},
                    "description": {"type": "string", "description": "Short description"},
                    "parent_id": {"type": "integer", "description": "Optional parent competency ID to nest under. Only use if generating a sub-category."}
                },
                "required": ["name"]
            }
        ),
        Tool(
            name="delete_competency",
            description="Delete a competency from the catalog",
            inputSchema={
                "type": "object",
                "properties": {
                    "competency_id": {"type": "integer", "description": "The competency ID to delete"}
                },
                "required": ["competency_id"]
            }
        ),
        Tool(
            name="assign_competency_to_user",
            description="Assign a competency to a specific user",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "The user ID"},
                    "competency_id": {"type": "integer", "description": "The competency ID"}
                },
                "required": ["user_id", "competency_id"]
            }
        ),
        Tool(
            name="remove_competency_from_user",
            description="Remove a competency from a specific user",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "The user ID"},
                    "competency_id": {"type": "integer", "description": "The competency ID"}
                },
                "required": ["user_id", "competency_id"]
            }
        ),
        Tool(
            name="list_user_competencies",
            description="List all competencies assigned to a user",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "The user ID"}
                },
                "required": ["user_id"]
            }
        )
    ]


def get_trace_headers() -> dict:
    headers = {}
    inject(headers)
    return headers


def get_trace_context() -> dict:
    env_headers = {}
    for key in os.environ:
        if key.lower() in ['traceparent', 'tracestate', 'baggage']:
            env_headers[key] = os.environ[key]
    return env_headers


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    headers = get_trace_headers()
    auth = mcp_auth_header_var.get(None)
    if auth:
        headers["Authorization"] = auth
    async with httpx.AsyncClient(follow_redirects=True, headers=headers) as client:
        try:
            if name == "list_competencies":
                response = await client.get(f"{API_BASE_URL}/competencies/", params=arguments)
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "get_competency":
                response = await client.get(f"{API_BASE_URL}/competencies/{arguments['competency_id']}/")
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "create_competency":
                response = await client.post(f"{API_BASE_URL}/competencies/", json=arguments)
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "delete_competency":
                response = await client.delete(f"{API_BASE_URL}/competencies/{arguments['competency_id']}")
                response.raise_for_status()
                return [TextContent(type="text", text="Competency deleted successfully")]

            elif name == "assign_competency_to_user":
                user_id = arguments["user_id"]
                comp_id = arguments["competency_id"]
                response = await client.post(f"{API_BASE_URL}/competencies/user/{user_id}/assign/{comp_id}")
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "remove_competency_from_user":
                user_id = arguments["user_id"]
                comp_id = arguments["competency_id"]
                response = await client.delete(f"{API_BASE_URL}/competencies/user/{user_id}/remove/{comp_id}")
                response.raise_for_status()
                return [TextContent(type="text", text="Competency removed from user")]

            elif name == "list_user_competencies":
                response = await client.get(f"{API_BASE_URL}/competencies/user/{arguments['user_id']}")
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]

        except Exception as e:
            return [TextContent(type="text", text=f"Error: {str(e)}")]


async def main():
    """Main entry point for the MCP server when run as a script."""
    from mcp.server.stdio import stdio_server
    options = InitializationOptions(
        server_name="competencies-api",
        server_version="1.0.0",
        capabilities={}
    )
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options)


if __name__ == "__main__":
    asyncio.run(main())
