import asyncio
import json
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
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.propagate import inject
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
import httpx

if os.getenv("TRACE_EXPORTER", "grpc") == "http":
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
elif os.getenv("TRACE_EXPORTER", "grpc") == "gcp":
    from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
else:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

propagate.set_global_textmap(TraceContextTextMapPropagator())

logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s', handlers=[logging.NullHandler()])

API_BASE_URL = os.getenv("PROMPTS_API_URL", "http://prompts_api:8000")

provider = TracerProvider(
    resource=Resource.create({
        ResourceAttributes.SERVICE_NAME: "prompts-api-mcp",
        ResourceAttributes.SERVICE_VERSION: "1.0.0",
    })
)
if os.getenv("TRACE_EXPORTER", "grpc") == "gcp":
    provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))
else:
    provider.add_span_processor(BatchSpanProcessor(
        OTLPSpanExporter() if os.getenv("TRACE_EXPORTER", "grpc") == "http" else OTLPSpanExporter(insecure=True)
    ))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(__name__)

server = Server("prompts-api")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="list_prompts",
            description=(
                "Liste tous les system prompts disponibles dans la base Zenika (admin uniquement). "
                "Chaque prompt est identifié par une clé unique (ex: 'agent_hr', 'agent_ops', 'agent_router'). "
                "Utiliser cet outil pour auditer ou consulter l'ensemble des prompts configurés."
            ),
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="get_prompt",
            description=(
                "Récupère le contenu d'un system prompt par sa clé unique. "
                "Les clés correspondent aux identifiants des agents (ex: 'agent_hr', 'agent_ops', 'agent_router', 'agent_missions'). "
                "Utiliser cet outil pour lire le prompt actif d'un agent spécifique."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Clé unique du prompt (ex: 'agent_hr', 'agent_ops')"}
                },
                "required": ["key"]
            }
        ),
        Tool(
            name="get_my_prompt",
            description=(
                "Récupère le system prompt personnalisé de l'utilisateur courant (identifié par le JWT). "
                "Retourne le prompt associé au compte connecté."
            ),
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="create_prompt",
            description=(
                "Crée un nouveau system prompt ou met à jour un prompt existant avec la même clé (upsert). "
                "Action réservée aux administrateurs. "
                "ATTENTION : La modification d'un prompt actif affecte immédiatement le comportement de l'agent concerné."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Clé unique du prompt"},
                    "value": {"type": "string", "description": "Contenu du system prompt"}
                },
                "required": ["key", "value"]
            }
        ),
        Tool(
            name="update_prompt",
            description=(
                "Met à jour le contenu d'un system prompt existant par sa clé. "
                "Action réservée aux administrateurs. "
                "Le cache Redis associé est automatiquement invalidé."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Clé unique du prompt à mettre à jour"},
                    "value": {"type": "string", "description": "Nouveau contenu du system prompt"}
                },
                "required": ["key", "value"]
            }
        ),
        Tool(
            name="update_my_prompt",
            description=(
                "Met à jour le system prompt personnalisé de l'utilisateur courant. "
                "Chaque utilisateur peut avoir son propre prompt pour personnaliser le comportement de l'agent."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "value": {"type": "string", "description": "Nouveau contenu du system prompt personnel"}
                },
                "required": ["value"]
            }
        ),
        Tool(
            name="analyze_prompt",
            description=(
                "Lance une analyse automatisée d'un prompt par sa clé avec Promptfoo et Gemini : "
                "génération de cas de test, évaluation des réponses, et proposition d'un prompt amélioré. "
                "Action réservée aux administrateurs. Opération longue (~30s)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Clé du prompt à analyser et améliorer"}
                },
                "required": ["key"]
            }
        ),
        Tool(
            name="health_check_prompts",
            description="Vérifie que l'API Prompts est opérationnelle et accessible.",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="report_service_error_for_prompt",
            description=(
                "Remonte une erreur d'exécution captée par un service ou un agent pour qu'elle soit "
                "transformée par le LLM (prompts_api) en une règle directive de prompt."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "service_name": {"type": "string", "description": "Nom du service source de l'erreur"},
                    "error_message": {"type": "string", "description": "Message brut de l'erreur"},
                    "context": {"type": "string", "description": "Contexte optionnel ou trace technique"}
                },
                "required": ["service_name", "error_message"]
            }
        ),
    ]


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

    async with httpx.AsyncClient(follow_redirects=True, headers=headers, timeout=120.0) as client:
        try:
            if name == "list_prompts":
                response = await client.get(f"{API_BASE_URL}/prompts/")
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "get_prompt":
                key = arguments["key"]
                response = await client.get(f"{API_BASE_URL}/prompts/{key}")
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "get_my_prompt":
                response = await client.get(f"{API_BASE_URL}/prompts/user/me")
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "create_prompt":
                payload = {"key": arguments["key"], "value": arguments["value"]}
                response = await client.post(f"{API_BASE_URL}/prompts/", json=payload)
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "update_prompt":
                key = arguments["key"]
                payload = {"value": arguments["value"]}
                response = await client.put(f"{API_BASE_URL}/prompts/{key}", json=payload)
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "update_my_prompt":
                payload = {"value": arguments["value"]}
                response = await client.put(f"{API_BASE_URL}/prompts/user/me", json=payload)
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "analyze_prompt":
                key = arguments["key"]
                response = await client.post(f"{API_BASE_URL}/prompts/{key}/analyze")
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "health_check_prompts":
                response = await client.get(f"{API_BASE_URL}/health")
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "report_service_error_for_prompt":
                payload = {
                    "service_name": arguments["service_name"],
                    "error_message": arguments["error_message"],
                    "context": arguments.get("context", "")
                }
                response = await client.post(f"{API_BASE_URL}/errors/report", json=payload)
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            else:
                return [TextContent(type="text", text=json.dumps({"success": False, "error": f"Unknown tool: {name}"}))]

        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=json.dumps({"success": False, "error": f"HTTP {e.response.status_code}: {e.response.text}"}))]
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]


async def main():
    """Main entry point for the MCP server when run as a script."""
    options = InitializationOptions(
        server_name="prompts-api",
        server_version="1.0.0",
        capabilities={}
    )
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options)


if __name__ == "__main__":
    asyncio.run(main())
