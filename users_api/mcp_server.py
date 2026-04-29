import asyncio
import os
import logging
import contextvars
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.server import InitializationOptions
from mcp.types import Tool, TextContent
from opentelemetry import trace, propagate
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.propagate import inject
import httpx

if os.getenv("TRACE_EXPORTER", "grpc") == "http":
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
elif os.getenv("TRACE_EXPORTER", "grpc") == "gcp":
    from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
else:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# Importer les outils refactorisés
from src.mcp_tools.tools_registry import get_mcp_tools
from src.mcp_tools.tools_handlers import handle_tool_call

mcp_auth_header_var = contextvars.ContextVar("mcp_auth_header", default=None)

propagate.set_global_textmap(TraceContextTextMapPropagator())
logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s', handlers=[logging.NullHandler()])

sampling_rate = float(os.getenv("TRACE_SAMPLING_RATE", "1.0"))
sampler = ParentBased(root=TraceIdRatioBased(sampling_rate))
provider = TracerProvider(
    resource=Resource.create({
        ResourceAttributes.SERVICE_NAME: "users-api-mcp",
        ResourceAttributes.SERVICE_VERSION: "1.0.0",
    }),
    sampler=sampler
)

if os.getenv("TRACE_EXPORTER", "grpc") == "gcp":
    provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))
else:
    provider.add_span_processor(BatchSpanProcessor(
        OTLPSpanExporter() if os.getenv("TRACE_EXPORTER", "grpc") == "http" else OTLPSpanExporter(insecure=True)
    ))
trace.set_tracer_provider(provider)

tracer = trace.get_tracer(__name__)
server = Server("users-api")

@server.list_tools()
async def list_tools() -> list[Tool]:
    return get_mcp_tools()

def get_trace_headers() -> dict:
    headers = {}
    inject(headers)
    return headers

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
