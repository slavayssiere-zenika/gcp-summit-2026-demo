# flake8: noqa: E501
from mcp.server import InitializationOptions
from tools.user_tools import (
    handle_assign_competency_to_user, handle_remove_competency_from_user, handle_list_user_competencies,
    handle_list_competency_users, handle_clear_user_competencies, handle_get_competency_stats,
    handle_get_agency_competency_coverage, handle_find_similar_consultants
)
from tools.tree_tools import (
    handle_search_competencies, handle_list_competencies, handle_get_competency, handle_create_competency, handle_update_competency,
    handle_delete_competency, handle_list_competency_suggestions, handle_create_competency_suggestion,
    handle_review_competency_suggestion
)
from tools.batch_tools import (
    handle_bulk_import_tree, handle_batch_evaluate_competencies_search, handle_batch_evaluate_competencies_users,
    handle_assign_competencies_bulk, handle_bulk_scoring_all
)
from tools.evaluation_tools import (
    handle_set_user_competency_score, handle_trigger_ai_scoring, handle_get_user_competency_evaluations,
    handle_clear_user_evaluations, handle_find_skill_gaps
)
import asyncio
import contextvars
import json
import logging
import os

import httpx
from mcp.server import InitializationOptions, Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
from opentelemetry import propagate, trace
from opentelemetry.propagate import inject
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.trace.propagation.tracecontext import \
    TraceContextTextMapPropagator

mcp_auth_header_var = contextvars.ContextVar("mcp_auth_header", default=None)


if os.getenv("TRACE_EXPORTER", "grpc") == "http":
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import \
        OTLPSpanExporter
elif os.getenv("TRACE_EXPORTER", "grpc") == "gcp":
    from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
else:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import \
        OTLPSpanExporter


propagate.set_global_textmap(TraceContextTextMapPropagator())

logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s', handlers=[logging.NullHandler()])

API_BASE_URL = os.getenv("COMPETENCIES_API_URL", "http://localhost:8003")

sampling_rate = float(os.getenv("TRACE_SAMPLING_RATE", "1.0"))
sampler = ParentBased(root=TraceIdRatioBased(sampling_rate))
provider = TracerProvider(
    resource=Resource.create({
        ResourceAttributes.SERVICE_NAME: "competencies-api-mcp",
        ResourceAttributes.SERVICE_VERSION: "1.0.0",
    }),
    sampler=sampler
)
if os.getenv("TRACE_EXPORTER", "grpc") == "gcp":
    provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))
