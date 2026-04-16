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
            description=(
                "Liste tous les utilisateurs avec pagination. "
                "Utiliser uniquement pour des listings génériques sans critère de recherche. "
                "Si un nom ou email est connu, préférer search_users qui est plus précis."
            ),
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
            description=(
                "Récupère un utilisateur par son ID (entier). "
                "ATTENTION : n'appeler qu'avec un ID réel issu d'un appel précédent à search_users. "
                "Ne JAMAIS inventer ou deviner un ID."
            ),
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
            description=(
                "Crée un nouvel utilisateur. "
                "Si le mot de passe n'est pas fourni explicitement, générer un mot de passe aléatoire sécurisé (ex: UUID). "
                "Ne JAMAIS échouer avec une erreur 422 pour cause de mot de passe manquant."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "username": {"type": "string", "description": "Username"},
                    "email": {"type": "string", "description": "Email address"},
                    "password": {"type": "string", "description": "User password"},
                    "full_name": {"type": "string", "description": "Full name (optional)"},
                    "is_anonymous": {"type": "boolean", "description": "Is this an anonymous/provisional profile?", "default": False}
                },
                "required": ["username", "email", "password"]
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
            description=(
                "ACTION DESTRUCTIVE ET IRRÉVERSIBLE. Supprime définitivement un utilisateur et toutes ses données associées. "
                "Ne PAS appeler sans confirmation explicite de l'utilisateur dans sa requête. "
                "Toujours proposer update_user (désactivation via is_active=false) comme alternative moins destructive."
            ),
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
            description=(
                "PREMIÈRE ÉTAPE OBLIGATOIRE pour tout flux impliquant un utilisateur identifié par son nom. "
                "Recherche par username, email ou nom complet. "
                "Retourne une liste d'utilisateurs avec leurs IDs réels. "
                "TOUJOURS appeler avant get_user, list_user_competencies, get_user_cv ou get_candidate_rag_context. "
                "Ne JAMAIS inventer un user_id sans passer par cet outil d'abord. "
                "Utiliser des mots-clés simples sans accents (ex: 'Lavayssiere' et non 'Lavayssière')."
            ),
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
        ),
        Tool(
            name="get_user_availability",
            description=(
                "Retourne la disponibilité consolidée d'un consultant en deux dimensions :\n"
                "1. unavailability_periods : indisponibilités déclarées (congés, formation, inter-contrat).\n"
                "2. active_missions : missions sur lesquelles le consultant est actuellement STAFFÉ (proposed_team). "
                "Un consultant avec des active_missions est déjà engagé — il n'est PAS pleinement disponible. "
                "TOUJOURS vérifier active_missions avant d'affirmer qu'un consultant est disponible pour une nouvelle mission."
            ),
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
                    "password": arguments.get("password", ""),
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
                data = response.json()
                if not data:
                    return [TextContent(type="text", text=f"Aucun utilisateur trouvé dans la base de données pour la recherche '{query}'.")]
                return [TextContent(type="text", text=json.dumps(data))]

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

            elif name == "get_user_availability":
                user_id = arguments['user_id']
                response = await client.get(f"{API_BASE_URL}/{user_id}")
                response.raise_for_status()
                user_data = response.json()
                unavailability_periods = user_data.get("unavailability_periods", [])

                # STAFF-003 : Croiser avec les missions actives (proposed_team) pour détecter
                # les conflits de staffing. Un consultant déjà proposé sur une mission active
                # n'est PAS pleinement disponible même si ses unavailability_periods sont vides.
                active_missions = []
                missions_api_url = os.getenv("MISSIONS_API_URL", "http://missions_api:8009")
                try:
                    missions_response = await client.get(
                        f"{missions_api_url}/missions/user/{user_id}/active",
                        timeout=5.0
                    )
                    if missions_response.status_code == 200:
                        missions_data = missions_response.json()
                        active_missions = missions_data.get("active_missions", [])
                except Exception as missions_err:
                    # Dégradation gracieuse : si missions_api est indisponible, on retourne
                    # quand même les indisponibilités déclarées sans bloquer la réponse.
                    logging.warning(
                        f"[get_user_availability] missions_api indisponible pour user {user_id}: {missions_err}. "
                        "Dégradation gracieuse : seules les unavailability_periods sont retournées."
                    )

                result = {
                    "user_id": user_id,
                    "unavailability_periods": unavailability_periods,
                    "active_missions": active_missions,
                    "is_available": len(active_missions) == 0 and len(unavailability_periods) == 0,
                    "conflict_detected": len(active_missions) > 0,
                    "summary": (
                        f"CONFLIT DÉTECTÉ : Le consultant est déjà staffé sur {len(active_missions)} mission(s) active(s). "
                        f"Missions : {', '.join(m['mission_title'] for m in active_missions)}"
                        if active_missions
                        else (
                            f"INDISPONIBILITÉS DÉCLARÉES : {len(unavailability_periods)} période(s) d'indisponibilité."
                            if unavailability_periods
                            else "DISPONIBLE : Aucun conflit de staffing ni indisponibilité déclarée."
                        )
                    )
                }
                return [TextContent(type="text", text=json.dumps(result))]

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
