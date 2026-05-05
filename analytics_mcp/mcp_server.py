# flake8: noqa: E501
from tools.finops_tools import handle_log_ai_consumption, handle_get_finops_report, handle_detect_usage_anomalies, handle_get_aiops_dashboard_data
from tools.market_tools import handle_get_top_market_skills, handle_get_market_demand_volume
import asyncio
import contextvars
import json
import logging
import os
from datetime import datetime, timezone

from google.cloud import bigquery
from mcp.server import Server
from mcp.types import TextContent, Tool

# Standard context var for MCP auth
mcp_auth_header_var = contextvars.ContextVar("mcp_auth_header", default=None)

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Config


def get_gcp_project_id() -> str:
    """
    Résout le GCP project ID dans l'ordre de priorité :
    1. Variable d'environnement GCP_PROJECT_ID
    2. ADC via google.auth.default() (natif Cloud Run / gcloud CLI)
    3. Chaîne vide — le client BigQuery lèvera une erreur explicite
    """
    pid = os.getenv("GCP_PROJECT_ID", "").strip()
    if pid and pid not in ("your-gcp-project-id", "YOUR_GCP_PROJECT_ID"):
        return pid
    try:
        import google.auth
        _, project = google.auth.default()
        if project:
            logger.info("[GCP] Project ID résolu via ADC : '%s'", project)
            return project
    except Exception as e:
        logger.warning("[GCP] Impossible de résoudre le project ID via google.auth.default(): %s", e)
    return ""


async def get_gcp_project_id_from_metadata() -> str:
    """Récupère le Project ID GCP depuis le Metadata Server (http://metadata.google.internal).

    Utilisé préférentiellement à google.auth.default() pour les appels async en milieu Cloud Run.
    Ordre de priorité :
    1. Variable d'environnement GCP_PROJECT_ID (override explicite)
    2. GCP Metadata Server (disponible sur Cloud Run, GCE, GKE)
    3. Fallback sync google.auth.default() + valeur hardcodée
    """
    pid = os.getenv("GCP_PROJECT_ID")
    if pid:
        return pid
    try:
        import httpx
        async with httpx.AsyncClient(timeout=2.0) as client:
            res = await client.get(
                "http://metadata.google.internal/computeMetadata/v1/project/project-id",
                headers={"Metadata-Flavor": "Google"}
            )
            if res.status_code == 200:
                project_id = res.text.strip()
                logger.info("[metadata] GCP Project ID retrieved from metadata server: %s", project_id)
                return project_id
    except Exception as e:
        logger.debug("[metadata] Metadata server unavailable (expected in local dev): %s", e)
    # Fallback sur la méthode sync
    return get_gcp_project_id()


PROJECT_ID = get_gcp_project_id()
DATASET_ID = os.getenv("DATASET_ID", "analytics_data")
TABLE_ID = os.getenv("TABLE_ID", "job_offers")
TABLE_REF = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"

# FinOps Config
FINOPS_DATASET_ID = os.getenv("FINOPS_DATASET_ID", "finops")
FINOPS_TABLE_ID = os.getenv("FINOPS_TABLE_ID", "ai_usage")
FINOPS_TABLE_REF = f"{PROJECT_ID}.{FINOPS_DATASET_ID}.{FINOPS_TABLE_ID}"

server = Server("analytics-mcp")

try:
    bq_location = os.getenv("BQ_LOCATION", "europe-west1")
    client = bigquery.Client(project=PROJECT_ID, location=bq_location)
except Exception as e:
    logger.warning(f"Failed to initialize BigQuery client: {e}")
    client = None


