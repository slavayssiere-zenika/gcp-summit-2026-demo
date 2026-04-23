resource "google_bigquery_dataset" "finops" {
  dataset_id                 = "finops_${terraform.workspace}"
  friendly_name              = "FinOps Observability (${terraform.workspace})"
  description                = "Dataset for AI consumption and costs tracking — env: ${terraform.workspace}"
  location                   = "europe-west1"
  delete_contents_on_destroy = false

  labels = {
    environment = terraform.workspace
    managed_by  = "terraform"
  }
}

resource "google_bigquery_table" "ai_usage" {
  dataset_id = google_bigquery_dataset.finops.dataset_id
  table_id   = "ai_usage"

  deletion_protection = false

  time_partitioning {
    type  = "DAY"
    field = "timestamp"
  }

  schema = <<EOF
[
  {
    "name": "timestamp",
    "type": "TIMESTAMP",
    "mode": "REQUIRED",
    "description": "Moment de l'appel"
  },
  {
    "name": "user_email",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Email de l'utilisateur"
  },
  {
    "name": "action",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Action ou outil appelé"
  },
  {
    "name": "model",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Modèle IA utilisé"
  },
  {
    "name": "input_tokens",
    "type": "INTEGER",
    "mode": "REQUIRED",
    "description": "Tokens en entrée"
  },
  {
    "name": "output_tokens",
    "type": "INTEGER",
    "mode": "REQUIRED",
    "description": "Tokens en sortie"
  },
  {
    "name": "unit_cost",
    "type": "FLOAT",
    "mode": "NULLABLE",
    "description": "Coût unitaire optionnel"
  },
  {
    "name": "metadata",
    "type": "JSON",
    "mode": "NULLABLE",
    "description": "Données additionnelles au format JSON"
  }
]
EOF
}

# Permissions pour le service market_mcp
resource "google_bigquery_dataset_iam_member" "market_editor" {
  dataset_id = google_bigquery_dataset.finops.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.market_sa.email}"
}

resource "google_project_iam_member" "market_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.market_sa.email}"
}
