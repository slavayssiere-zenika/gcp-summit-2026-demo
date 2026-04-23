import asyncio
import json
import os
import contextvars
import httpx
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

mcp_auth_header_var = contextvars.ContextVar("mcp_auth_header", default=None)
propagate.set_global_textmap(TraceContextTextMapPropagator())

API_BASE_URL = os.getenv("CV_API_URL", "http://localhost:8004")

sampling_rate = float(os.getenv("TRACE_SAMPLING_RATE", "1.0"))
sampler = ParentBased(root=TraceIdRatioBased(sampling_rate))
provider = TracerProvider(
    resource=Resource.create({
        ResourceAttributes.SERVICE_NAME: "cv-api-mcp",
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

server = Server("cv-api")

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="analyze_cv",
            description=(
                "Download, parse, extract, and convert a CV into the Zenika platform by recursively importing "
                "the candidate's skills and their matrix. Only call this when providing a public Google Docs Link. "
                "Returns a structured result with: 'message' (summary), 'user_id' (created/matched user), "
                "'competencies_assigned' (count), 'steps' (list of pipeline steps with status/duration — "
                "useful to explain what happened), and 'warnings' (non-blocking issues such as truncated document, "
                "zero competencies extracted, missing email, or identity conflicts). "
                "If 'warnings' is non-empty, report them to the user. "
                "If a step has status='error', the import failed at that stage. "
                "Si vous connaissez le nom du consultant (ex: depuis un dossier Drive 'Prénom Nom'), "
                "fournissez-le dans 'folder_name' pour une résolution d'identité Zenika prioritaire."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL of the candidate's CV. Must be a Google Document link."
                    },
                    "source_tag": {
                        "type": "string",
                        "description": "Optional thematic tag (e.g., location, department) to associate with this CV."
                    },
                    "folder_name": {
                        "type": "string",
                        "description": (
                            "Optionnel — Nom du consultant au format 'Prénom Nom' tel qu'il apparaît dans "
                            "le dossier Drive (nomenclature Zenika). Fait foi sur l'analyse LLM si fourni."
                        )
                    }
                },
                "required": ["url"]
            }
        ),

        Tool(
            name="search_best_candidates",
            description=(
                "Outil de recherche sémantique vectorielle — trouve les meilleurs candidats pour un contexte technique donné. "
                "RETOURNE UNIQUEMENT des user_ids. "
                "Il faut ensuite appeler get_candidate_rag_context ou get_user (users_api) pour enrichir les profils. "
                "Utiliser en priorité pour les questions 'qui maîtrise X ?' ou les missions de staffing. "
                "Ne pas utiliser pour retrouver une personne par son nom (utiliser search_users à la place)."
            ),
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
            name="get_user_cv",
            description="Get the CV profile (including source URL) for a specific user",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "integer",
                        "description": "The user ID"
                    }
                },
                "required": ["user_id"]
            }
        ),
        Tool(
            name="get_users_by_tag",
            description="Obtain the list of user profiles (including their user_id) associated with a specific tag (e.g. location like 'Niort')",
            inputSchema={
                "type": "object",
                "properties": {
                    "tag": {
                        "type": "string",
                        "description": "The custom tag (e.g., location like 'Niort') used during import to group or locate CVs"
                    }
                },
                "required": ["tag"]
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
        ),
        Tool(
            name="get_user_missions",
            description="Récupère la liste des missions (projets, expériences) d'un consultant avec les compétences associées à chaque mission.",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "integer",
                        "description": "L'ID de l'utilisateur"
                    }
                },
                "required": ["user_id"]
            }
        ),
        Tool(
            name="global_reanalyze_cvs",
            description=(
                "(Admin Only) Remet les CVs en file d'attente Pub/Sub pour réingestion complète. "
                "Efface les compétences existantes des utilisateurs concernés, remet les fichiers "
                "en PENDING dans le scanner Drive, et déclenche immédiatement un /sync. "
                "Retour IMMÉDIAT (< 30s) — le traitement réel s'effectue en arrière-plan via le worker cv_api. "
                "Surveiller la progression via GET /reanalyze/status ou le Scanner Drive. "
                "Ne JAMAIS appeler sans confirmation explicite de l'administrateur."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "tag": {
                        "type": "string",
                        "description": "Filtre par tag (ex: Niort)"
                    },
                    "user_id": {
                        "type": "integer",
                        "description": "Filtre par ID utilisateur"
                    }
                }
            }
        ),
        Tool(
            name="get_candidate_rag_context",
            description="Récupère les informations vectorisées et distillées (résumé, missions, rôle) pour un candidat. Utile pour comprendre pourquoi un profil correspond à une recherche ou pour générer une synthèse.",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "integer",
                        "description": "L'ID de l'utilisateur (candidat)"
                    }
                },
                "required": ["user_id"]
            }
        ),
        Tool(
            name="get_most_experienced_consultants",
            description="Récupère le classement des consultants les plus expérimentés (basé sur les années d'expérience).",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Nombre de profils à retourner (défaut 5)."
                    }
                }
            }
        ),
        Tool(
            name="get_cv_status_bulk",
            description=(
                "Vérifie la présence d'un CV pour une liste d'utilisateurs. "
                "Retourne un tableau indiquant pour chaque user_id si le CV existe (has_cv: true/false). "
                "Idéal pour filtrer les consultants n'ayant pas encore importé leur CV."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "user_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Liste d'IDs utilisateurs à vérifier"
                    }
                },
                "required": ["user_ids"]
            }
        ),
        Tool(
            name="get_reanalyze_status",
            description=(
                "Retourne l'état d'avancement de la réanalyse globale des CVs déclenchée par global_reanalyze_cvs. "
                "Inclut le nombre de CVs traités, en attente et en erreur. "
                "Appeler périodiquement pour suivre la progression sans bloquer l'agent."
            ),
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="get_recalculate_tree_status",
            description=(
                "Retourne l'état d'avancement du recalcul de l'arbre des compétences déclenché par recalculate_competencies_tree. "
                "Appeler pour savoir si le recalcul est terminé avant d'interroger la taxonomie mise à jour."
            ),
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="get_tags_map",
            description=(
                "Retourne le mapping complet tag → nombre de consultants pour toutes les agences/tags enregistrés. "
                "Utiliser pour lister toutes les agences disponibles, ou pour vérifier quel tag correspond "
                "à quelle entité Zenika avant d'appeler get_users_by_tag."
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
            if name == "analyze_cv":
                url = arguments.get("url")
                source_tag = arguments.get("source_tag")
                folder_name = arguments.get("folder_name")
                if not url:
                    return [TextContent(type="text", text="Error: Missing url argument.")]
                
                try:
                    payload = {"url": url}
                    if source_tag:
                        payload["source_tag"] = source_tag
                    if folder_name:
                        payload["folder_name"] = folder_name
                    response = await client.post(f"{API_BASE_URL}/import", json=payload, headers=headers, timeout=60.0)
                    response.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 409:
                        return [TextContent(type="text", text=f"CONFLIT (409) : {e.response.text}. Ne PAS réessayer l'outil avec les mêmes paramètres.")]
                    return [TextContent(type="text", text=f"API Error {e.response.status_code}: {e.response.text}")]
                except Exception as e:
                    return [TextContent(type="text", text=f"Request failed: {str(e)}")]
            
            elif name == "get_cv_status_bulk":
                user_ids = arguments.get("user_ids", [])
                if not user_ids:
                    return [TextContent(type="text", text="[]")]
                
                async def check_cv(uid):
                    try:
                        res = await client.get(f"{API_BASE_URL}/{uid}", headers=headers, timeout=5.0)
                        return {"user_id": uid, "has_cv": res.status_code == 200}
                    except Exception:
                        return {"user_id": uid, "has_cv": False}
                        
                import asyncio
                results = await asyncio.gather(*(check_cv(uid) for uid in user_ids))
                return [TextContent(type="text", text=json.dumps(results))]

            elif name == "search_best_candidates":
                query = arguments.get("query")
                limit = arguments.get("limit", 5)
                if not query:
                    return [TextContent(type="text", text="Error: Missing query argument.")]
                
                try:
                    response = await client.get(f"{API_BASE_URL}/search", params={"query": query, "limit": limit}, headers=headers, timeout=60.0)
                    response.raise_for_status()
                    data = response.json()
                    if not data:
                        return [TextContent(type="text", text=f"Aucun candidat ne correspond à la recherche sémantique '{query}' dans la base de CVs.")]
                    return [TextContent(type="text", text=json.dumps(data, indent=2))]
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 409:
                        return [TextContent(type="text", text=f"CONFLIT (409) : {e.response.text}. Ne PAS réessayer l'outil avec les mêmes paramètres.")]
                    return [TextContent(type="text", text=f"API Error {e.response.status_code}: {e.response.text}")]
                except Exception as e:
                    return [TextContent(type="text", text=f"Request failed: {str(e)}")]
            elif name == "get_user_cv":
                user_id = arguments.get("user_id")
                if not user_id:
                    return [TextContent(type="text", text="Error: Missing user_id argument.")]
                
                try:
                    response = await client.get(f"{API_BASE_URL}/user/{user_id}", headers=headers, timeout=10.0)
                    response.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 409:
                        return [TextContent(type="text", text=f"CONFLIT (409) : {e.response.text}. Ne PAS réessayer l'outil avec les mêmes paramètres.")]
                    return [TextContent(type="text", text=f"API Error {e.response.status_code}: {e.response.text}")]
                except Exception as e:
                    return [TextContent(type="text", text=f"Request failed: {str(e)}")]
            elif name == "recalculate_competencies_tree":
                try:
                    response = await client.post(f"{API_BASE_URL}/recalculate_tree", headers=headers, timeout=120.0)
                    response.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 409:
                        return [TextContent(type="text", text=f"CONFLIT (409) : {e.response.text}. Ne PAS réessayer l'outil avec les mêmes paramètres.")]
                    return [TextContent(type="text", text=f"API Error {e.response.status_code}: {e.response.text}")]
                except Exception as e:
                    return [TextContent(type="text", text=f"Request failed: {str(e)}")]
            elif name == "get_users_by_tag":
                tag = arguments.get("tag")
                if not tag:
                    return [TextContent(type="text", text="Error: Missing tag argument.")]
                
                try:
                    response = await client.get(f"{API_BASE_URL}/users/tag/{tag}", headers=headers, timeout=10.0)
                    response.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
                except httpx.HTTPStatusError as e:
                    return [TextContent(type="text", text=f"API Error {e.response.status_code}: {e.response.text}")]
                except Exception as e:
                    return [TextContent(type="text", text=f"Request failed: {str(e)}")]
            elif name == "get_user_missions":
                user_id = arguments.get("user_id")
                if not user_id:
                    return [TextContent(type="text", text="Error: Missing user_id argument.")]
                
                try:
                    response = await client.get(f"{API_BASE_URL}/user/{user_id}/missions", headers=headers, timeout=10.0)
                    response.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
                except httpx.HTTPStatusError as e:
                    return [TextContent(type="text", text=f"API Error {e.response.status_code}: {e.response.text}")]
                except Exception as e:
                    return [TextContent(type="text", text=f"Request failed: {str(e)}")]
            elif name == "global_reanalyze_cvs":
                try:
                    params = {}
                    if arguments.get("tag"): params["tag"] = arguments["tag"]
                    if arguments.get("user_id"): params["user_id"] = arguments["user_id"]
                    
                    response = await client.post(f"{API_BASE_URL}/reanalyze", params=params, headers=headers, timeout=30.0)
                    response.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
                except httpx.HTTPStatusError as e:
                    return [TextContent(type="text", text=f"API Error {e.response.status_code}: {e.response.text}")]
                except Exception as e:
                    return [TextContent(type="text", text=f"Request failed: {str(e)}")]

            elif name == "get_candidate_rag_context":
                user_id = arguments.get("user_id")
                if not user_id:
                    return [TextContent(type="text", text="Error: Missing user_id argument.")]
                try:
                    response = await client.get(f"{API_BASE_URL}/user/{user_id}/details", headers=headers, timeout=20.0)
                    response.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
                except httpx.HTTPStatusError as e:
                    return [TextContent(type="text", text=f"API Error {e.response.status_code}: {e.response.text}")]
                except Exception as e:
                    return [TextContent(type="text", text=f"Request failed: {str(e)}")]
            elif name == "get_most_experienced_consultants":
                limit = arguments.get("limit", 5)
                try:
                    response = await client.get(f"{API_BASE_URL}/ranking/experience", params={"limit": limit}, headers=headers, timeout=20.0)
                    response.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
                except httpx.HTTPStatusError as e:
                    return [TextContent(type="text", text=f"API Error {e.response.status_code}: {e.response.text}")]
                except Exception as e:
                    return [TextContent(type="text", text=f"Request failed: {str(e)}")]
            elif name == "get_reanalyze_status":
                try:
                    response = await client.get(f"{API_BASE_URL}/reanalyze/status", headers=headers, timeout=10.0)
                    response.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
                except httpx.HTTPStatusError as e:
                    return [TextContent(type="text", text=json.dumps({"success": False, "error": f"API Error {e.response.status_code}: {e.response.text}"}))] 
                except Exception as e:
                    return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]
            elif name == "get_recalculate_tree_status":
                try:
                    response = await client.get(f"{API_BASE_URL}/recalculate_tree/status", headers=headers, timeout=10.0)
                    response.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
                except httpx.HTTPStatusError as e:
                    return [TextContent(type="text", text=json.dumps({"success": False, "error": f"API Error {e.response.status_code}: {e.response.text}"}))] 
                except Exception as e:
                    return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]
            elif name == "get_tags_map":
                try:
                    response = await client.get(f"{API_BASE_URL}/users/tags/map", headers=headers, timeout=10.0)
                    response.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
                except httpx.HTTPStatusError as e:
                    return [TextContent(type="text", text=json.dumps({"success": False, "error": f"API Error {e.response.status_code}: {e.response.text}"}))] 
                except Exception as e:
                    return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]
            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]
