"""
mcp_server.py — Dispatcher MCP pour monitoring_mcp.

Ce fichier est le point d'entrée du serveur MCP stdio.
Il ne contient plus aucune logique d'implémentation — tout est délégué
aux modules du package `tools/`.

Architecture :
  tools/infra_tools.py   → topologie GCP, liste services Cloud Run
  tools/logs_tools.py    → logs Cloud Logging (service, trace, 500 errors)
  tools/data_tools.py    → Redis, AlloyDB, Pub/Sub DLQ
  tools/pipeline_tools.py → health checks, pipeline ingestion CV
"""

import json
import logging

from context import mcp_auth_header_var  # noqa: F401
from mcp.server import Server
from mcp.types import TextContent, Tool
from tools.data_tools import (execute_read_only_query_internal,
                              get_redis_invalidation_state_internal,
                              inspect_pubsub_dlq_internal)
from tools.infra_tools import get_gcp_project_id, list_gcp_services_internal
from tools.infra_tools import get_gcp_project_id_from_metadata  # noqa: F401
from tools.infra_tools import get_infrastructure_topology  # noqa: F401
from tools.logs_tools import (get_recent_500_errors_internal,
                              get_service_logs_internal,
                              search_cloud_logs_by_trace_internal)
from tools.pipeline_tools import (check_all_components_health_internal,
                                  check_component_health_internal,
                                  get_ingestion_pipeline_status_internal)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ID = get_gcp_project_id()
server = Server("monitoring-mcp")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Registre des 10 tools MCP exposés par monitoring_mcp."""
    return [
        Tool(
            name="get_service_logs",
            description="Extrait les logs récents d'un service Cloud Run spécifique. Permet d'investiguer les erreurs 500 ou les timeouts.",  # noqa: E501
            inputSchema={
                "type": "object",
                "properties": {
                    "service_name": {"type": "string", "description": "Le nom du service Cloud Run (ex: 'agent-router-api-dev')."},  # noqa: E501
                    "limit": {"type": "integer", "description": "Nombre de lignes à remonter (défaut 10).", "default": 10},  # noqa: E501
                    "hours_lookback": {"type": "integer", "description": "Nombre d'heures d'historique (défaut 1).", "default": 1},  # noqa: E501
                    "severity": {"type": "string", "description": "Niveau minimum de sévérité (ex: 'ERROR', 'INFO').", "default": "DEFAULT"},  # noqa: E501
                },
                "required": ["service_name"],
            },
        ),
        Tool(
            name="list_gcp_services",
            description="Liste tous les services Cloud Run de la plateforme Zenika déployés dans le projet GCP.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="check_component_health",
            description="Vérifie l'état de santé d'un composant de la plateforme (Service Cloud Run, Redis, BigQuery, AlloyDB).",  # noqa: E501
            inputSchema={
                "type": "object",
                "properties": {
                    "component_name": {"type": "string", "description": "Nom du service ou composant (ex: 'users-api', 'redis-cache', 'alloydb')."}  # noqa: E501
                },
                "required": ["component_name"],
            },
        ),
        Tool(
            name="check_all_components_health",
            description="Réalise un check de santé global de TOUS les services et composants de la plateforme Zenika.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="get_ingestion_pipeline_status",
            description="Récupère l'état complet de la pipeline d'ingestion des CVs (Discovery Drive → Queue Pub/Sub → Traitement cv_api). Retourne les compteurs par statut et signale les blocages.",  # noqa: E501
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="search_cloud_logs_by_trace",
            description="Récupère le flux de logs Cloud Logging complet associé à un trace ID spécifique. À utiliser en conjonction avec l'outil serveur Cloud Trace natif (cloudtrace) pour corréler une trace lente avec les logs d'application.",  # noqa: E501
            inputSchema={
                "type": "object",
                "properties": {
                    "trace_id": {"type": "string", "description": "L'ID de la trace (sans le préfixe project)."},
                    "limit": {"type": "integer", "description": "Nombre de logs max.", "default": 50},
                },
                "required": ["trace_id"],
            },
        ),
        Tool(
            name="get_recent_500_errors",
            description="Recherche les erreurs HTTP 5xx récentes sur l'ensemble des services Cloud Run GCP.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Nombre de logs max.", "default": 10},
                    "hours_lookback": {"type": "integer", "description": "Nombre d'heures d'historique.", "default": 1},
                },
            },
        ),
        Tool(
            name="inspect_pubsub_dlq",
            description="Examine les messages dans la file DLQ Pub/Sub sans les acquitter (lecture seule).",
            inputSchema={
                "type": "object",
                "properties": {
                    "subscription_id": {"type": "string", "description": "L'ID de la souscription DLQ.", "default": "cv-ingestion-dlq-sub"},  # noqa: E501
                    "limit": {"type": "integer", "description": "Nombre max de messages à lire.", "default": 10},
                },
            },
        ),
        Tool(
            name="get_redis_invalidation_state",
            description="Vérifie l'état des clés dans Redis (cache sémantique, sessions). Utile pour déboguer des problèmes d'invalidation.",  # noqa: E501
            inputSchema={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Pattern de recherche de clés (ex: 'items:list:*', 'session:*').", "default": "*"}  # noqa: E501
                },
            },
        ),
        Tool(
            name="execute_read_only_query",
            description="Exécute une requête SQL SELECT (lecture seule) sur la base PostgreSQL/AlloyDB.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "La requête SQL SELECT."},
                    "db_name": {"type": "string", "description": "Nom de la base.", "default": "zenika"},
                },
                "required": ["query"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Dispatcher — route chaque appel vers le module tool approprié."""
    try:
        if name == "get_service_logs":
            data = await get_service_logs_internal(
                arguments.get("service_name"),
                arguments.get("limit", 10),
                arguments.get("hours_lookback", 1),
                arguments.get("severity", "DEFAULT"),
            )

        elif name == "list_gcp_services":
            data = await list_gcp_services_internal()

        elif name == "check_component_health":
            data = await check_component_health_internal(arguments.get("component_name"))

        elif name == "check_all_components_health":
            data = await check_all_components_health_internal()

        elif name == "get_ingestion_pipeline_status":
            data = await get_ingestion_pipeline_status_internal()

        elif name == "search_cloud_logs_by_trace":
            data = await search_cloud_logs_by_trace_internal(
                arguments.get("trace_id"),
                arguments.get("limit", 50),
            )

        elif name == "get_recent_500_errors":
            data = await get_recent_500_errors_internal(
                arguments.get("limit", 10),
                arguments.get("hours_lookback", 1),
            )

        elif name == "inspect_pubsub_dlq":
            data = await inspect_pubsub_dlq_internal(
                arguments.get("subscription_id", "cv-ingestion-dlq-sub"),
                arguments.get("limit", 10),
            )

        elif name == "get_redis_invalidation_state":
            data = await get_redis_invalidation_state_internal(arguments.get("pattern", "*"))

        elif name == "execute_read_only_query":
            data = await execute_read_only_query_internal(
                arguments.get("query"),
                arguments.get("db_name", "zenika"),
            )

        else:
            data = {"error": f"Unknown tool: {name}"}

        return [TextContent(type="text", text=json.dumps(data))]

    except Exception as e:
        logger.exception(f"Error in monitoring-mcp tool call '{name}'")
        return [TextContent(type="text", text=json.dumps({"error": str(e), "tool": name, "status": "failure"}))]
