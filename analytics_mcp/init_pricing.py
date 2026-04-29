import os
from google.cloud import bigquery
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_gcp_project_id() -> str:
    pid = os.getenv("GCP_PROJECT_ID", "").strip()
    if pid and pid not in ("your-gcp-project-id", "YOUR_GCP_PROJECT_ID"):
        return pid
    try:
        import google.auth
        _, project = google.auth.default()
        if project:
            return project
    except Exception:
        pass
    return ""


# Pricing data — source of truth for model costs.
# Descriptions and field modes are owned by Terraform (bigquery.tf).
# This script only upserts rows; it must NOT recreate the table schema.
PRICING_ROWS = [
    ("gemini-3.1-pro-preview",        0.00000125,  0.00000375),
    ("gemini-3-pro-preview",           0.00000125,  0.00000375),
    ("gemini-2.5-pro",                 0.00000125,  0.00000375),
    ("gemini-1.5-pro",                 0.00000125,  0.00000375),
    ("gemini-embedding-001",           0.00000000,  0.00000000),
    ("gemini-3.1-flash-lite-preview",  0.000000075, 0.00000030),
    ("gemini-3-flash-preview",         0.000000075, 0.00000030),
    ("gemini-2.5-flash",               0.000000075, 0.00000030),
    ("gemini-1.5-flash",               0.000000075, 0.00000030),
]


def init_pricing_table() -> None:
    """
    Upsert pricing rows into the model_pricing table using a MERGE statement.
    The table DDL (schema, field modes, descriptions) is exclusively managed
    by Terraform — this function must never run CREATE OR REPLACE TABLE.
    """
    project_id = get_gcp_project_id()
    if not project_id:
        logger.error("No GCP Project ID found.")
        raise ValueError("GCP_PROJECT_ID is not set or could not be detected.")

    bq_location = os.getenv("BQ_LOCATION", "europe-west1")
    client = bigquery.Client(project=project_id, location=bq_location)

    finops_dataset_id = os.getenv("FINOPS_DATASET_ID", "finops")
    table_ref = f"`{project_id}.{finops_dataset_id}.model_pricing`"

    # Build a VALUES clause from PRICING_ROWS
    values_clause = ",\n    ".join(
        f"('{name}', {inp}, {out})" for name, inp, out in PRICING_ROWS
    )

    merge_query = f"""
MERGE {table_ref} AS target
USING (
  SELECT model_name, input_cost_per_token, output_cost_per_token
  FROM UNNEST([
    STRUCT<model_name STRING, input_cost_per_token FLOAT64, output_cost_per_token FLOAT64>
    {values_clause}
  ])
) AS source
ON target.model_name = source.model_name
WHEN MATCHED THEN
  UPDATE SET
    input_cost_per_token  = source.input_cost_per_token,
    output_cost_per_token = source.output_cost_per_token
WHEN NOT MATCHED THEN
  INSERT (model_name, input_cost_per_token, output_cost_per_token)
  VALUES (source.model_name, source.input_cost_per_token, source.output_cost_per_token)
"""

    try:
        client.query(merge_query).result()
        logger.info(f"Successfully upserted {len(PRICING_ROWS)} rows into {table_ref}.")
    except Exception as e:
        logger.error(f"Failed to upsert pricing data: {e}")
        raise


if __name__ == "__main__":
    init_pricing_table()
