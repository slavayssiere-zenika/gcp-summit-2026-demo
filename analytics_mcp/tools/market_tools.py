# flake8: noqa: E501, E701, E302, F541, E306
import json
from google.cloud import bigquery
from mcp.types import TextContent

async def handle_get_top_market_skills(arguments: dict, client, TABLE_REF) -> list[TextContent]:
    category = arguments.get("category", "")
    limit = arguments.get("limit", 10)
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

async def handle_get_market_demand_volume(arguments: dict, client, TABLE_REF) -> list[TextContent]:
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
