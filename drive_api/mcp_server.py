import asyncio
import json
import os
import contextvars
from mcp.server import Server
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
from opentelemetry.propagate import inject
import httpx

mcp_auth_header_var = contextvars.ContextVar("mcp_auth_header", default=None)
propagate.set_global_textmap(TraceContextTextMapPropagator())

API_BASE_URL = os.getenv("DRIVE_API_URL", "http://localhost:8006")

sampling_rate = float(os.getenv("TRACE_SAMPLING_RATE", "1.0"))
sampler = ParentBased(root=TraceIdRatioBased(sampling_rate))
provider = TracerProvider(
    resource=Resource.create({
        ResourceAttributes.SERVICE_NAME: "drive-api-mcp",
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

server = Server("drive-api")

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="add_drive_folder",
            description=(
                "Enregistre un dossier Google Drive pour la synchronisation automatique des CVs. "
                "Le nom du dossier est automatiquement récupéré depuis l'API Drive. "
                "Convention Zenika : les dossiers consultants sont nommés 'Prénom Nom' (ex: 'Marie Dupont'). "
                "Ce nom sera utilisé comme identité prioritaire lors de l'ingestion du CV. "
                "Les dossiers commençant par '_' (underscore) sont exclus de toute synchronisation. "
                "Requires a folder ID and a business tag."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "google_folder_id": {
                        "type": "string",
                        "description": "L'ID unique Google Drive du dossier (ou son URL complète — l'ID sera extrait automatiquement)"
                    },
                    "tag": {
                        "type": "string",
                        "description": "Tag métier logique à appliquer à tous les CVs trouvés (ex: 'Paris', 'Nantes', 'Data')"
                    },
                    "folder_name": {
                        "type": "string",
                        "description": "Optionnel — Nom du dossier (nomenclature 'Prénom Nom'). Si absent, récupéré automatiquement via l'API Drive."
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
        ),
        Tool(
            name="get_drive_file_state",
            description=(
                "Retourne l'état de synchronisation d'un fichier Drive par son ID Google. "
                "Inclut le parent_folder_name (nomenclature Zenika 'Prénom Nom') utilisé "
                "pour la résolution d'identité prioritaire lors de la réanalyse de CV."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "google_file_id": {
                        "type": "string",
                        "description": "L'ID Google Drive du fichier (ex: '1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs')"
                    }
                },
                "required": ["google_file_id"]
            }
        ),
        Tool(
            name="reset_drive_folder_sync",
            description=(
                "Remet tous les fichiers d'un dossier Drive (ou de tous les dossiers si tag absent) "
                "en statut PENDING pour forcer une re-synchronisation complète. "
                "Utiliser quand des fichiers sont bloqués dans un état incohérent ou après un changement de configuration."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "tag": {
                        "type": "string",
                        "description": "Optionnel — tag du dossier à réinitialiser. Si absent, réinitialise tous les dossiers."
                    }
                }
            }
        ),
        Tool(
            name="get_dlq_status",
            description=(
                "Retourne l'état de la Dead Letter Queue (DLQ) du scanner Drive : "
                "nombre de messages en erreur, aperçu des fichiers bloqués et raisons d'échec. "
                "Utiliser pour diagnostiquer les CVs qui n'ont pas pu être ingérés automatiquement."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Nombre maximum de messages DLQ à retourner (défaut: 10)",
                        "default": 10
                    }
                }
            }
        ),
        Tool(
            name="delete_dlq_message",
            description=(
                "Supprime un message spécifique de la Dead Letter Queue Drive (par son ack_id ou file_id). "
                "Utiliser pour acquitter définitivement un message erroné non récupérable "
                "(fichier supprimé, accès révoqué, format non supporté)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ack_id": {
                        "type": "string",
                        "description": "L'identifiant Pub/Sub ack_id du message à supprimer (retourné par get_dlq_status)"
                    },
                    "google_file_id": {
                        "type": "string",
                        "description": "Alternative : l'ID Google Drive du fichier à supprimer de la DLQ"
                    }
                }
            }
        ),
        Tool(
            name="replay_dlq",
            description=(
                "Rejoue tous les messages de la Dead Letter Queue Drive : remet les fichiers en erreur "
                "en statut PENDING et déclenche une nouvelle tentative d'ingestion. "
                "Utiliser après avoir résolu la cause racine des erreurs (ex: permission Drive accordée, "
                "format de fichier corrigé). Retour immédiat — le traitement s'effectue en arrière-plan."
            ),
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="update_drive_file",
            description=(
                "Met à jour l'état ou les métadonnées d'un fichier Drive suivi par le scanner. "
                "Permet de forcer un statut (ex: 'PENDING' pour re-tenter l'ingéstion) "
                "ou de corriger des métadonnées incorrectes."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_id": {
                        "type": "string",
                        "description": "L'ID Google Drive du fichier à mettre à jour"
                    },
                    "status": {
                        "type": "string",
                        "enum": ["PENDING", "PROCESSING", "DONE", "ERROR", "IGNORED"],
                        "description": "Nouveau statut à appliquer au fichier"
                    },
                    "error_message": {
                        "type": "string",
                        "description": "Optionnel — message d'erreur à associer"
                    }
                },
                "required": ["file_id"]
            }
        ),
        Tool(
            name="get_ingestion_kpis",
            description=(
                "Retourne les KPIs de data quality du pipeline d'ingéstion Drive → CV. "
                "Inclut le grade global (A/B/C/D/F), les métriques de couverture (taux d'import, "
                "liaison consultant, nommage résolu, durée de traitement, fraîcheur du pipeline) "
                "et les recommandations d'actions correctives. "
                "Appeler avant de décider de lancer un Quality Gate Batch."
            ),
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="get_folder_ingestion_kpis",
            description=(
                "Retourne les KPIs d'ingéstion par folder/agence. "
                "Permet d'identifier quelles agences ont des problèmes d'import, "
                "de liaison consultant ou de durée de traitement anormale. "
                "Chaque folder est classé avec un statut ok/warning/critical."
            ),
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="run_quality_gate_batch",
            description=(
                "Déclenche un Quality Gate Batch sur le pipeline Drive : identifie les CVs importés "
                "avec des données incomplètes (user_id manquant, nommage absent, erreurs persistantes) "
                "et les remet en PENDING pour re-traitement ciblé via Pub/Sub. "
                "Plus fin qu'un retry global : ne re-traite que les CVs avec des problèmes identifiés. "
                "Retourne le nombre de CVs remis en queue et la ventilation par raison."
            ),
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

                elif name == "get_drive_file_state":
                    gfid = arguments.get("google_file_id")
                    if not gfid:
                        return [TextContent(type="text", text=json.dumps({"success": False, "error": "Paramètre 'google_file_id' manquant."}))]
                    res = await client.get(f"{API_BASE_URL}/files/{gfid}", headers=headers, timeout=10.0)
                    res.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(res.json(), indent=2))]

                elif name == "reset_drive_folder_sync":
                    params = {}
                    if arguments.get("tag"):
                        params["tag"] = arguments["tag"]
                    res = await client.post(f"{API_BASE_URL}/folders/reset-sync", params=params, headers=headers, timeout=30.0)
                    res.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(res.json(), indent=2))]

                elif name == "get_dlq_status":
                    limit = arguments.get("limit", 10)
                    res = await client.get(f"{API_BASE_URL}/dlq/status", params={"limit": limit}, headers=headers, timeout=30.0)
                    res.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(res.json(), indent=2))]

                elif name == "delete_dlq_message":
                    params = {}
                    if arguments.get("ack_id"):
                        params["ack_id"] = arguments["ack_id"]
                    if arguments.get("google_file_id"):
                        params["google_file_id"] = arguments["google_file_id"]
                    if not params:
                        return [TextContent(type="text", text=json.dumps({"success": False, "error": "Fournir 'ack_id' ou 'google_file_id'."}))]
                    res = await client.delete(f"{API_BASE_URL}/dlq/message", params=params, headers=headers, timeout=20.0)
                    res.raise_for_status()
                    return [TextContent(type="text", text=json.dumps({"success": True, "message": "Message DLQ supprimé."}))]

                elif name == "replay_dlq":
                    res = await client.post(f"{API_BASE_URL}/dlq/replay", headers=headers, timeout=60.0)
                    res.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(res.json(), indent=2))]

                elif name == "update_drive_file":
                    file_id = arguments.get("file_id")
                    if not file_id:
                        return [TextContent(type="text", text=json.dumps({"success": False, "error": "Paramètre 'file_id' manquant."}))]
                    body = {k: v for k, v in arguments.items() if k != "file_id" and v is not None}
                    res = await client.patch(f"{API_BASE_URL}/files/{file_id}", json=body, headers=headers, timeout=10.0)
                    res.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(res.json(), indent=2))]

                elif name == "get_ingestion_kpis":
                    res = await client.get(f"{API_BASE_URL}/ingestion/stats", headers=headers, timeout=30.0)
                    res.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(res.json(), indent=2))]

                elif name == "get_folder_ingestion_kpis":
                    res = await client.get(f"{API_BASE_URL}/ingestion/folder-kpis", headers=headers, timeout=30.0)
                    res.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(res.json(), indent=2))]

                elif name == "run_quality_gate_batch":
                    res = await client.post(f"{API_BASE_URL}/ingestion/quality-gate-batch", headers=headers, timeout=60.0)
                    res.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(res.json(), indent=2))]

                else:
                    return [TextContent(type="text", text=f"Unknown tool: {name}")]
            except httpx.HTTPStatusError as e:
                return [TextContent(type="text", text=json.dumps({"success": False, "error": f"API Error {e.response.status_code}: {e.response.text}"}))]
            except Exception as e:
                return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]
