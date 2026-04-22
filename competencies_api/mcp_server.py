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

API_BASE_URL = os.getenv("COMPETENCIES_API_URL", "http://localhost:8003")

provider = TracerProvider(
    resource=Resource.create({
        ResourceAttributes.SERVICE_NAME: "competencies-api-mcp",
        ResourceAttributes.SERVICE_VERSION: "1.0.0",
    })
)
if os.getenv("TRACE_EXPORTER", "grpc") == "gcp":
    provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))
else:
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter() if os.getenv("TRACE_EXPORTER", "grpc") == "http" else OTLPSpanExporter(insecure=True)))
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
            name="search_competencies",
            description=(
                "Search for competencies by name or alias in the competency tree. "
                "IMPORTANT: Use specific terms of at least 3 characters (e.g. 'AWS', 'React', 'Python', 'Data Engineering'). "
                "DO NOT use single letters like 'C', 'R', 'J' as they match every competency containing that letter and return useless results. "
                "For the 'C language' or 'C programming', search for 'langage C' or 'C language' or 'systems programming'. "
                "For semantic/staffing searches, prefer search_best_candidates (cv_api) instead."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search term (minimum 3 meaningful characters). Examples: 'AWS', 'Kubernetes', 'React', 'Data Engineering'"},
                    "limit": {"type": "integer", "description": "Maximum number of results to return", "default": 10}
                },
                "required": ["query"]
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
            name="update_competency",
            description="Update an existing competency",
            inputSchema={
                "type": "object",
                "properties": {
                    "competency_id": {"type": "integer", "description": "The competency ID"},
                    "name": {"type": "string", "description": "New name (optional)"},
                    "description": {"type": "string", "description": "New description (optional)"},
                    "parent_id": {"type": "integer", "description": "New parent ID (optional)"}
                },
                "required": ["competency_id"]
            }
        ),
        Tool(
            name="bulk_import_tree",
            description="Bulk import a taxonomy tree (Admin only)",
            inputSchema={
                "type": "object",
                "properties": {
                    "tree": {
                        "type": "object",
                        "description": "Hierarchical dictionary of competencies"
                    }
                },
                "required": ["tree"]
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
        ),
        Tool(
            name="list_competency_users",
            description="Get a list of user IDs that possess a specific competency",
            inputSchema={
                "type": "object",
                "properties": {
                    "competency_id": {"type": "integer", "description": "The competency ID"}
                },
                "required": ["competency_id"]
            }
        ),
        Tool(
            name="clear_user_competencies",
            description="(Admin Only) Supprime toutes les assignations de compétences pour un utilisateur spécifique.",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "L'ID de l'utilisateur"}
                },
                "required": ["user_id"]
            }
        ),
        Tool(
            name="get_competency_stats",
            description="Get analytics on competency distribution. Can identify rarest/most common and filter by a specific cohort of users (e.g. from an agency).",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Optional list of user IDs to filter by (e.g. collected via get_users_by_tag in cv_api)."
                    },
                    "limit": {"type": "integer", "description": "Number of results", "default": 10},
                    "sort_order": {"type": "string", "enum": ["asc", "desc"], "default": "desc", "description": "Use 'asc' for rarest, 'desc' for most common."}
                }
            }
        ),
        Tool(
            name="get_user_competency_evaluations",
            description=(
                "Recupere toutes les evaluations de competences feuilles pour un consultant. "
                "Chaque evaluation contient : la note IA (ai_score, calculee par Gemini depuis ses missions reelles), "
                "la justification textuelle de cette note, et la note auto-evaluee par le consultant (user_score). "
                "Utilise cet outil pour analyser le niveau reel d'un consultant, identifier les gaps, "
                "ou declencher un coaching CV personnalise."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "L'ID du consultant"}
                },
                "required": ["user_id"]
            }
        ),
        Tool(
            name="set_user_competency_score",
            description=(
                "Enregistre la note auto-evaluee (user_score) d'un consultant pour une competence specifique. "
                "La note doit etre entre 0 et 5. Un commentaire optionnel peut accompagner la note. "
                "Cette note est distincte de la note IA (ai_score) calculee depuis les missions du CV."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "L'ID du consultant"},
                    "competency_id": {"type": "integer", "description": "L'ID de la competence feuille"},
                    "score": {"type": "number", "minimum": 0, "maximum": 5, "description": "Note de 0 a 5 (par pas de 0.5 recommandes)"},
                    "comment": {"type": "string", "description": "Commentaire optionnel justifiant la note (max 500 chars)"}
                },
                "required": ["user_id", "competency_id", "score"]
            }
        ),
        Tool(
            name="trigger_ai_scoring",
            description=(
                "Declenche le calcul IA des notes pour TOUTES les competences feuilles assignees a un consultant. "
                "Gemini analyse les missions du CV et attribue un score (0-5) avec justification pour chaque competence. "
                "Le traitement est asynchrone (BackgroundTask). Utilise cet outil apres une reanalyse de CV "
                "ou quand le consultant demande a connaitre son niveau objectif."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "L'ID du consultant"}
                },
                "required": ["user_id"]
            }
        ),
        Tool(
            name="get_agency_competency_coverage",
            description=(
                "Heatmap des compétences par agence. Retourne pour chaque paire (agence, compétence) le nombre "
                "de consultants qui la possèdent et le score IA moyen. "
                "Utilise cet outil pour : comparer les agences sur leurs forces techniques, identifier quelles "
                "agences couvrent le mieux une technologie (ex: 'Quelle agence a le plus de GCP ?'), "
                "ou produire un rapport de synthèse multi-agences pour un directeur commercial."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "min_count": {"type": "integer", "description": "Nombre minimum de consultants pour apparaitre dans les résultats (défaut: 1)", "default": 1},
                    "limit": {"type": "integer", "description": "Nombre maximum de lignes retournées (défaut: 50)", "default": 50}
                }
            }
        ),
        Tool(
            name="find_skill_gaps",
            description=(
                "Identifie les compétences manquantes dans un pool de consultants. "
                "Pour chaque compétence cible, calcule le taux de couverture dans le pool (0-100%). "
                "Utilise cet outil pour : détecter les lacunes d'une agence avant de répondre à un AO, "
                "identifier les compétences à recruter en priorité, "
                "ou analyser les manques d'une équipe projet. "
                "Passer les user_ids d'une agence (via get_users_by_tag) et optionnellement les competency_ids cibles."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "user_ids": {"type": "array", "items": {"type": "integer"}, "description": "Liste des IDs du pool de consultants à analyser"},
                    "competency_ids": {"type": "array", "items": {"type": "integer"}, "description": "IDs des compétences cibles (toutes les feuilles si omis)"},
                    "min_coverage": {"type": "number", "description": "Seuil de couverture (0.0-1.0) en dessous duquel une compétence est un gap (défaut: 0.0 = toutes)", "default": 0.0}
                },
                "required": ["user_ids"]
            }
        ),
        Tool(
            name="find_similar_consultants",
            description=(
                "Trouve les N consultants les plus similaires à un consultant de référence, "
                "basé sur la similarité de Jaccard de leurs compétences feuilles. "
                "Utilise cet outil pour : trouver un remplaçant sur une mission ('qui peut remplacer Ahmed ?'), "
                "identifier un mentor ou pair technique pour du coaching, "
                "ou proposer un backup consultant en urgence. "
                "Le score Jaccard va de 0 (aucune compétence commune) à 1 (profil identique)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "L'ID du consultant de référence"},
                    "top_n": {"type": "integer", "description": "Nombre de consultants similaires à retourner (défaut: 5)", "default": 5}
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
                response = await client.get(f"{API_BASE_URL}/", params=arguments)
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "search_competencies":
                response = await client.get(f"{API_BASE_URL}/search", params=arguments)
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "get_competency":
                response = await client.get(f"{API_BASE_URL}/{arguments['competency_id']}/")
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "create_competency":
                response = await client.post(f"{API_BASE_URL}/", json=arguments)
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "update_competency":
                comp_id = arguments["competency_id"]
                data = {k: v for k, v in arguments.items() if k != "competency_id" and v is not None}
                response = await client.put(f"{API_BASE_URL}/{comp_id}", json=data)
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "bulk_import_tree":
                response = await client.post(f"{API_BASE_URL}/bulk_tree", json={"tree": arguments["tree"]})
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "delete_competency":
                response = await client.delete(f"{API_BASE_URL}/{arguments['competency_id']}")
                response.raise_for_status()
                return [TextContent(type="text", text="Competency deleted successfully")]

            elif name == "assign_competency_to_user":
                user_id = arguments["user_id"]
                comp_id = arguments["competency_id"]
                response = await client.post(f"{API_BASE_URL}/user/{user_id}/assign/{comp_id}")
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "remove_competency_from_user":
                user_id = arguments["user_id"]
                comp_id = arguments["competency_id"]
                response = await client.delete(f"{API_BASE_URL}/user/{user_id}/remove/{comp_id}")
                response.raise_for_status()
                return [TextContent(type="text", text="Competency removed from user")]

            elif name == "list_user_competencies":
                response = await client.get(f"{API_BASE_URL}/user/{arguments['user_id']}")
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "list_competency_users":
                response = await client.get(f"{API_BASE_URL}/{arguments['competency_id']}/users")
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]
            
            elif name == "clear_user_competencies":
                user_id = arguments["user_id"]
                response = await client.delete(f"{API_BASE_URL}/user/{user_id}/clear")
                response.raise_for_status()
                return [TextContent(type="text", text=f"All competencies cleared for user {user_id}")]

            elif name == "get_competency_stats":
                response = await client.post(f"{API_BASE_URL}/stats/counts", json=arguments)
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "get_user_competency_evaluations":
                user_id = arguments["user_id"]
                response = await client.get(f"{API_BASE_URL}/evaluations/user/{user_id}")
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "set_user_competency_score":
                user_id = arguments["user_id"]
                competency_id = arguments["competency_id"]
                body = {"score": arguments["score"]}
                if arguments.get("comment"):
                    body["comment"] = arguments["comment"]
                response = await client.post(
                    f"{API_BASE_URL}/evaluations/user/{user_id}/competency/{competency_id}/user-score",
                    json=body
                )
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "trigger_ai_scoring":
                user_id = arguments["user_id"]
                response = await client.post(
                    f"{API_BASE_URL}/evaluations/user/{user_id}/ai-score-all"
                )
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "get_agency_competency_coverage":
                params = {}
                if "min_count" in arguments:
                    params["min_count"] = arguments["min_count"]
                if "limit" in arguments:
                    params["limit"] = arguments["limit"]
                response = await client.get(f"{API_BASE_URL}/analytics/agency-coverage", params=params)
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "find_skill_gaps":
                params = {"user_ids": arguments["user_ids"]}
                if "competency_ids" in arguments and arguments["competency_ids"]:
                    params["competency_ids"] = arguments["competency_ids"]
                if "min_coverage" in arguments:
                    params["min_coverage"] = arguments["min_coverage"]
                response = await client.get(f"{API_BASE_URL}/analytics/skill-gaps", params=params)
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            elif name == "find_similar_consultants":
                user_id = arguments["user_id"]
                top_n = arguments.get("top_n", 5)
                response = await client.get(
                    f"{API_BASE_URL}/analytics/similar-consultants/{user_id}",
                    params={"top_n": top_n}
                )
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json()))]

            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]


        except httpx.HTTPStatusError as e:
            if e.response.status_code == 409:
                return [TextContent(type="text", text=f"CONFLIT (409) : {e.response.text}. Ne PAS réessayer l'outil avec les mêmes paramètres.")]
            return [TextContent(type="text", text=f"API Error {e.response.status_code}: {e.response.text}")]
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
