# flake8: noqa: E501, E701, E302, F541, E306
import json
import asyncio
from datetime import datetime, timezone
from google.cloud import bigquery
from mcp.types import TextContent


async def handle_log_ai_consumption(arguments: dict, client, FINOPS_TABLE_REF) -> list[TextContent]:
    user_email = arguments.get("user_email")
    if not user_email:
        return [TextContent(type="text", text="Error: user_email is required and cannot be null/empty.")]

    row_to_insert = [
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_email": user_email,
            "action": arguments["action"],
            "model": arguments["model"],
            "input_tokens": arguments["input_tokens"],
            "output_tokens": arguments["output_tokens"],
            "unit_cost": arguments.get("unit_cost"),
            "is_batch": arguments.get("is_batch", False),
            "metadata": json.dumps(arguments.get("metadata", {}))
        }
    ]
    errors = client.insert_rows_json(FINOPS_TABLE_REF, row_to_insert)
    if errors == []:
        return [TextContent(type="text", text="Consumption logged successfully.")]
    else:
        return [TextContent(type="text", text=f"Errors occurred while logging consumption: {errors}")]


async def handle_get_finops_report(arguments: dict, client, PROJECT_ID, FINOPS_DATASET_ID, FINOPS_TABLE_REF) -> list[TextContent]:
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
    query = f"""
        SELECT
            {date_col} as period,
            user_email,
            action,
            SUM(input_tokens) as total_input,
            SUM(output_tokens) as total_output,
            ROUND(SUM((input_tokens * IFNULL(p.input_cost_per_token, 0.000000075) + output_tokens * IFNULL(p.output_cost_per_token, 0.0000003)) * IF(IFNULL(t.is_batch, FALSE), 0.5, 1.0)), 6) as estimated_cost_usd
        FROM `{FINOPS_TABLE_REF}` t
        LEFT JOIN `{PROJECT_ID}.{FINOPS_DATASET_ID}.model_pricing` p ON t.model = p.model_name
        {where_clause}
        GROUP BY 1, 2, 3
        ORDER BY 1 DESC, 5 DESC
    """
    job_config = bigquery.QueryJobConfig(query_parameters=params)
    query_job = client.query(query, job_config=job_config)
    results = query_job.result()
    data = [dict(row) for row in results]
    for d in data:
        if 'period' in d and hasattr(d['period'], 'isoformat'):
            d['period'] = d['period'].isoformat()
    return [TextContent(type="text", text=json.dumps(data))]


async def handle_detect_usage_anomalies(arguments: dict, client, FINOPS_TABLE_REF) -> list[TextContent]:
    threshold = int(arguments.get("threshold_tokens_per_hour", 50000))
    hours_back = int(arguments.get("hours_back", 1))
    query = f"""
        SELECT
            user_email,
            SUM(input_tokens + output_tokens) AS total_tokens,
            COUNT(*) AS request_count,
            MIN(timestamp) AS window_start,
            MAX(timestamp) AS window_end
        FROM `{FINOPS_TABLE_REF}`
        WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @hours_back HOUR)
        GROUP BY user_email
        HAVING total_tokens > @threshold
        ORDER BY total_tokens DESC
        LIMIT 20
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("threshold", "INT64", threshold),
            bigquery.ScalarQueryParameter("hours_back", "INT64", hours_back),
        ]
    )
    query_job = await asyncio.to_thread(client.query, query, job_config)
    results = await asyncio.to_thread(query_job.result)
    anomalies = []
    for row in results:
        anomalies.append({
            "user_email": row.user_email,
            "total_tokens": row.total_tokens,
            "request_count": row.request_count,
            "window_start": row.window_start.isoformat() if row.window_start else None,
            "window_end": row.window_end.isoformat() if row.window_end else None,
            "threshold_exceeded_by": row.total_tokens - threshold,
        })
    return [TextContent(type="text", text=json.dumps({
        "anomalies": anomalies,
        "threshold_tokens_per_hour": threshold,
        "hours_back": hours_back,
        "anomaly_count": len(anomalies),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }))]


async def handle_get_aiops_dashboard_data(get_aiops_dashboard_data_internal) -> list[TextContent]:
    data = await get_aiops_dashboard_data_internal()
    return [TextContent(type="text", text=json.dumps(data))]