else:
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter() if os.getenv(
        "TRACE_EXPORTER", "grpc") == "http" else OTLPSpanExporter(insecure=True)))
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
            },
            meta={"ui": {"resourceUri": "ui://competencies"}}
        ),
        Tool(
            name="search_competencies",
            description=(
                "Recherche des compétences par nom OU par alias dans l'arbre taxonomique. "
                "⚠️ LA RECHERCHE COUVRE DÉJÀ LES ALIASES : si 'Google Cloud Platform' a pour alias 'GCP', "
                "une recherche 'GCP' retournera LES DEUX nœuds. "
                "RÈGLE ANTI-FRAGMENTATION OBLIGATOIRE : la réponse peut contenir PLUSIEURS items représentant "
                "la même technologie sous des labels différents (ex: 'GCP' ID 10053 ET 'Google Cloud Platform' ID 12). "
                "Tu DOIS collecter TOUS les IDs retournés — ne jamais t'arrêter au premier résultat. "
                "Ces IDs seront ensuite passés individuellement à list_competency_users puis les pools d'users fusionnés. "
                "IMPORTANT : Utilise des termes spécifiques d'au moins 3 caractères (ex: 'AWS', 'React', 'Python'). "
                "NE PAS utiliser des lettres seules comme 'C', 'R', 'J' — elles matchent toutes les compétences contenant cette lettre. "
                "Pour les recherches sémantiques de staffing, préférer search_best_candidates (cv_api)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Le terme de recherche (minimum 3 caractères significatifs). Exemples: 'AWS', 'Kubernetes', 'React', 'GCP'"},
                    "limit": {"type": "integer", "description": "Nombre maximum de résultats (augmenter à 20 si la technologie peut avoir plusieurs labels)", "default": 20}
                },
                "required": ["query"]
            },
            meta={"ui": {"resourceUri": "ui://competencies"}}
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
                    "user_id": {"type": "integer", "description": "The user ID"},
                    "skip": {"type": "integer", "description": "Number of items to skip", "default": 0},
                    "limit": {"type": "integer", "description": "Maximum number of items to return", "default": 100}
                },
                "required": ["user_id"]
            }
        ),
        Tool(
            name="list_competency_users",
            description=(
                "Retourne la liste des IDs d'utilisateurs qui possèdent une compétence spécifique. "
                "⚠️ RETOURNE DES IDs BRUTS — pas des noms. "
                "⚠️ RÈGLE ANTI-FRAGMENTATION (OBLIGATOIRE) : Une même technologie peut exister sous plusieurs "
                "nœuds taxonomiques distincts (ex: 'GCP' ID 10053 ET 'Google Cloud Platform' ID 12). "
                "Si search_competencies a retourné N items, tu DOIS appeler list_competency_users N fois "
                "(une fois par ID) et faire l'UNION des listes — un consultant peut être indexé sous n'importe lequel des labels. "
                "Ne jamais conclure 'liste exhaustive' sans avoir interrogé TOUS les IDs retournés par search_competencies. "
                "FLUX OBLIGATOIRE pour 'qui maîtrise X ?' : "
                "1) search_competencies(query='X', limit=20) → liste de N items avec leurs IDs, "
                "2) list_competency_users pour CHAQUE ID → N listes d'user_ids, "
                "3) UNION des N listes (set() en Python / dédoublonnage), "
                "4) batch_evaluate_competencies_users(competency_ids=[TOUS les IDs], user_ids=[pool unifié]) → scores, "
                "5) filtrer ai_score ≥ seuil demandé, "
                "6) get_users_bulk → noms complets. "
                "NE PAS utiliser list_users : trop coûteux et incomplet (limit=100 max)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "competency_id": {"type": "integer", "description": "L'ID de la compétence (un appel par ID retourné par search_competencies)"}
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
                "Recupere TOUTES les evaluations de competences feuilles pour un consultant. "
                "⚠️ RETOURNE L'ENSEMBLE DES COMPÉTENCES DU CONSULTANT — pas uniquement une compétence spécifique. "
                "N'utiliser que pour un profil complet (coaching, bilan 360°). "
                "Si tu as besoin du score d'une seule compétence, préfère batch_evaluate_competencies_users "
                "qui est ciblé et retourne uniquement les compétences demandées. "
                "Chaque evaluation contient : la note IA (ai_score, calculee par Gemini depuis ses missions reelles), "
                "la justification textuelle de cette note, et la note auto-evaluee par le consultant (user_score)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "L'ID du consultant"},
                    "skip": {"type": "integer", "description": "Number of items to skip", "default": 0},
                    "limit": {"type": "integer", "description": "Maximum number of items to return", "default": 500}
                },
                "required": ["user_id"]
            },
            meta={"ui": {"resourceUri": "ui://evaluations"}}
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
            },
            meta={"ui": {"resourceUri": "ui://candidates"}}
        ),
        Tool(
            name="list_competency_suggestions",
            description=(
                "Liste les suggestions de compétences soumises automatiquement depuis les analyses de missions. "
                "Triées par fréquence d'occurrence ('signal marché'), elles indiquent quelles technologies "
                "les clients demandent régulièrement et qui ne sont pas encore dans la taxonomie. "
                "Utilise cet outil pour : identifier les compétences à ajouter en priorité, "
                "préparer les plans de formation, ou enrichir le référentiel de compétences."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["PENDING_REVIEW", "ACCEPTED", "REJECTED"],
                        "default": "PENDING_REVIEW",
                        "description": "Filtre par statut de la suggestion"
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Nombre maximum de résultats"}
                }
            }
        ),
        Tool(
            name="create_competency_suggestion",
            description=(
                "Soumet une suggestion de compétence pour révision admin. "
                "Idémpotent : si la suggestion existe déjà, incrémente son compteur d'occurrence. "
                "Utilise cet outil lorsque le consultant mentionne une technologie absente de la taxonomie "
                "et qui mériterait d'être ajoutée au référentiel."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nom de la compétence à suggérer"},
                    "source": {"type": "string", "default": "agent", "description": "Source : 'mission', 'cv' ou 'agent'"},
                    "context": {"type": "string", "description": "Contexte (ex: nom de la mission ou du CV)"}
                },
                "required": ["name"]
            }
        ),
        Tool(
            name="review_competency_suggestion",
            description=(
                "(Admin uniquement) Accepte ou rejette une suggestion de compétence. "
                "Si action='ACCEPT' : la compétence est créée dans la taxonomie officielle. "
                "Si action='REJECT' : la suggestion est archivée. "
                "Fournir parent_id pour placer la compétence dans l'arbre hiérarchique correct."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "suggestion_id": {"type": "integer", "description": "L'ID de la suggestion"},
                    "action": {"type": "string", "enum": ["ACCEPT", "REJECT"], "description": "Action à effectuer"},
                    "parent_id": {"type": "integer", "description": "(ACCEPT uniquement) ID du parent dans la taxonomie"},
                    "description": {"type": "string", "description": "(ACCEPT uniquement) Description de la compétence"}
                },
                "required": ["suggestion_id", "action"]
            }
        ),
        Tool(
            name="batch_evaluate_competencies_search",
            description=(
                "Récupère les évaluations de compétences pour un ensemble de consultants correspondant "
                "à une requête de recherche (completé par competency_ids optionnels). "
                "Retourne un tableau croisé [consultant x compétence] avec scores IA et auto-évalués. "
                "Utiliser pour comparer les niveaux de plusieurs candidats simultanément lors d'un staffing."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "user_ids": {"type": "array", "items": {"type": "integer"}, "description": "IDs des consultants à évaluer"},
                    "competency_ids": {"type": "array", "items": {"type": "integer"}, "description": "Optionnel — IDs des compétences à inclure (toutes si absent)"}
                },
                "required": ["user_ids"]
            }
        ),
        Tool(
            name="batch_evaluate_competencies_users",
            description=(
                "Récupère les scores de compétences pour un ensemble de consultants et des compétences ciblées. "
                "Retourne les scores IA par paire (user_id, compétence). Les utilisateurs sans score (ai_score=null) "
                "n'ont pas encore été analysés par l'IA — les exclure des résultats. "
                "⚠️ FLUX RECOMMANDÉ pour 'qui maîtrise une techno' : "
                "1) search_competencies → id, 2) list_competency_users → pool d'IDs, "
                "3) batch_evaluate_competencies_users(competency_ids=[id], user_ids=pool[:50]) → scores, "
                "4) filtrer ai_score >= 3.0, 5) get_users_bulk → noms. "
                "Ne jamais passer plus de 100 user_ids à la fois."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "competency_ids": {"type": "array", "items": {"type": "integer"}, "description": "IDs des compétences cibles"},
                    "user_ids": {"type": "array", "items": {"type": "integer"}, "description": "Optionnel — Filtre sur un pool de consultants (max 100)"}
                },
                "required": ["competency_ids"]
            }
        ),
        Tool(
            name="assign_competencies_bulk",
            description=(
                "(Admin/Pipeline) Résout, crée si manquant, et assigne en masse une liste de compétences "
                "pour un utilisateur en un seul appel. Idempotent. Ignore les compétences avec practiced=False. "
                "Utilisé par le pipeline de ré-analyse globale Vertex AI Batch."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "L'ID de l'utilisateur"},
                    "competencies": {
                        "type": "array",
                        "description": "Liste des compétences à assigner",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "parent": {"type": "string"},
                                "aliases": {"type": "array", "items": {"type": "string"}},
                                "practiced": {"type": "boolean", "default": True}
                            },
                            "required": ["name"]
                        }
                    }
                },
                "required": ["user_id", "competencies"]
            }
        ),
        Tool(
            name="clear_user_evaluations",
            description=(
                "(Admin Only) Supprime toutes les CompetencyEvaluation (scores IA + manuels) pour un utilisateur. "
                "Utilisé par le pipeline de ré-analyse globale avant ré-assignation complète des compétences."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "L'ID de l'utilisateur"}
                },
                "required": ["user_id"]
            }
        ),
        Tool(
            name="bulk_scoring_all",
            description=(
                "(Admin/Rattrapage) Déclenche le calcul IA des scores de compétences pour TOUS les consultants "
                "sans ai_score. Utiliser après un pipeline bulk ou quand des consultants n'ont pas de score "
                "suite à une erreur quota Gemini ou un scale-down Cloud Run. "
                "Retourne le nombre de consultants concernés et le message de confirmation. "
                "Le traitement se fait en arrière-plan (BackgroundTask) — ne pas attendre de résultats immédiats. "
                "Utiliser force=True pour re-scorer même les consultants ayant déjà un score."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "force": {"type": "boolean", "description": "Si True, re-score tous les consultants même avec un score existant", "default": False},
                    "semaphore_limit": {"type": "integer", "description": "Nombre max de scorings simultanés (2 recommandé)", "default": 2, "minimum": 1, "maximum": 5}
                },
                "required": []
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
    with tracer.start_as_current_span(f"mcp.tool.{name}"):
        auth_header = mcp_auth_header_var.get()
        headers = {}
        if auth_header:
            headers["Authorization"] = auth_header
        inject(headers)

        async with httpx.AsyncClient() as client:
            try:
                if name == "set_user_competency_score":
                    return await handle_set_user_competency_score(client, arguments, headers, API_BASE_URL)
                elif name == "trigger_ai_scoring":
                    return await handle_trigger_ai_scoring(client, arguments, headers, API_BASE_URL)
                elif name == "get_user_competency_evaluations":
                    return await handle_get_user_competency_evaluations(client, arguments, headers, API_BASE_URL)
                elif name == "clear_user_evaluations":
                    return await handle_clear_user_evaluations(client, arguments, headers, API_BASE_URL)
                elif name == "find_skill_gaps":
                    return await handle_find_skill_gaps(client, arguments, headers, API_BASE_URL)

                elif name == "bulk_import_tree":
                    return await handle_bulk_import_tree(client, arguments, headers, API_BASE_URL)
                elif name == "batch_evaluate_competencies_search":
                    return await handle_batch_evaluate_competencies_search(client, arguments, headers, API_BASE_URL)
                elif name == "batch_evaluate_competencies_users":
                    return await handle_batch_evaluate_competencies_users(client, arguments, headers, API_BASE_URL)
                elif name == "assign_competencies_bulk":
                    return await handle_assign_competencies_bulk(client, arguments, headers, API_BASE_URL)
                elif name == "bulk_scoring_all":
                    return await handle_bulk_scoring_all(client, arguments, headers, API_BASE_URL)

                if name == "list_competencies":
                    return await handle_list_competencies(client, arguments, headers, API_BASE_URL)
                elif name == "search_competencies":
                    return await handle_search_competencies(client, arguments, headers, API_BASE_URL)
                elif name == "get_competency":
                    return await handle_get_competency(client, arguments, headers, API_BASE_URL)
                elif name == "create_competency":
                    return await handle_create_competency(client, arguments, headers, API_BASE_URL)
                elif name == "update_competency":
                    return await handle_update_competency(client, arguments, headers, API_BASE_URL)
                elif name == "delete_competency":
                    return await handle_delete_competency(client, arguments, headers, API_BASE_URL)
                elif name == "list_competency_suggestions":
                    return await handle_list_competency_suggestions(client, arguments, headers, API_BASE_URL)
                elif name == "create_competency_suggestion":
                    return await handle_create_competency_suggestion(client, arguments, headers, API_BASE_URL)
                elif name == "review_competency_suggestion":
                    return await handle_review_competency_suggestion(client, arguments, headers, API_BASE_URL)

                elif name == "assign_competency_to_user":
                    return await handle_assign_competency_to_user(client, arguments, headers, API_BASE_URL)
                elif name == "remove_competency_from_user":
                    return await handle_remove_competency_from_user(client, arguments, headers, API_BASE_URL)
                elif name == "list_user_competencies":
                    return await handle_list_user_competencies(client, arguments, headers, API_BASE_URL)
                elif name == "list_competency_users":
                    return await handle_list_competency_users(client, arguments, headers, API_BASE_URL)
                elif name == "clear_user_competencies":
                    return await handle_clear_user_competencies(client, arguments, headers, API_BASE_URL)
                elif name == "get_competency_stats":
                    return await handle_get_competency_stats(client, arguments, headers, API_BASE_URL)
                elif name == "get_agency_competency_coverage":
                    return await handle_get_agency_competency_coverage(client, arguments, headers, API_BASE_URL)
                elif name == "find_similar_consultants":
                    return await handle_find_similar_consultants(client, arguments, headers, API_BASE_URL)

                else:
                    return [TextContent(type="text", text=json.dumps({"success": False, "error": f"Unknown tool: {name}"}))]
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 409:
                    return [TextContent(type="text", text=json.dumps({"success": False, "error": f"CONFLIT (409) : {e.response.text}. Ne PAS réessayer l'outil avec les mêmes paramètres."}))]
                return [TextContent(type="text", text=json.dumps({"success": False, "error": f"API Error {e.response.status_code}: {e.response.text}"}))]
            except Exception as e:
                return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]


async def main():
    """Main entry point for the MCP server when run as a script."""
    options = InitializationOptions(
        server_name="competencies-api",
        server_version="1.0.0",
        capabilities={}
    )
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
