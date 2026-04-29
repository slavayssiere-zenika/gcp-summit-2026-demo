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
                    },
                    "agency": {
                        "type": "string",
                        "description": "Filtre strict par ville/agence (ex: 'Paris', 'Lyon'). À utiliser si l'utilisateur demande explicitement une localisation."
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
            description="Récupère le classement global des consultants les plus expérimentés (basé sur les années d'expérience). Outil indispensable et OBLIGATOIRE pour générer des tableaux complets classés par séniorité.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Nombre de profils à retourner (défaut 5, peut aller jusqu'à 500 pour les requêtes globales)."
                    },
                    "agency": {
                        "type": "string",
                        "description": "Filtre optionnel sur le nom de l'agence (ex: 'Bordeaux', 'Paris')."
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
        ),

        # ── Sprint 0 ──────────────────────────────────────────────────────────
        Tool(
            name="reindex_cv_embeddings",
            description=(
                "(Admin Only) Re-calcule les embeddings vectoriels de tous les CVs existants "
                "avec la nouvelle représentation distillée améliorée (missions structurées), "
                "SANS relancer l'extraction LLM. À appeler après une mise à jour du pipeline "
                "d'embedding pour re-indexer le corpus. Retour immédiat — traitement en arrière-plan. "
                "Surveiller la progression via get_reanalyze_status. "
                "Ne JAMAIS appeler sans confirmation explicite de l'administrateur."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "tag": {"type": "string", "description": "Filtre par tag/agence (optionnel)"},
                    "user_id": {"type": "integer", "description": "Filtre par user_id (optionnel)"}
                }
            }
        ),

        # ── Sprint A ──────────────────────────────────────────────────────────
        Tool(
            name="find_similar_consultants",
            description=(
                "Trouve les consultants dont le profil sémantique est le plus proche d'un consultant donné. "
                "Utile pour : cloner un profil de staffing ('quelqu'un comme Jean Dupont'), "
                "constituer une équipe cohérente, ou identifier des remplaçants potentiels. "
                "Zéro coût LLM — résultat O(log N) via index HNSW pgvector (<100ms)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "L'ID du consultant de référence"},
                    "limit": {"type": "integer", "description": "Nombre de résultats (défaut 5, max 20)"},
                    "agency": {"type": "string", "description": "Filtre optionnel par agence/ville"}
                },
                "required": ["user_id"]
            }
        ),
        Tool(
            name="search_candidates_multi_criteria",
            description=(
                "Recherche sémantique multi-critères : trouve les consultants correspondant à PLUSIEURS "
                "dimensions techniques simultanément via une moyenne pondérée de distances cosine. "
                "Plus précis que plusieurs appels search_best_candidates séquentiels. "
                "Utiliser quand la requête contient 2 à 5 dimensions distinctes "
                "(ex: ['expert GCP', 'expérience migration legacy', 'leadership']). "
                "Supports des weights pour pondérer l'importance de chaque critère."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "queries": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Liste de 2 à 5 critères de recherche sémantiques"
                    },
                    "weights": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Pondération optionnelle (ex: [0.7, 0.3]). Défaut: équirépartition"
                    },
                    "limit": {"type": "integer", "description": "Nombre de résultats (défaut 10)"},
                    "agency": {"type": "string", "description": "Filtre optionnel par agence/ville"}
                },
                "required": ["queries"]
            }
        ),
        Tool(
            name="get_rag_snippet",
            description=(
                "Retourne les passages les plus pertinents du CV d'un consultant pour une query donnée. "
                "Utilise un chunking du profil distillé + re-ranking par similarité cosine. "
                "Permet de JUSTIFIER pourquoi un candidat est recommandé avec des preuves textuelles "
                "précises extraites de son historique de missions et compétences. "
                "Appeler après search_best_candidates pour enrichir la justification (timeout ~30s)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "L'ID du consultant"},
                    "query": {"type": "string", "description": "La requête de recherche (ex: 'expertise Kubernetes CI/CD')"},
                    "top_k": {"type": "integer", "description": "Nombre de passages à retourner (défaut 3, max 5)"}
                },
                "required": ["user_id", "query"]
            }
        ),

        # ── Sprint B ──────────────────────────────────────────────────────────
        Tool(
            name="match_mission_to_candidates",
            description=(
                "Matching direct mission → candidats via le semantic_embedding de la mission. "
                "Plus précis que search_best_candidates pour le staffing car prend en compte "
                "le contexte complet de la mission (description, compétences extraites). "
                "Retourne les N consultants les mieux alignés avec la mission ciblée, "
                "classés par score de similarité décroissant. "
                "Utiliser dès qu'un mission_id est connu — remplace search_best_candidates dans ce cas."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "mission_id": {"type": "integer", "description": "L'ID de la mission à staffer"},
                    "limit": {"type": "integer", "description": "Nombre de candidats à retourner (défaut 10)"},
                    "agency": {"type": "string", "description": "Filtre optionnel par agence/ville"}
                },
                "required": ["mission_id"]
            }
        ),

        # ── Sprint C ──────────────────────────────────────────────────────────
        Tool(
            name="get_skills_coverage",
            description=(
                "Analyse la couverture de compétences du corpus de consultants Zenika. "
                "Retourne les N compétences les plus représentées et le nombre de consultants par compétence. "
                "Aucun appel LLM — résultat instantané basé sur les keywords indexés. "
                "Utiliser pour répondre aux questions stratégiques : "
                "'Quelle est notre force en Cloud ?', 'Combien d'experts React avons-nous ?', "
                "'Quelle est la couverture compétences de l'agence Lyon ?'"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "agency": {"type": "string", "description": "Filtre optionnel par agence/tag"},
                    "top_n": {"type": "integer", "description": "Nombre de compétences à retourner (défaut 50)"}
                }
            }
        ),

        # ── Vertex AI Batch — Ré-analyse Globale (Option B) ───────────────────
        Tool(
            name="start_bulk_cv_reanalyse",
            description=(
                "(Admin Only) Lance la ré-analyse globale de TOUS les CVs en base via Vertex AI Batch. "
                "Pipeline complet Option B : extraction LLM + mise à jour cv_profiles + embedding + "
                "purge et réassignation des compétences + purge et réindexation des missions + scoring IA. "
                "Retour immédiat (202) — le traitement est entièrement asynchrone. "
                "Surveiller la progression via get_bulk_cv_reanalyse_status. "
                "NE JAMAIS appeler sans confirmation explicite de l'administrateur — opération irréversible."
            ),
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="get_bulk_cv_reanalyse_status",
            description=(
                "Retourne le statut courant du pipeline de ré-analyse globale (Vertex AI Batch). "
                "Statuts possibles : idle, building, uploading, batch_running, applying, completed, error. "
                "En phase batch_running, retourne les completion_stats Vertex en temps réel. "
                "En phase applying, retourne la progression N/M CVs traités. "
                "Appeler périodiquement pour suivre la progression sans bloquer."
            ),
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="cancel_bulk_cv_reanalyse",
            description=(
                "(Admin Only) Annule le job Vertex AI Batch de ré-analyse en cours et réinitialise l'état. "
                "Si le job est en phase batch_running, il est cancelé côté GCP. "
                "Si le job est en phase applying, les CVs déjà traités le restent."
            ),
            inputSchema={"type": "object", "properties": {}}
        ),

        # ── Data Quality ──────────────────────────────────────────────────────
        Tool(
            name="get_data_quality_report",
            description=(
                "Retourne le rapport de qualité des données du pipeline bulk CV. "
                "Score 0-100 (grade A-D) basé sur 7 métriques pondérées : missions extraites, "
                "embeddings vectoriels, compétences extraites, summary, current_role, "
                "competency_assignment (compétences liées aux consultants), "
                "et ai_scoring (≥10 compétences scorées par l'IA). "
                "Inclut les issues actionnables et une recommandation. "
                "Appeler pour diagnostiquer automatiquement l'état du pipeline après un bulk apply "
                "ou pour répondre aux questions 'Quel est l'état de nos données ?' "
                "ou 'Faut-il relancer un bulk scoring ?'."
            ),
            inputSchema={"type": "object", "properties": {}}
        ),
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
                agency = arguments.get("agency")
                if not query:
                    return [TextContent(type="text", text="Error: Missing query argument.")]
                
                try:
                    params = {"query": query, "limit": limit}
                    if agency:
                        params["agency"] = agency
                    response = await client.get(f"{API_BASE_URL}/search", params=params, headers=headers, timeout=60.0)
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
                agency = arguments.get("agency")
                params = {"limit": limit}
                if agency:
                    params["agency"] = agency
                try:
                    response = await client.get(f"{API_BASE_URL}/ranking/experience", params=params, headers=headers, timeout=20.0)
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

            # ── Sprint 0 : re-indexation embeddings ───────────────────────────
            elif name == "reindex_cv_embeddings":
                try:
                    params = {}
                    if arguments.get("tag"):
                        params["tag"] = arguments["tag"]
                    if arguments.get("user_id"):
                        params["user_id"] = arguments["user_id"]
                    response = await client.post(f"{API_BASE_URL}/reindex-embeddings", params=params, headers=headers, timeout=30.0)
                    response.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
                except httpx.HTTPStatusError as e:
                    return [TextContent(type="text", text=json.dumps({"success": False, "error": f"API Error {e.response.status_code}: {e.response.text}"}))]
                except Exception as e:
                    return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]

            # ── Sprint A : nouveaux endpoints RAG ─────────────────────────────
            elif name == "find_similar_consultants":
                user_id = arguments.get("user_id")
                if not user_id:
                    return [TextContent(type="text", text=json.dumps({"success": False, "error": "user_id requis"}))]
                try:
                    params = {"limit": arguments.get("limit", 5)}
                    if arguments.get("agency"):
                        params["agency"] = arguments["agency"]
                    response = await client.get(f"{API_BASE_URL}/user/{user_id}/similar", params=params, headers=headers, timeout=15.0)
                    response.raise_for_status()
                    data = response.json()
                    if not data:
                        return [TextContent(type="text", text=f"Aucun consultant similaire trouvé pour user_id={user_id}.")]
                    return [TextContent(type="text", text=json.dumps(data, indent=2))]
                except httpx.HTTPStatusError as e:
                    return [TextContent(type="text", text=json.dumps({"success": False, "error": f"API Error {e.response.status_code}: {e.response.text}"}))]
                except Exception as e:
                    return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]

            elif name == "search_candidates_multi_criteria":
                queries = arguments.get("queries")
                if not queries:
                    return [TextContent(type="text", text=json.dumps({"success": False, "error": "queries requis (liste de critères)"}))]
                try:
                    payload = {
                        "queries": queries,
                        "limit": arguments.get("limit", 10),
                    }
                    if arguments.get("weights"):
                        payload["weights"] = arguments["weights"]
                    if arguments.get("agency"):
                        payload["agency"] = arguments["agency"]
                    response = await client.post(f"{API_BASE_URL}/search/multi-criteria", json=payload, headers=headers, timeout=60.0)
                    response.raise_for_status()
                    data = response.json()
                    if not data:
                        return [TextContent(type="text", text=f"Aucun candidat correspondant à ces critères combinés.")]
                    return [TextContent(type="text", text=json.dumps(data, indent=2))]
                except httpx.HTTPStatusError as e:
                    return [TextContent(type="text", text=json.dumps({"success": False, "error": f"API Error {e.response.status_code}: {e.response.text}"}))]
                except Exception as e:
                    return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]

            elif name == "get_rag_snippet":
                user_id = arguments.get("user_id")
                query = arguments.get("query")
                if not user_id or not query:
                    return [TextContent(type="text", text=json.dumps({"success": False, "error": "user_id et query requis"}))]
                try:
                    params = {"query": query, "top_k": arguments.get("top_k", 3)}
                    response = await client.get(f"{API_BASE_URL}/user/{user_id}/rag-snippet", params=params, headers=headers, timeout=45.0)
                    response.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
                except httpx.HTTPStatusError as e:
                    return [TextContent(type="text", text=json.dumps({"success": False, "error": f"API Error {e.response.status_code}: {e.response.text}"}))]
                except Exception as e:
                    return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]

            # ── Sprint B : mission matching ────────────────────────────────────
            elif name == "match_mission_to_candidates":
                mission_id = arguments.get("mission_id")
                if not mission_id:
                    return [TextContent(type="text", text=json.dumps({"success": False, "error": "mission_id requis"}))]
                try:
                    params = {
                        "mission_id": mission_id,
                        "limit": arguments.get("limit", 10),
                    }
                    if arguments.get("agency"):
                        params["agency"] = arguments["agency"]
                    response = await client.post(f"{API_BASE_URL}/search/mission-match", params=params, headers=headers, timeout=30.0)
                    response.raise_for_status()
                    data = response.json()
                    if not data:
                        return [TextContent(type="text", text=f"Aucun candidat correspondant à la mission {mission_id}.")]
                    return [TextContent(type="text", text=json.dumps(data, indent=2))]
                except httpx.HTTPStatusError as e:
                    return [TextContent(type="text", text=json.dumps({"success": False, "error": f"API Error {e.response.status_code}: {e.response.text}"}))]
                except Exception as e:
                    return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]

            # ── Sprint C : analytics corpus ────────────────────────────────────
            elif name == "get_skills_coverage":
                try:
                    params = {"top_n": arguments.get("top_n", 50)}
                    if arguments.get("agency"):
                        params["agency"] = arguments["agency"]
                    response = await client.get(f"{API_BASE_URL}/analytics/skills-coverage", params=params, headers=headers, timeout=15.0)
                    response.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
                except httpx.HTTPStatusError as e:
                    return [TextContent(type="text", text=json.dumps({"success": False, "error": f"API Error {e.response.status_code}: {e.response.text}"}))]
                except Exception as e:
                    return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]

            # ── Vertex AI Batch — Ré-analyse Globale ────────────────────────────
            elif name == "start_bulk_cv_reanalyse":
                try:
                    response = await client.post(
                        f"{API_BASE_URL}/bulk-reanalyse/start",
                        headers=headers,
                        timeout=30.0,
                    )
                    response.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 409:
                        return [TextContent(type="text", text=f"CONFLIT (409) : une ré-analyse est déjà en cours. Utiliser get_bulk_cv_reanalyse_status pour suivre.")]
                    return [TextContent(type="text", text=json.dumps({"success": False, "error": f"API Error {e.response.status_code}: {e.response.text}"}))]
                except Exception as e:
                    return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]

            elif name == "get_bulk_cv_reanalyse_status":
                try:
                    response = await client.get(
                        f"{API_BASE_URL}/bulk-reanalyse/status",
                        headers=headers,
                        timeout=15.0,
                    )
                    response.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
                except httpx.HTTPStatusError as e:
                    return [TextContent(type="text", text=json.dumps({"success": False, "error": f"API Error {e.response.status_code}: {e.response.text}"}))]
                except Exception as e:
                    return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]

            elif name == "cancel_bulk_cv_reanalyse":
                try:
                    response = await client.post(
                        f"{API_BASE_URL}/bulk-reanalyse/cancel",
                        headers=headers,
                        timeout=15.0,
                    )
                    response.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
                except httpx.HTTPStatusError as e:
                    return [TextContent(type="text", text=json.dumps({"success": False, "error": f"API Error {e.response.status_code}: {e.response.text}"}))]
                except Exception as e:
                    return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]

            # ── Data Quality ────────────────────────────────────────────────────
            elif name == "get_data_quality_report":
                try:
                    response = await client.get(
                        f"{API_BASE_URL}/bulk-reanalyse/data-quality",
                        headers=headers,
                        timeout=30.0,
                    )
                    response.raise_for_status()
                    return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
                except httpx.HTTPStatusError as e:
                    return [TextContent(type="text", text=json.dumps({"success": False, "error": f"API Error {e.response.status_code}: {e.response.text}"}))]
                except Exception as e:
                    return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]

            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]

