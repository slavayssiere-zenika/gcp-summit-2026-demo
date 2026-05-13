import asyncio
import contextvars
import json
import logging
import os

import httpx
from mcp.server import InitializationOptions, Server
from mcp.types import TextContent, Tool
from opentelemetry import propagate, trace
from opentelemetry.propagate import inject
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.trace.propagation.tracecontext import \
    TraceContextTextMapPropagator

from tools.categories import get_categories_tools, handle_categories_tool
from tools.items import get_items_tools, handle_items_tool

mcp_auth_header_var = contextvars.ContextVar("mcp_auth_header", default=None)

if os.getenv("TRACE_EXPORTER", "grpc") == "http":
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import \
        OTLPSpanExporter
elif os.getenv("TRACE_EXPORTER", "grpc") == "gcp":
    from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
else:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import \
        OTLPSpanExporter

propagate.set_global_textmap(TraceContextTextMapPropagator())

logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s', handlers=[logging.NullHandler()])

API_BASE_URL = os.getenv("ITEMS_API_URL", "http://localhost:8001")
USERS_API_URL = os.getenv("USERS_API_URL", "http://localhost:8000")

sampling_rate = float(os.getenv("TRACE_SAMPLING_RATE", "1.0"))
sampler = ParentBased(root=TraceIdRatioBased(sampling_rate))
provider = TracerProvider(
    resource=Resource.create({
        ResourceAttributes.SERVICE_NAME: "items-api-mcp",
        ResourceAttributes.SERVICE_VERSION: os.getenv("APP_VERSION", "dev"),
    }),
    sampler=sampler
)
if os.getenv("TRACE_EXPORTER", "grpc") == "gcp":
    provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))
else:
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter() if os.getenv(
                "TRACE_EXPORTER",
                "grpc") == "http" else OTLPSpanExporter(
                insecure=True)))
trace.set_tracer_provider(provider)

tracer = trace.get_tracer(__name__)

server = Server("items-api")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return get_categories_tools() + get_items_tools()


def get_trace_headers() -> dict:
    headers = {}
    inject(headers)
    return headers


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    headers = get_trace_headers()
    auth = mcp_auth_header_var.get(None)
    if auth:
        headers["Authorization"] = auth

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
