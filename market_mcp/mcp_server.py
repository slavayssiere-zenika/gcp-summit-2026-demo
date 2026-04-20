import asyncio
import json
import os
import logging
import contextvars
from datetime import datetime
from mcp.server import Server
from mcp.types import Tool, TextContent
from google.cloud import bigquery
from google.protobuf.timestamp_pb2 import Timestamp
import time
from google.cloud import logging_v2 as logging_cloud
from google.cloud import run_v2

# Standard context var for MCP auth
mcp_auth_header_var = contextvars.ContextVar("mcp_auth_header", default=None)

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Config
def get_gcp_project_id():
    pid = os.getenv("GCP_PROJECT_ID")
    if pid:
        return pid
    try:
        import google.auth
        _, project = google.auth.default()
        if project:
            return project
    except Exception:
        pass
    return "slavayssiere-sandbox-462015"


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
DATASET_ID = os.getenv("DATASET_ID", "market_data")
TABLE_ID = os.getenv("TABLE_ID", "job_offers")
TABLE_REF = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"

# FinOps Config
FINOPS_DATASET_ID = os.getenv("FINOPS_DATASET_ID", "finops")
FINOPS_TABLE_ID = os.getenv("FINOPS_TABLE_ID", "ai_usage")
FINOPS_TABLE_REF = f"{PROJECT_ID}.{FINOPS_DATASET_ID}.{FINOPS_TABLE_ID}"

server = Server("market-mcp")

try:
    client = bigquery.Client(project=PROJECT_ID)
except Exception as e:
    logger.warning(f"Failed to initialize BigQuery client: {e}")
    client = None


# Note: Dataset for FinOps logic is now managed by Terraform in bigquery.tf
# Market MCP only requires roles/bigquery.dataEditor and roles/bigquery.jobUser

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
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:

    try:
        if name == "get_top_market_skills":
            category = arguments.get("category", "")
            limit = arguments.get("limit", 10)
            
            # UNNEST array in BigQuery and Group By
            query = f"""
                SELECT skill, COUNT(*) as demand_count
                FROM `{TABLE_REF}`,
                UNNEST(skills) as skill
                WHERE zenika_category = @category
                GROUP BY skill
                ORDER BY demand_count DESC
                LIMIT @limit
            """
            
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("category", "STRING", category),
                    bigquery.ScalarQueryParameter("limit", "INT64", limit)
                ]
            )
            
            query_job = client.query(query, job_config=job_config)
            results = query_job.result()
            
            data = [{"skill": row.skill, "demand_count": row.demand_count} for row in results]
            return [TextContent(type="text", text=json.dumps(data))]

        elif name == "get_market_demand_volume":
            category = arguments.get("category", "")
            
            query = f"""
                SELECT COUNT(*) as volume
                FROM `{TABLE_REF}`
                WHERE zenika_category = @category
            """
            
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("category", "STRING", category)
                ]
            )
            
            query_job = client.query(query, job_config=job_config)
            results = query_job.result()
            volume = 0
            for row in results:
                volume = row.volume
                
            data = {"category": category, "volume": volume}
            return [TextContent(type="text", text=json.dumps(data))]

        elif name == "log_ai_consumption":
            row_to_insert = [
                {
                    "timestamp": datetime.utcnow().isoformat(),
                    "user_email": arguments["user_email"],
                    "action": arguments["action"],
                    "model": arguments["model"],
                    "input_tokens": arguments["input_tokens"],
                    "output_tokens": arguments["output_tokens"],
                    "unit_cost": arguments.get("unit_cost"),
                    "metadata": json.dumps(arguments.get("metadata", {}))
                }
            ]
            
            errors = client.insert_rows_json(FINOPS_TABLE_REF, row_to_insert)
            if errors == []:
                return [TextContent(type="text", text="Consumption logged successfully.")]
            else:
                return [TextContent(type="text", text=f"Errors occurred while logging consumption: {errors}")]

        elif name == "get_finops_report":
            period = arguments.get("period", "daily")
            user_email = arguments.get("user_email")
            
            date_col = "DATE(timestamp)"
            if period == "weekly":
                date_col = "DATE_TRUNC(DATE(timestamp), WEEK)"
            elif period == "monthly":
                date_col = "DATE_TRUNC(DATE(timestamp), MONTH)"
                
            where_clause = ""
            params = []
            if user_email:
                where_clause = "WHERE user_email = @user_email"
                params.append(bigquery.ScalarQueryParameter("user_email", "STRING", user_email))
                
            # Pricing rules (Flash 1.5/2.0 standard: 0.075$ / 1M input, 0.30$ / 1M output)
            # We do the math in SQL for speed
            query = f"""
                SELECT 
                    {date_col} as period,
                    user_email,
                    action,
                    SUM(input_tokens) as total_input,
                    SUM(output_tokens) as total_output,
                    ROUND(SUM(input_tokens) * 0.000000075 + SUM(output_tokens) * 0.0000003, 6) as estimated_cost_usd
                FROM `{FINOPS_TABLE_REF}`
                {where_clause}
                GROUP BY 1, 2, 3
                ORDER BY 1 DESC, 5 DESC
            """
            
            job_config = bigquery.QueryJobConfig(query_parameters=params)
            query_job = client.query(query, job_config=job_config)
            results = query_job.result()
            
            data = [dict(row) for row in results]
            # Convert date objects to string for JSON serialization
            for d in data:
                if 'period' in d and hasattr(d['period'], 'isoformat'):
                    d['period'] = d['period'].isoformat()
                    
            return [TextContent(type="text", text=json.dumps(data))]

        elif name == "get_aiops_dashboard_data":
            data = await get_aiops_dashboard_data_internal()
            return [TextContent(type="text", text=json.dumps(data))]

        else:
            return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

    except Exception as e:
        logger.exception(f"Error in market-mcp tool call '{name}'")
        return [TextContent(type="text", text=json.dumps({
            "error": str(e),
            "tool": name,
            "status": "failure"
        }))]

