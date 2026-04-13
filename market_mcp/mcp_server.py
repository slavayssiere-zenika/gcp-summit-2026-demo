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
            name="get_infrastructure_topology",
            description="Récupère la topologie dynamique de l'infrastructure en analysant les traces GCP Cloud Trace. Retourne un graphe de dépendances entre services.",
            inputSchema={
                "type": "object",
                "properties": {
                    "hours_lookback": {"type": "integer", "description": "Nombre d'heures d'historique à analyser (défaut 1).", "default": 1}
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

        elif name == "get_infrastructure_topology":
            hours = arguments.get("hours_lookback", 1)
            data = await get_infrastructure_topology(hours)
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
    
    # Helper pour la requête
    def fetch_data(q):
        return [dict(row) for row in client.query(q).result()]
        
    import asyncio
    
    # Exécution parallèle
    monthly_res, daily_res, top_count_res, top_cost_res = await asyncio.gather(
        asyncio.to_thread(fetch_data, query_monthly),
        asyncio.to_thread(fetch_data, query_daily),
        asyncio.to_thread(fetch_data, query_top_count),
        asyncio.to_thread(fetch_data, query_top_cost)
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
        "generated_at": datetime.utcnow().isoformat()
    }

async def get_infrastructure_topology(hours_lookback: int = 1) -> dict:
    """Standalone logic to fetch infrastructure topology from GCP Cloud Trace."""
    try:
        from google.cloud import trace_v1
        v1_client = trace_v1.TraceServiceClient()
        
        # Time range
        now = time.time()
        start_time = now - (hours_lookback * 3600)
        
        start_ts = Timestamp()
        start_ts.FromSeconds(int(start_time))
        end_ts = Timestamp()
        end_ts.FromSeconds(int(now))
        
        request = trace_v1.ListTracesRequest(
            project_id=PROJECT_ID,
            start_time=start_ts,
            end_time=end_ts,
            view=trace_v1.ListTracesRequest.ViewType.COMPLETE
        )
        import asyncio
        traces_pager = await asyncio.to_thread(v1_client.list_traces, request=request)
        
        nodes_data = {} # name -> id for dedup
        links = []
        seen_links = set()
        
        for i, trace_obj in enumerate(traces_pager):
            if i >= 500: # Limit the number of traces processed to avoid timeout
                break
            
            # 0. Check if we should skip this trace (health/metrics)
            skip_trace = False
            for span in trace_obj.spans:
                labels = span.labels if hasattr(span, 'labels') else {}
                url = labels.get("/http/url", "")
                if "/health" in url or "/metrics" in url:
                    skip_trace = True
                    break
            
            if skip_trace:
                continue

            span_to_service = {}
            # 1. First pass: map all spans to services
            for span in trace_obj.spans:
                s_id = str(span.span_id)
                service_name = "unknown"
                node_type = "unknown"
                node_label = "unknown"
                labels = span.labels if hasattr(span, 'labels') else {}
                
                # Priority extraction
                if "db.system" in labels:
                    sys = labels["db.system"]
                    if sys == "postgresql":
                        service_name = labels.get("db.name", "alloydb")
                        node_type = "alloydb"
                        node_label = f"AlloyDB ({service_name})"
                    elif sys == "redis":
                        service_name = "redis-cache"
                        node_type = "redis"
                        node_label = "Redis Cache"
                    else:
                        service_name = sys
                        node_type = "database"
                        node_label = sys
                elif "messaging.system" in labels:
                    sys = labels["messaging.system"]
                    service_name = labels.get("messaging.destination", sys)
                    node_type = "pubsub"
                    node_label = f"Pub/Sub ({service_name})"
                elif "g.co/r/cloud_run_revision/service_name" in labels:
                    service_name = labels["g.co/r/cloud_run_revision/service_name"]
                elif "service.name" in labels:
                    service_name = labels["service.name"]
                elif "/http/host" in labels:
                    h = labels["/http/host"]
                    import re
                    if re.match(r'^\d{1,3}(\.\d{1,3}){3}(:\d+)?$', h):
                        service_name = h
                    else:
                        service_name = h.split('.')[0]
                elif "/http/url" in labels:
                    from urllib.parse import urlparse
                    nl = urlparse(labels["/http/url"]).netloc
                    import re
                    if re.match(r'^\d{1,3}(\.\d{1,3}){3}(:\d+)?$', nl):
                        service_name = nl
                    else:
                        service_name = nl.split('.')[0]
                        
                if node_type == "unknown" and service_name != "unknown":
                    if "169.254" in service_name or service_name == "169":
                        node_type = "metadata"
                        node_label = "GCP Metadata Server"
                    elif "127." in service_name or service_name == "127":
                        node_type = "service"
                        node_label = f"Local Proxy ({service_name})"
                    elif service_name == "api" or "internal" in service_name:
                        node_type = "lb_private"
                        node_label = "LB Privé (api.internal.zenika)"
                    elif service_name == "dev" or ".fr" in service_name:
                        node_type = "lb_public"
                        node_label = "LB Public"
                    elif "pubsub" in service_name:
                        node_type = "pubsub"
                        node_label = "Google Pub/Sub"
                    elif "api" in service_name or "mcp" in service_name or "frontend" in service_name or "agent" in service_name:
                        node_type = "cloud_run"
                        node_label = service_name
                    else:
                        node_type = "service"
                        node_label = service_name
                
                span_to_service[s_id] = service_name
                if service_name != "unknown":
                    nodes_data[service_name] = {"id": service_name, "type": node_type, "label": node_label}
            
            # 2. Second pass: find links using normalized IDs
            for span in trace_obj.spans:
                p_id = str(span.parent_span_id) if span.parent_span_id else None
                s_id = str(span.span_id)
                
                if p_id and p_id in span_to_service:
                    parent_service = span_to_service[p_id]
                    child_service = span_to_service[s_id]
                    
                    if parent_service != child_service and parent_service != "unknown" and child_service != "unknown":
                        link_key = f"{parent_service}->{child_service}"
                        if link_key not in seen_links:
                            links.append({"source": parent_service, "target": child_service})
                            seen_links.add(link_key)
        
        # 3. Filter nodes: Keep Zenika services OR nodes involved in links
        zenika_keywords = ["api", "mcp", "agent", "frontend", "market", "users", "items", "cv", "competencies"]
        final_nodes = []
        linked_service_names = set()
        for l in links:
            linked_service_names.add(l["source"])
            linked_service_names.add(l["target"])
            
        for name, data in nodes_data.items():
            is_zenika = any(k in name.lower() for k in zenika_keywords)
            is_linked = name in linked_service_names
            if is_zenika or is_linked:
                final_nodes.append(data)
        
        return {
            "nodes": final_nodes,
            "links": links
        }
    except Exception as e:
        logger.exception(f"Failed to fetch topology from GCP: {e}")
        raise e

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
