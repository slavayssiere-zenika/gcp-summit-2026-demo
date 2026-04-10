import asyncio
import json
import threading
import os
import sys
import logging
import contextvars

mcp_auth_header_var = contextvars.ContextVar("mcp_auth_header", default=None)

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.server import InitializationOptions, NotificationOptions
from mcp.types import Tool, TextContent
from opentelemetry import trace, propagate
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes
import os
if os.getenv("TRACE_EXPORTER", "grpc") == "http":
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
elif os.getenv("TRACE_EXPORTER", "grpc") == "gcp":
    from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
else:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.propagate import inject, extract
import httpx

propagate.set_global_textmap(TraceContextTextMapPropagator())

logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s', handlers=[logging.NullHandler()])

API_BASE_URL = os.getenv("USERS_API_URL", "http://localhost:8000")

provider = TracerProvider(
    resource=Resource.create({
        ResourceAttributes.SERVICE_NAME: "users-api-mcp",
        ResourceAttributes.SERVICE_VERSION: "1.0.0",
    })
)
if os.getenv("TRACE_EXPORTER", "grpc") == "gcp":
    provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))
else:
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter() if os.getenv("TRACE_EXPORTER", "grpc") == "http" else OTLPSpanExporter(insecure=True)))
trace.set_tracer_provider(provider)

tracer = trace.get_tracer(__name__)

server = Server("users-api")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="list_users",
            description="List all users with pagination",
            inputSchema={
                "type": "object",
                "properties": {
                    "skip": {"type": "integer", "description": "Number of users to skip", "default": 0},
                    "limit": {"type": "integer", "description": "Maximum number of users to return", "default": 10}
                }
            }
        ),
        Tool(
            name="get_user",
            description="Get a user by ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "The user ID"}
                },
                "required": ["user_id"]
            }
        ),
        Tool(
            name="get_users_bulk",
            description="Get multiple users by their IDs",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "List of user IDs to retrieve"
                    }
                },
                "required": ["user_ids"]
            }
        ),
        Tool(
            name="create_user",
            description="Create a new user",
            inputSchema={
                "type": "object",
                "properties": {
                    "username": {"type": "string", "description": "Username"},
                    "email": {"type": "string", "description": "Email address"},
                    "full_name": {"type": "string", "description": "Full name (optional)"},
                    "is_anonymous": {"type": "boolean", "description": "Is this an anonymous/provisional profile?", "default": false}
                },
                "required": ["username", "email"]
            }
        ),
        Tool(
            name="update_user",
            description="Update a user",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "The user ID"},
                    "username": {"type": "string", "description": "New username (optional)"},
                    "email": {"type": "string", "description": "New email (optional)"},
                    "full_name": {"type": "string", "description": "New full name (optional)"},
                    "is_active": {"type": "boolean", "description": "Active status (optional)"},
                    "is_anonymous": {"type": "boolean", "description": "Anonymous status (optional)"}
                },
                "required": ["user_id"]
            }
        ),
        Tool(
            name="delete_user",
            description="Delete a user",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "The user ID"}
                },
                "required": ["user_id"]
            }
        ),
        Tool(
            name="health_check",
            description="Check if the API is healthy",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="search_users",
            description="Search users by username, email or full name",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {"type": "integer", "description": "Maximum number of results", "default": 10}
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="toggle_user_status",
            description="Activate or deactivate a user",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "The user ID"},
                    "is_active": {"type": "boolean", "description": "Set user active status"}
                },
                "required": ["user_id", "is_active"]
            }
        ),
        Tool(
            name="get_user_stats",
            description="Get statistics about users",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="get_user_duplicates",
            description="Get a list of potential duplicate users based on name similarity",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="merge_users",
            description="Merge a source user into a target user",
            inputSchema={
                "type": "object",
                "required": ["source_id", "target_id"]
            }
        ),
        Tool(
            name="search_anonymous_users",
            description="Search for users marked as anonymous/provisional inside the platform.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Maximum results", "default": 10}
                }
            }
        )
    ]


