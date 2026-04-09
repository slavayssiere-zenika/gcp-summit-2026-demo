import asyncio
import json
import os
import contextvars
from mcp.server import Server
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
from opentelemetry.propagate import inject
import httpx

mcp_auth_header_var = contextvars.ContextVar("mcp_auth_header", default=None)
propagate.set_global_textmap(TraceContextTextMapPropagator())

API_BASE_URL = os.getenv("DRIVE_API_URL", "http://localhost:8006")

provider = TracerProvider(
    resource=Resource.create({
        ResourceAttributes.SERVICE_NAME: "drive-api-mcp",
        ResourceAttributes.SERVICE_VERSION: "1.0.0",
    })
)
if os.getenv("TRACE_EXPORTER", "grpc") == "gcp":
    provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))
else:
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter() if os.getenv("TRACE_EXPORTER", "grpc") == "http" else OTLPSpanExporter(insecure=True)))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(__name__)

server = Server("drive-api")

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="add_drive_folder",
            description="Add a new Google Drive folder to be tracked for CV ingestion. Requires a folder ID and a business tag.",
            inputSchema={
                "type": "object",
                "properties": {
                    "google_folder_id": {
                        "type": "string",
                        "description": "The unique Google Drive Folder ID"
                    },
                    "tag": {
                        "type": "string",
                        "description": "The logical business tag to apply to all CVs found in this folder (e.g. 'Paris', 'Nantes', 'Data')"
                    }
                },
                "required": ["google_folder_id", "tag"]
            }
        ),
        Tool(
            name="list_drive_folders",
            description="Retrieve the list of all Google Drive folders currently tracked by the system.",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="delete_drive_folder",
            description="Stop tracking a specific Google Drive folder. Requires its internal ID (not the Google ID).",
            inputSchema={
                "type": "object",
                "properties": {
                    "folder_id": {
                        "type": "integer",
                        "description": "The internal database ID of the Drive folder"
                    }
                },
                "required": ["folder_id"]
            }
        ),
        Tool(
            name="get_drive_status",
            description="View the global synchronization and ingestion stats of the Google Drive integration.",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="list_drive_files",
            description="List all tracked files across all synced Google Drive folders, ordered by most recent first.",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="retry_drive_errors",
            description="Flip all files stuck in ERROR state back to PENDING so the next batch ingestion will retry processing them.",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="trigger_drive_sync",
            description="Manually trigger a deep sync delta discovery across all tracked Drive folders to find new or updated CVs.",
            inputSchema={"type": "object", "properties": {}}
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    with tracer.start_as_current_span(f"mcp.tool.{name}") as span:
        auth_header = mcp_auth_header_var.get()
        headers = {}
        if auth_header:
            headers["Authorization"] = auth_header
        # OTel Propagation
        inject(headers)

        async with httpx.AsyncClient() as client:
            try:
                if name == "add_drive_folder":
                    res = await client.post(f"{API_BASE_URL}/folders", json=arguments, headers=headers, timeout=10.0)
                    res.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(res.json(), indent=2))]
                    
                elif name == "list_drive_folders":
                    res = await client.get(f"{API_BASE_URL}/folders", headers=headers, timeout=10.0)
                    res.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(res.json(), indent=2))]
                    
                elif name == "delete_drive_folder":
                    fid = arguments.get("folder_id")
                    res = await client.delete(f"{API_BASE_URL}/folders/{fid}", headers=headers, timeout=10.0)
                    res.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(res.json(), indent=2))]
                    
                elif name == "get_drive_status":
                    res = await client.get(f"{API_BASE_URL}/status", headers=headers, timeout=10.0)
                    res.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(res.json(), indent=2))]
                    
                elif name == "list_drive_files":
                    res = await client.get(f"{API_BASE_URL}/files", headers=headers, timeout=10.0)
                    res.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(res.json(), indent=2))]
                    
                elif name == "retry_drive_errors":
                    res = await client.post(f"{API_BASE_URL}/retry-errors", headers=headers, timeout=10.0)
                    res.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(res.json(), indent=2))]
                    
                elif name == "trigger_drive_sync":
                    # This endpoint might take longer to return (Cloud Run default limit 60 min, but HTTP is standard)
                    res = await client.post(f"{API_BASE_URL}/sync", headers=headers, timeout=300.0)
                    res.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(res.json(), indent=2))]
                    
                else:
                    return [TextContent(type="text", text=f"Unknown tool: {name}")]
            except httpx.HTTPStatusError as e:
                return [TextContent(type="text", text=f"API Error {e.response.status_code}: {e.response.text}")]
            except Exception as e:
                return [TextContent(type="text", text=f"Request failed: {str(e)}")]
