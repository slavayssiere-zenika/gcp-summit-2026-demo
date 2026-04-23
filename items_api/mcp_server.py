import asyncio
import json
import threading
import os
import logging
import contextvars

mcp_auth_header_var = contextvars.ContextVar("mcp_auth_header", default=None)

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.server import InitializationOptions, NotificationOptions
from mcp.types import Tool, TextContent
from opentelemetry import trace, propagate
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

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

API_BASE_URL = os.getenv("ITEMS_API_URL", "http://localhost:8001")
USERS_API_URL = os.getenv("USERS_API_URL", "http://localhost:8000")

sampling_rate = float(os.getenv("TRACE_SAMPLING_RATE", "1.0"))
sampler = ParentBased(root=TraceIdRatioBased(sampling_rate))
provider = TracerProvider(
    resource=Resource.create({
        ResourceAttributes.SERVICE_NAME: "items-api-mcp",
        ResourceAttributes.SERVICE_VERSION: "1.0.0",
    })
,
    sampler=sampler
)
if os.getenv("TRACE_EXPORTER", "grpc") == "gcp":
    provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))
else:
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter() if os.getenv("TRACE_EXPORTER", "grpc") == "http" else OTLPSpanExporter(insecure=True)))
trace.set_tracer_provider(provider)

tracer = trace.get_tracer(__name__)

