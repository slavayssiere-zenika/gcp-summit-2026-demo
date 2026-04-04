import asyncio
import json
import os
import logging
import contextvars
from mcp.server import Server
from mcp.types import Tool, TextContent
from google.cloud import bigquery

# Standard context var for MCP auth
mcp_auth_header_var = contextvars.ContextVar("mcp_auth_header", default=None)

logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s', handlers=[logging.NullHandler()])

# Config
PROJECT_ID = os.getenv("GCP_PROJECT_ID", "slavayssiere-zenika")
DATASET_ID = os.getenv("DATASET_ID", "market_data")
TABLE_ID = os.getenv("TABLE_ID", "job_offers")
TABLE_REF = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"

server = Server("market-mcp")

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
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    client = bigquery.Client(project=PROJECT_ID)

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

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        return [TextContent(type="text", text=f"Error executing BigQuery: {str(e)}")]

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
