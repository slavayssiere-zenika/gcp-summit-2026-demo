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
if os.getenv("TRACE_EXPORTER", "grpc") == "http":
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
elif os.getenv("TRACE_EXPORTER", "grpc") == "gcp":
    from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
else:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.propagate import inject

mcp_auth_header_var = contextvars.ContextVar("mcp_auth_header", default=None)
propagate.set_global_textmap(TraceContextTextMapPropagator())

API_BASE_URL = os.getenv("MISSIONS_API_URL", "http://localhost:8009")

provider = TracerProvider(
    resource=Resource.create({
        ResourceAttributes.SERVICE_NAME: "missions-api-mcp",
        ResourceAttributes.SERVICE_VERSION: "1.0.0",
    })
)
if os.getenv("TRACE_EXPORTER", "grpc") == "gcp":
    provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))
else:
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter() if os.getenv("TRACE_EXPORTER", "grpc") == "http" else OTLPSpanExporter(insecure=True)))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(__name__)

server = Server("missions-api")

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="create_mission",
            description="Créer et enregistrer une nouvelle fiche de mission",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": { "type": "string" },
                    "description": { "type": "string" }
                },
                "required": ["title", "description"]
            }
        ),
        Tool(
            name="list_missions",
            description="Récupère toutes les missions enregistrées.",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="reanalyze_mission",
            description="Relancer l'analyse complète (RAG et Staffing) d'une mission existante. Utile pour proposer une nouvelle équipe.",
            inputSchema={
                "type": "object",
                "properties": {
                    "mission_id": { "type": "integer" }
                },
                "required": ["mission_id"]
            }
        ),
        Tool(
            name="get_mission",
            description="Récupère le détail complet d'une mission par son ID : titre, description, statut, compétences requises et consultants staffés. Appeler après list_missions pour obtenir un mission_id.",
            inputSchema={
                "type": "object",
                "properties": {
                    "mission_id": { "type": "integer", "description": "L'ID de la mission" }
                },
                "required": ["mission_id"]
            }
        ),
        Tool(
            name="get_mission_candidates",
            description="Retourne la liste des consultants actuellement staffés sur une mission donnée, avec leurs IDs utilisateurs. Utiliser pour répondre à 'Qui est staffé sur la mission X ?'",
            inputSchema={
                "type": "object",
                "properties": {
                    "mission_id": { "type": "integer", "description": "L'ID de la mission" }
                },
                "required": ["mission_id"]
            }
        ),
        Tool(
            name="update_mission_status",
            description=(
                "Modifie le statut d'une mission. "
                "Réservé aux rôles commercial et admin. "
                "Transitions autorisées : "
                "STAFFED→NO_GO, STAFFED→SUBMITTED_TO_CLIENT, STAFFED→CANCELLED, "
                "SUBMITTED_TO_CLIENT→WON, SUBMITTED_TO_CLIENT→LOST, SUBMITTED_TO_CLIENT→CANCELLED. "
                "Utiliser quand l'utilisateur dit 'marquer la mission X comme No-Go', 'on a gagné l\'appel d\'offres Y', 'envoyer la proposition au client', etc. "
                "Toujours préciser un reason (motif) pour l'audit."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "mission_id": { "type": "integer", "description": "L'ID de la mission à mettre à jour" },
                    "status": {
                        "type": "string",
                        "enum": ["NO_GO", "SUBMITTED_TO_CLIENT", "WON", "LOST", "CANCELLED"],
                        "description": "Le nouveau statut à appliquer"
                    },
                    "reason": { "type": "string", "description": "Motif du changement de statut (obligatoire pour l'audit)" }
                },
                "required": ["mission_id", "status"]
            }
        ),
        Tool(
            name="get_mission_status_history",
            description="Retourne l'historique complet des changements de statut d'une mission (audit trail). Utiliser pour répondre à 'quel est l\'historique de la mission X ?', 'qui a changé le statut ?' etc.",
            inputSchema={
                "type": "object",
                "properties": {
                    "mission_id": { "type": "integer", "description": "L'ID de la mission" }
                },
                "required": ["mission_id"]
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
        inject(headers)

        async with httpx.AsyncClient() as client:
            if name == "create_mission":
                payload = {
                    "title": arguments.get("title"),
                    "description": arguments.get("description")
                }
                try:
                    response = await client.post(f"{API_BASE_URL}/missions", json=payload, headers=headers, timeout=60.0)
                    response.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
                except Exception as e:
                    return [TextContent(type="text", text=f"Request failed: {str(e)}")]
            elif name == "list_missions":
                try:
                    response = await client.get(f"{API_BASE_URL}/missions", headers=headers, timeout=20.0)
                    response.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
                except Exception as e:
                    return [TextContent(type="text", text=f"Request failed: {str(e)}")]
            elif name == "reanalyze_mission":
                mission_id = arguments.get("mission_id")
                try:
                    response = await client.post(f"{API_BASE_URL}/missions/{mission_id}/reanalyze", headers=headers, timeout=60.0)
                    response.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
                except Exception as e:
                    return [TextContent(type="text", text=f"Request failed: {str(e)}")]
            elif name == "get_mission":
                mission_id = arguments.get("mission_id")
                try:
                    response = await client.get(f"{API_BASE_URL}/missions/{mission_id}", headers=headers, timeout=20.0)
                    response.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
                except Exception as e:
                    return [TextContent(type="text", text=f"Request failed: {str(e)}")]
            elif name == "get_mission_candidates":
                mission_id = arguments.get("mission_id")
                try:
                    response = await client.get(f"{API_BASE_URL}/missions/{mission_id}/candidates", headers=headers, timeout=20.0)
                    response.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
                except Exception as e:
                    return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]
            elif name == "update_mission_status":
                mission_id = arguments.get("mission_id")
                new_status = arguments.get("status")
                reason = arguments.get("reason")
                try:
                    response = await client.patch(
                        f"{API_BASE_URL}/missions/{mission_id}/status",
                        json={"status": new_status, "reason": reason},
                        headers=headers,
                        timeout=20.0,
                    )
                    response.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
                except Exception as e:
                    return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]
            elif name == "get_mission_status_history":
                mission_id = arguments.get("mission_id")
                try:
                    response = await client.get(f"{API_BASE_URL}/missions/{mission_id}/status/history", headers=headers, timeout=20.0)
                    response.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
                except Exception as e:
                    return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]
            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]

async def main():
    from mcp.server.stdio import stdio_server
    from mcp.server import InitializationOptions
    options = InitializationOptions(
        server_name="missions-api",
        server_version="1.0.0",
        capabilities={}
    )
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options)

if __name__ == "__main__":
    asyncio.run(main())