server = Server("items-api")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="list_items",
            description="List all items with pagination",
            inputSchema={
                "type": "object",
                "properties": {
                    "skip": {"type": "integer", "description": "Number of items to skip", "default": 0},
                    "limit": {"type": "integer", "description": "Maximum number of items to return", "default": 10}
                }
            }
        ),
        Tool(
            name="list_categories",
            description="List all item categories",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="create_category",
            description="Create a new item category",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Category name"},
                    "description": {"type": "string", "description": "Category description (optional)"}
                },
                "required": ["name"]
            }
        ),
        Tool(
            name="get_item",
            description="Get an item by ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "item_id": {"type": "integer", "description": "The item ID"}
                },
                "required": ["item_id"]
            }
        ),
        Tool(
            name="create_item",
            description="Create a new item (requires valid user_id)",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Item name"},
                    "description": {"type": "string", "description": "Item description (optional)"},
                    "user_id": {"type": "integer", "description": "ID of the user who owns this item"},
                    "category_ids": {"type": "array", "items": {"type": "integer"}, "description": "List of category IDs"},
                    "metadata_json": {"type": "object", "description": "Rich metadata (JSONB) for missions, etc."}
                },
                "required": ["name", "user_id", "category_ids"]
            }
        ),
        Tool(
            name="get_item_with_user",
            description="Get an item with user information",
            inputSchema={
                "type": "object",
                "properties": {
                    "item_id": {"type": "integer", "description": "The item ID"}
                },
                "required": ["item_id"]
            }
        ),
        Tool(
            name="health_check",
            description="Check if the API is healthy",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="update_item",
            description="Update an existing item",
            inputSchema={
                "type": "object",
                "properties": {
                    "item_id": {"type": "integer", "description": "The item ID"},
                    "name": {"type": "string", "description": "New name (optional)"},
                    "description": {"type": "string", "description": "New description (optional)"},
                    "category_ids": {"type": "array", "items": {"type": "integer"}, "description": "New category IDs (optional)"},
                    "metadata_json": {"type": "object", "description": "New metadata (optional)"}
                },
                "required": ["item_id"]
            }
        ),
        Tool(
            name="delete_item",
            description="Delete an item",
            inputSchema={
                "type": "object",
                "properties": {
                    "item_id": {"type": "integer", "description": "The item ID"}
                },
                "required": ["item_id"]
            }
        ),
        Tool(
            name="search_items",
            description="Search items by name or description",
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
            name="get_items_by_user",
            description="Get all items for a specific user",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "The user ID"}
                },
                "required": ["user_id"]
            }
        ),
        Tool(
            name="get_item_stats",
            description="Get statistics about items",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="bulk_create_items",
            description=(
                "Crée plusieurs items en une seule requête (bulk). "
                "Très performant pour l'ingestion de CVs (création de profils consultants en masse). "
                "Chaque item doit avoir un nom, un user_id et au moins une catégorie. "
                "Idémpotent : les items existants sont mis à jour plutôt que dupliqués."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "description": "Liste des items à créer",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "Nom de l'item"},
                                "description": {"type": "string", "description": "Description (optionnel)"},
                                "user_id": {"type": "integer", "description": "ID de l'utilisateur propriétaire"},
                                "category_ids": {"type": "array", "items": {"type": "integer"}, "description": "IDs des catégories"},
                                "metadata_json": {"type": "object", "description": "Métadonnées riches (JSONB)"}
                            },
                            "required": ["name", "user_id", "category_ids"]
                        }
                    }
                },
                "required": ["items"]
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
    auth = mcp_auth_header_var.get(None)
    if auth:
        headers["Authorization"] = auth
    async with httpx.AsyncClient(follow_redirects=True, headers=headers) as client:
        try:
            if name == "list_items":
                skip = arguments.get("skip", 0)
                limit = arguments.get("limit", 10)
                response = await client.get(f"{API_BASE_URL}/", params={"skip": skip, "limit": limit})
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "get_item":
                response = await client.get(f"{API_BASE_URL}/{arguments['item_id']}/")
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "create_item":
                payload = {
                    "name": arguments["name"],
                    "description": arguments.get("description"),
                    "user_id": arguments["user_id"],
                    "category_ids": arguments.get("category_ids", []),
                    "metadata_json": arguments.get("metadata_json")
                }
                response = await client.post(f"{API_BASE_URL}/", json=payload)
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "get_item_with_user":
                item_response = await client.get(f"{API_BASE_URL}/{arguments['item_id']}/")
                item_response.raise_for_status()
                item_data = item_response.json()

                user_response = await client.get(f"{USERS_API_URL.rstrip('/')}/{item_data.get('user_id')}")
                if user_response.status_code == 200:
                    item_data["user"] = user_response.json()

                return [TextContent(type="text", text=json.dumps(item_data))]

            elif name == "health_check":
                response = await client.get(f"{API_BASE_URL}/health")
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "update_item":
                item_id = arguments["item_id"]
                data = {k: v for k, v in arguments.items() if k not in ["item_id"] and v is not None}
                response = await client.put(f"{API_BASE_URL}/{item_id}", json=data)
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "delete_item":
                item_id = arguments["item_id"]
                response = await client.delete(f"{API_BASE_URL}/{item_id}")
                response.raise_for_status()
                return [TextContent(type="text", text="Item deleted successfully")]

            elif name == "search_items":
                query = arguments.get("query", "")
                limit = arguments.get("limit", 10)
                response = await client.get(f"{API_BASE_URL}/search/query", params={"query": query, "limit": limit})
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "list_categories":
                response = await client.get(f"{API_BASE_URL}/categories")
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "create_category":
                response = await client.post(f"{API_BASE_URL}/categories", json={
                    "name": arguments["name"],
                    "description": arguments.get("description")
                })
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "get_items_by_user":
                # Robust type conversion as LLMs might pass string IDs
                try:
                    user_id = int(arguments["user_id"])
                except Exception as e:
                    return [TextContent(type="text", text=f"Error: user_id must be an integer, got {arguments.get('user_id')}")]
                
                # Use the new dedicated endpoint for better performance and reliability
                response = await client.get(f"{API_BASE_URL}/user/{user_id}", params={"skip": 0, "limit": 100})
                response.raise_for_status()
                data = response.json()
                
                return [TextContent(type="text", text=json.dumps(data))]

            elif name == "get_item_stats":
                response = await client.get(f"{API_BASE_URL}/stats")
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "bulk_create_items":
                items_payload = arguments.get("items", [])
                if not items_payload:
                    return [TextContent(type="text", text=json.dumps({"success": False, "error": "Paramètre 'items' manquant ou vide."}))]
                response = await client.post(f"{API_BASE_URL}/bulk", json=items_payload, timeout=60.0)
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 409:
                return [TextContent(type="text", text=f"CONFLIT (409) : {e.response.text}. Ne PAS réessayer l'outil avec les mêmes paramètres.")]
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
