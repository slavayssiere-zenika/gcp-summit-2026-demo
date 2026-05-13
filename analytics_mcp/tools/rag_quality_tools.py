import json
import logging
from datetime import datetime, timezone

from google.cloud import bigquery
from mcp.types import TextContent

logger = logging.getLogger(__name__)

RAG_QUALITY_TABLE_ID = "rag_quality_snapshots"


async def handle_log_rag_quality_snapshot(
    arguments: dict,
    client,
    project_id: str,
    finops_dataset_id: str,
) -> list[TextContent]:
    """
    Persiste un snapshot de qualité RAG dans BigQuery (table rag_quality_snapshots).

    Appelé automatiquement par manage_env.py après chaque calibrage (rag-calibrate).
    Alimente le dashboard AIOps et la gate de qualité données.
    """
    try:
        env = arguments.get("env", "unknown")
        embedding_model = arguments.get("embedding_model", "unknown")
        nb_cases = int(arguments.get("nb_cases", 0))
        nb_cases_ok = int(arguments.get("nb_cases_ok", 0))
        global_recall = float(arguments.get("global_recall", 0.0))
        global_mrr = float(arguments.get("global_mrr", 0.0))
        cases_detail = arguments.get("cases_detail", [])  # list[dict]
        triggered_by = arguments.get("triggered_by", "manual")  # "manual" | "model_change" | "deploy"

        table_ref = f"{project_id}.{finops_dataset_id}.{RAG_QUALITY_TABLE_ID}"
        row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "env": env,
            "embedding_model": embedding_model,
            "nb_cases": nb_cases,
            "nb_cases_ok": nb_cases_ok,
            "global_recall_at_5": global_recall,
            "global_mrr": global_mrr,
            "cases_detail": json.dumps(cases_detail),
            "triggered_by": triggered_by,
        }

        errors = client.insert_rows_json(table_ref, [row])
        if errors:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": f"BigQuery insert errors: {errors}",
            }))]

        return [TextContent(type="text", text=json.dumps({
            "success": True,
            "env": env,
            "global_recall_at_5": global_recall,
            "nb_cases_ok": nb_cases_ok,
            "nb_cases": nb_cases,
        }))]

    except Exception as e:
        logger.exception("[rag_quality] Erreur lors de l'insertion du snapshot RAG")
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]


async def handle_get_rag_quality_history(
    arguments: dict,
    client,
    project_id: str,
    finops_dataset_id: str,
) -> list[TextContent]:
    """
    Retourne l'historique des snapshots RAG pour un env donné.
    Utilisé par le dashboard AIOps pour afficher la tendance Recall@K.
    """
    try:
        env = arguments.get("env", "prd")
        days_back = int(arguments.get("days_back", 30))
        table_ref = f"{project_id}.{finops_dataset_id}.{RAG_QUALITY_TABLE_ID}"

        query = f"""
            SELECT
                timestamp,
                env,
                embedding_model,
                nb_cases,
                nb_cases_ok,
                global_recall_at_5,
                global_mrr,
                triggered_by
            FROM `{table_ref}`
            WHERE env = @env
              AND timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @days_back DAY)
            ORDER BY timestamp DESC
            LIMIT 100
        """
        job_config = bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("env", "STRING", env),
            bigquery.ScalarQueryParameter("days_back", "INT64", days_back),
        ])
        rows = [dict(r) for r in client.query(query, job_config=job_config).result()]
        for r in rows:
            if "timestamp" in r and r["timestamp"]:
                r["timestamp"] = r["timestamp"].isoformat()

        return [TextContent(type="text", text=json.dumps({"success": True, "history": rows}))]

    except Exception as e:
        logger.exception("[rag_quality] Erreur lors de la lecture de l'historique RAG")
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]