def get_trace_headers() -> dict:
    headers = {}
    inject(headers)
    return headers


def get_trace_context() -> dict:
    """Get trace context from environment variables (set by parent process)."""
    env_headers = {}
    for key in os.environ:
        if key.lower() in ['traceparent', 'tracestate', 'baggage']:
            env_headers[key] = os.environ[key]
    return env_headers


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    headers = get_trace_headers()
    
    # DEBUG LOGS FOR THE USER
    logging.warning(f">>> [MCP SERVER DEBUG] call_tool triggered! Tool: {name}, Args: {arguments}")
    logging.warning(f">>> [MCP SERVER DEBUG] Trace Headers: {headers}")
    
    auth_header = mcp_auth_header_var.get(None)
    if auth_header:
        headers["Authorization"] = auth_header
    
    async with httpx.AsyncClient(follow_redirects=True, headers=headers) as client:
        try:
            if name == "list_users":
                skip = arguments.get("skip", 0)
                limit = arguments.get("limit", 10)
                response = await client.get(f"{API_BASE_URL}/", params={"skip": skip, "limit": limit})
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "get_user":
                response = await client.get(f"{API_BASE_URL}/{arguments['user_id']}/")
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "get_users_bulk":
                user_ids = arguments.get("user_ids", [])
                if not user_ids:
                    return [TextContent(type="text", text="[]")]
                response = await client.post(f"{API_BASE_URL}/bulk", json=user_ids)
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "create_user":
                response = await client.post(f"{API_BASE_URL}/", json={
                    "username": arguments["username"],
                    "email": arguments["email"],
                    "full_name": arguments.get("full_name"),
                    "is_anonymous": arguments.get("is_anonymous", False)
                })
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "update_user":
                data = {k: v for k, v in arguments.items() if k != "user_id" and v is not None}
                response = await client.put(f"{API_BASE_URL}/{arguments['user_id']}", json=data)
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "delete_user":
                response = await client.delete(f"{API_BASE_URL}/{arguments['user_id']}")
                response.raise_for_status()
                return [TextContent(type="text", text="User deleted successfully")]

            elif name == "health_check":
                response = await client.get(f"{API_BASE_URL}/health")
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "search_users":
                query = arguments.get("query", "")
                limit = arguments.get("limit", 10)
                response = await client.get(f"{API_BASE_URL}/search", params={"query": query, "limit": limit})
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "toggle_user_status":
                user_id = arguments["user_id"]
                is_active = arguments["is_active"]
                response = await client.put(f"{API_BASE_URL}/{user_id}", json={"is_active": is_active})
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "get_user_stats":
                response = await client.get(f"{API_BASE_URL}/stats")
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "get_user_duplicates":
                response = await client.get(f"{API_BASE_URL}/duplicates")
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "merge_users":
                source_id = arguments["source_id"]
                target_id = arguments["target_id"]
                response = await client.post(f"{API_BASE_URL}/merge", json={"source_id": source_id, "target_id": target_id})
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "search_anonymous_users":
                limit = arguments.get("limit", 10)
                response = await client.get(f"{API_BASE_URL}/search", params={"is_anonymous": True, "limit": limit})
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 409:
                return [TextContent(type="text", text=f"CONFLIT (409) : {e.response.text}. Ne PAS réessayer l'outil avec les mêmes paramètres.")]
            return [TextContent(type="text", text=f"HTTP Error: {e.response.status_code} - {e.response.text}")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error: {str(e)}")]


async def main():
    """Main entry point for the MCP server when run as a script."""
    from mcp.server.stdio import stdio_server
    options = InitializationOptions(
        server_name="users-api",
        server_version="1.0.0",
        capabilities={}
    )
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options)


if __name__ == "__main__":
    asyncio.run(main())