# Note: Dataset for FinOps logic is now managed by Terraform in bigquery.tf
# Analytics MCP only requires roles/bigquery.dataEditor and roles/bigquery.jobUser

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_top_market_skills",
            description="Permet de récupérer les compétences les plus demandées sur le marché pour une catégorie de métier spécifique (ex: Data Engineer, DevOps).",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "La catégorie métier Zenika à cibler."},
                    "limit": {"type": "integer", "description": "Nombre de résultats à remonter.", "default": 10}
                },
                "required": ["category"]
            }
        ),
        Tool(
            name="get_market_demand_volume",
            description="Permet de connaître le volume d'offres d'emploi actuelles pour une catégorie métier afin d'évaluer la tension du marché.",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "La catégorie métier Zenika."}
                },
                "required": ["category"]
            }
        ),
        Tool(
            name="log_ai_consumption",
            description="Enregistre la consommation de tokens d'un appel à l'IA pour le suivi FinOps et l'auditabilité.",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_email": {"type": "string", "description": "Email de l'utilisateur ayant lancé la commande."},
                    "action": {"type": "string", "description": "L'action ou l'outil ayant entraîné le coût (ex: 'analyze_cv', 'agent_query')."},
                    "model": {"type": "string", "description": "Le modèle IA utilisé (ex: 'gemini-3-flash-preview')."},
                    "input_tokens": {"type": "integer", "description": "Nombre de tokens en entrée."},
                    "output_tokens": {"type": "integer", "description": "Nombre de tokens en sortie."},
                    "unit_cost": {"type": "number", "description": "Coût unitaire estimé (optionnel)."},
                    "is_batch": {"type": "boolean", "description": "Si true, le coût sera divisé par 2 (Vertex AI Batch).", "default": False},
                    "metadata": {"type": "object", "description": "Métadonnées additionnelles au format JSON."}
                },
                "required": ["user_email", "action", "model", "input_tokens", "output_tokens"]
            }
        ),
        Tool(
            name="get_finops_report",
            description="Génère un rapport de consommation FinOps par utilisateur ou par action sur une période donnée.",
            inputSchema={
                "type": "object",
                "properties": {
                    "period": {"type": "string", "enum": ["daily", "weekly", "monthly"], "default": "daily"},
                    "user_email": {"type": "string", "description": "Filtrer pour un utilisateur spécifique."}
                }
            }
        ),
        Tool(
            name="get_aiops_dashboard_data",
            description="Récupère l'ensemble des indicateurs AIOps et FinOps pour le dashboard : consommation mensuelle, évolution journalière, et tops utilisateurs.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="detect_usage_anomalies",
            description="Détecte les utilisateurs dépassant un seuil de tokens/heure (anomaly detection FinOps). Utile pour identifier les comportements anormaux (exfiltration de données via flood de requêtes LLM).",
            inputSchema={
                "type": "object",
                "properties": {
                    "threshold_tokens_per_hour": {
                        "type": "integer",
                        "description": "Seuil de tokens par heure déclenchant l'alerte. Défaut: 50000.",
                        "default": 50000
                    },
                    "hours_back": {
                        "type": "integer",
                        "description": "Fenêtre d'analyse en heures (1 = dernière heure). Défaut: 1.",
                        "default": 1
                    }
                }
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "get_top_market_skills":
            return await handle_get_top_market_skills(arguments, client, TABLE_REF)
        elif name == "get_market_demand_volume":
            return await handle_get_market_demand_volume(arguments, client, TABLE_REF)
        elif name == "log_ai_consumption":
            return await handle_log_ai_consumption(arguments, client, FINOPS_TABLE_REF)
        elif name == "get_finops_report":
            return await handle_get_finops_report(arguments, client, PROJECT_ID, FINOPS_DATASET_ID, FINOPS_TABLE_REF)
        elif name == "get_aiops_dashboard_data":
            return await handle_get_aiops_dashboard_data(get_aiops_dashboard_data_internal)
        elif name == "detect_usage_anomalies":
            return await handle_detect_usage_anomalies(arguments, client, FINOPS_TABLE_REF)
        else:
            return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]
    except Exception as e:
        logger.exception(f"Error in analytics-mcp tool call '{name}'")
        return [TextContent(type="text", text=json.dumps({"error": str(e), "tool": name, "status": "failure"}))]


async def get_aiops_dashboard_data_internal():
    # 1. Monthly Summary (Current vs Last)
    query_monthly = f"""
        SELECT 
            DATE_TRUNC(DATE(timestamp), MONTH) as month,
            SUM((input_tokens * IFNULL(p.input_cost_per_token, 0.000000075) + output_tokens * IFNULL(p.output_cost_per_token, 0.0000003)) * IF(IFNULL(t.is_batch, FALSE), 0.5, 1.0)) as cost,
            COUNT(*) as requests
        FROM `{FINOPS_TABLE_REF}` t
        LEFT JOIN `{PROJECT_ID}.{FINOPS_DATASET_ID}.model_pricing` p ON t.model = p.model_name
        WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 60 DAY)
        GROUP BY 1 ORDER BY 1 DESC LIMIT 2
    """

    # 2. Daily Evolution (Last 30 Days)
    query_daily = f"""
        SELECT 
            DATE(timestamp) as day,
            SUM((input_tokens * IFNULL(p.input_cost_per_token, 0.000000075) + output_tokens * IFNULL(p.output_cost_per_token, 0.0000003)) * IF(IFNULL(t.is_batch, FALSE), 0.5, 1.0)) as cost,
            COUNT(*) as requests
        FROM `{FINOPS_TABLE_REF}` t
        LEFT JOIN `{PROJECT_ID}.{FINOPS_DATASET_ID}.model_pricing` p ON t.model = p.model_name
        WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
        GROUP BY 1 ORDER BY 1 ASC
    """

    # 3. Top Users by Count
    query_top_count = f"""
        SELECT user_email, COUNT(*) as count
        FROM `{FINOPS_TABLE_REF}`
        GROUP BY 1 ORDER BY 2 DESC LIMIT 10
    """

    # 4. Top Users by Cost
    query_top_cost = f"""
        SELECT user_email, SUM((input_tokens * IFNULL(p.input_cost_per_token, 0.000000075) + output_tokens * IFNULL(p.output_cost_per_token, 0.0000003)) * IF(IFNULL(t.is_batch, FALSE), 0.5, 1.0)) as cost
        FROM `{FINOPS_TABLE_REF}` t
        LEFT JOIN `{PROJECT_ID}.{FINOPS_DATASET_ID}.model_pricing` p ON t.model = p.model_name
        GROUP BY 1 ORDER BY 2 DESC LIMIT 10
    """

    # 5. Répartition par Action (outil/usage LLM)
    query_top_actions = f"""
        SELECT action, COUNT(*) as count
        FROM `{FINOPS_TABLE_REF}`
        GROUP BY 1 ORDER BY 2 DESC LIMIT 15
    """

    # 6. Répartition par Modèle IA
    query_top_models = f"""
        SELECT model, COUNT(*) as count
        FROM `{FINOPS_TABLE_REF}`
        GROUP BY 1 ORDER BY 2 DESC LIMIT 10
    """

    # 7. Table des Prix (Reference)
    query_pricing = f"""
        SELECT model_name, input_cost_per_token, output_cost_per_token
        FROM `{PROJECT_ID}.{FINOPS_DATASET_ID}.model_pricing`
        ORDER BY input_cost_per_token DESC, model_name ASC
    """

    # Helper pour la requête
    def fetch_data(q):
        if not client:
            raise Exception("BigQuery client is not initialized.")
        return [dict(row) for row in client.query(q).result()]

    import asyncio

    # Exécution parallèle
    monthly_res, daily_res, top_count_res, top_cost_res, top_actions_res, top_models_res, pricing_res = await asyncio.gather(
        asyncio.to_thread(fetch_data, query_monthly),
        asyncio.to_thread(fetch_data, query_daily),
        asyncio.to_thread(fetch_data, query_top_count),
        asyncio.to_thread(fetch_data, query_top_cost),
        asyncio.to_thread(fetch_data, query_top_actions),
        asyncio.to_thread(fetch_data, query_top_models),
        asyncio.to_thread(fetch_data, query_pricing)
    )

    # Formatting
    for r in monthly_res:
        if 'month' in r and r['month']:
            r['month'] = r['month'].isoformat()
    for r in daily_res:
        if 'day' in r and r['day']:
            r['day'] = r['day'].isoformat()

    return {
        "monthly": monthly_res,
        "daily": daily_res,
        "top_users_count": top_count_res,
        "top_users_cost": top_cost_res,
        "top_actions": top_actions_res,
        "top_models": top_models_res,
        "pricing_table": pricing_res,
        "generated_at": datetime.now(timezone.utc).isoformat()
    }


async def main():
    """Main entry point for the MCP server when run directly over stdio."""
    from mcp.server import InitializationOptions
    from mcp.server.stdio import stdio_server
    options = InitializationOptions(
        server_name="analytics-mcp",
        server_version="1.0.0",
        capabilities={}
    )
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options)

if __name__ == "__main__":
    asyncio.run(main())
