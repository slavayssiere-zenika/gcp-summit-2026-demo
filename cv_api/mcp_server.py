import asyncio
import json
import os
import contextvars
import httpx
from mcp.server import Server
from mcp.types import Tool, TextContent
from opentelemetry import trace, propagate
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.propagate import inject

mcp_auth_header_var = contextvars.ContextVar("mcp_auth_header", default=None)
propagate.set_global_textmap(TraceContextTextMapPropagator())

API_BASE_URL = os.getenv("CV_API_URL", "http://localhost:8004")

provider = TracerProvider(
    resource=Resource.create({
        ResourceAttributes.SERVICE_NAME: "cv-api-mcp",
        ResourceAttributes.SERVICE_VERSION: "1.0.0",
    })
)
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(insecure=True)))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(__name__)

server = Server("cv-api")

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="analyze_cv",
            description="Download, parse, extract, and convert a CV into the Zenika platform recursively importing the candidate's skills and their matrix. Only call this when providing a public Google Docs Link.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL of the candidate's CV. Must be a Google Document link."
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="search_best_candidates",
            description="Find the best ranked candidates for a specific project format, role, or technical context by semantically matching their CVs against an embedded vector spatial graph. Only Returns user IDs.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language query describing the desired consultant (e.g. 'Expert in Kubernetes and GKE with devops skills')"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of top candidates to return. Default is 5."
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="recalculate_competencies_tree",
            description="Recalcule totalement l'arbre des compétences (Taxonomie globale) en lisant tous les CVs de la base avec Gemini. Cette commande prend plusieurs secondes et ne reconstruit qu'un JSON brut.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
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
            if name == "analyze_cv":
                url = arguments.get("url")
                if not url:
                    return [TextContent(type="text", text="Error: Missing url argument.")]
                
                try:
                    response = await client.post(f"{API_BASE_URL}/cvs/import", json={"url": url}, headers=headers, timeout=60.0)
                    response.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
                except httpx.HTTPStatusError as e:
                    return [TextContent(type="text", text=f"API Error {e.response.status_code}: {e.response.text}")]
                except Exception as e:
                    return [TextContent(type="text", text=f"Request failed: {str(e)}")]
            elif name == "search_best_candidates":
                query = arguments.get("query")
                limit = arguments.get("limit", 5)
                if not query:
                    return [TextContent(type="text", text="Error: Missing query argument.")]
                
                try:
                    response = await client.get(f"{API_BASE_URL}/cvs/search", params={"query": query, "limit": limit}, headers=headers, timeout=60.0)
                    response.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
                except httpx.HTTPStatusError as e:
                    return [TextContent(type="text", text=f"API Error {e.response.status_code}: {e.response.text}")]
                except Exception as e:
                    return [TextContent(type="text", text=f"Request failed: {str(e)}")]
            elif name == "recalculate_competencies_tree":
                try:
                    response = await client.post(f"{API_BASE_URL}/cvs/recalculate_tree", headers=headers, timeout=120.0)
                    response.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
                except httpx.HTTPStatusError as e:
                    return [TextContent(type="text", text=f"API Error {e.response.status_code}: {e.response.text}")]
                except Exception as e:
                    return [TextContent(type="text", text=f"Request failed: {str(e)}")]
            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]