async def get_aiops_dashboard_data_internal():
    # 1. Monthly Summary (Current vs Last)
    query_monthly = f"""
        SELECT 
            DATE_TRUNC(DATE(timestamp), MONTH) as month,
            SUM(input_tokens * 0.000000075 + output_tokens * 0.0000003) as cost,
            COUNT(*) as requests
        FROM `{FINOPS_TABLE_REF}`
        WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 60 DAY)
        GROUP BY 1 ORDER BY 1 DESC LIMIT 2
    """
    
    # 2. Daily Evolution (Last 30 Days)
    query_daily = f"""
        SELECT 
            DATE(timestamp) as day,
            SUM(input_tokens * 0.000000075 + output_tokens * 0.0000003) as cost,
            COUNT(*) as requests
        FROM `{FINOPS_TABLE_REF}`
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
        SELECT user_email, SUM(input_tokens * 0.000000075 + output_tokens * 0.0000003) as cost
        FROM `{FINOPS_TABLE_REF}`
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
    
    # Helper pour la requête
    def fetch_data(q):
        return [dict(row) for row in client.query(q).result()]
        
    import asyncio
    
    # Exécution parallèle
    monthly_res, daily_res, top_count_res, top_cost_res, top_actions_res, top_models_res = await asyncio.gather(
        asyncio.to_thread(fetch_data, query_monthly),
        asyncio.to_thread(fetch_data, query_daily),
        asyncio.to_thread(fetch_data, query_top_count),
        asyncio.to_thread(fetch_data, query_top_cost),
        asyncio.to_thread(fetch_data, query_top_actions),
        asyncio.to_thread(fetch_data, query_top_models)
    )

    # Formatting
    for r in monthly_res:
        if 'month' in r and r['month']: r['month'] = r['month'].isoformat()
    for r in daily_res:
        if 'day' in r and r['day']: r['day'] = r['day'].isoformat()

    return {
        "monthly": monthly_res,
        "daily": daily_res,
        "top_users_count": top_count_res,
        "top_users_cost": top_cost_res,
        "top_actions": top_actions_res,
        "top_models": top_models_res,
        "generated_at": datetime.utcnow().isoformat()
    }

async def main():
    """Main entry point for the MCP server when run directly over stdio."""
    from mcp.server.stdio import stdio_server
    from mcp.server import InitializationOptions
    options = InitializationOptions(
        server_name="market-mcp",
        server_version="1.0.0",
        capabilities={}
    )
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options)

if __name__ == "__main__":
    asyncio.run(main())
