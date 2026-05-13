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

  deletion_protection = terraform.workspace == "prd" ? true : false

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
  },
  {
    "name": "is_batch",
    "type": "BOOLEAN",
    "mode": "NULLABLE",
    "description": "Indique si l'appel a ete realise via Vertex AI Batch"
  }
]
EOF
}

# Permissions pour le service analytics_mcp
resource "google_bigquery_dataset_iam_member" "analytics_editor" {
  dataset_id = google_bigquery_dataset.finops.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.analytics_sa.email}"
}

resource "google_project_iam_member" "analytics_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.analytics_sa.email}"
}

resource "google_bigquery_table" "data_quality_history" {
  dataset_id          = google_bigquery_dataset.finops.dataset_id
  table_id            = "data_quality_history"
  deletion_protection = terraform.workspace == "prd" ? true : false

  time_partitioning {
    type  = "DAY"
    field = "computed_at"
  }

  schema = <<EOF
[
  {"name":"computed_at","type":"TIMESTAMP","mode":"REQUIRED","description":"Horodatage du snapshot"},
  {"name":"total_cvs","type":"INTEGER","mode":"REQUIRED","description":"Nombre total de CVs"},
  {"name":"users_with_cv","type":"INTEGER","mode":"REQUIRED","description":"Consultants avec CV"},
  {"name":"score","type":"INTEGER","mode":"REQUIRED","description":"Score global 0-100"},
  {"name":"grade","type":"STRING","mode":"REQUIRED","description":"Grade A/B/C/D"},
  {"name":"embedding_pct","type":"FLOAT","mode":"REQUIRED","description":"Proportion CVs avec embedding sémantique (0.0→1.0)"},
  {"name":"missions_pct","type":"FLOAT","mode":"REQUIRED","description":"Proportion CVs avec missions (0.0→1.0)"},
  {"name":"competencies_pct","type":"FLOAT","mode":"REQUIRED","description":"Proportion CVs avec compétences extraites (0.0→1.0)"},
  {"name":"summary_pct","type":"FLOAT","mode":"REQUIRED","description":"Proportion CVs avec summary (0.0→1.0)"},
  {"name":"current_role_pct","type":"FLOAT","mode":"REQUIRED","description":"Proportion CVs avec current_role (0.0→1.0)"},
  {"name":"competency_assignment_pct","type":"FLOAT","mode":"REQUIRED","description":"Proportion consultants avec compétences assignées (0.0→1.0)"},
  {"name":"ai_scoring_pct","type":"FLOAT","mode":"REQUIRED","description":"Proportion consultants avec scoring IA suffisant (0.0→1.0)"},
  {"name":"processing_errors_pct","type":"FLOAT","mode":"REQUIRED","description":"Proportion CVs sans erreurs de post-traitement (0.0→1.0)"},
  {"name":"issues_count","type":"INTEGER","mode":"REQUIRED","description":"Nombre d'anomalies détectées"},
  {"name":"trigger",             "type":"STRING",  "mode":"REQUIRED", "description":"scheduler | batch_completed | manual"},
  {"name":"rag_recall_at_5",     "type":"FLOAT",   "mode":"NULLABLE", "description":"Recall@5 global du golden dataset RAG (0.0-1.0). Null si pas encore calibre."},
  {"name":"rag_nb_cases",        "type":"INTEGER", "mode":"NULLABLE", "description":"Nombre de cas golden RAG"},
  {"name":"rag_nb_cases_ok",     "type":"INTEGER", "mode":"NULLABLE", "description":"Cas golden calibres avec expected_user_ids"},
  {"name":"rag_embedding_model", "type":"STRING",  "mode":"NULLABLE", "description":"Modele d embedding utilise lors du calibrage"}
]
EOF
}

resource "google_bigquery_table" "model_pricing" {
  dataset_id = google_bigquery_dataset.finops.dataset_id
  table_id   = "model_pricing"

  deletion_protection = terraform.workspace == "prd" ? true : false

  schema = <<EOF
[
  {
    "name": "model_name",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Nom exact du modele (ex: gemini-3.1-pro-preview)"
  },
  {
    "name": "input_cost_per_token",
    "type": "FLOAT",
    "mode": "REQUIRED",
    "description": "Cout unitaire d'un token en entree"
  },
  {
    "name": "output_cost_per_token",
    "type": "FLOAT",
    "mode": "REQUIRED",
    "description": "Cout unitaire d'un token en sortie"
  }
]
EOF
}

resource "google_bigquery_table" "rag_quality_snapshots" {
  dataset_id          = google_bigquery_dataset.finops.dataset_id
  table_id            = "rag_quality_snapshots"
  deletion_protection = terraform.workspace == "prd" ? true : false

  time_partitioning {
    type  = "DAY"
    field = "timestamp"
  }

  schema = <<EOF
[
  {"name":"timestamp",         "type":"TIMESTAMP", "mode":"REQUIRED", "description":"Horodatage du calibrage"},
  {"name":"env",               "type":"STRING",    "mode":"REQUIRED", "description":"Environnement : dev | uat | prd"},
  {"name":"embedding_model",   "type":"STRING",    "mode":"REQUIRED", "description":"Modele d embedding utilise"},
  {"name":"nb_cases",          "type":"INTEGER",   "mode":"REQUIRED", "description":"Nombre de cas golden evalues"},
  {"name":"nb_cases_ok",       "type":"INTEGER",   "mode":"REQUIRED", "description":"Cas dont Recall@5 >= seuil"},
  {"name":"global_recall_at_5","type":"FLOAT",     "mode":"REQUIRED", "description":"Recall@5 global (moyenne)"},
  {"name":"global_mrr",        "type":"FLOAT",     "mode":"NULLABLE", "description":"MRR global (moyenne)"},
  {"name":"cases_detail",      "type":"JSON",      "mode":"NULLABLE", "description":"Detail par cas [{id, recall, mrr}]"},
  {"name":"triggered_by",      "type":"STRING",    "mode":"REQUIRED", "description":"Origine : manual | model_change | deploy"}
]
EOF
}

# Export des logs HTTP Cloud Run vers BigQuery pour Looker Studio
resource "google_logging_project_sink" "http_requests_bq" {
  name        = "http-requests-to-bq-${terraform.workspace}"
  description = "Export Cloud Run HTTP requests to BigQuery dataset finops_${terraform.workspace}"
  destination = "bigquery.googleapis.com/projects/${var.project_id}/datasets/${google_bigquery_dataset.finops.dataset_id}"

  # Filtrer uniquement les logs d'accès HTTP de Cloud Run
  filter = "resource.type=\"cloud_run_revision\" AND httpRequest.requestMethod!=\"\" AND severity>=DEFAULT"

  unique_writer_identity = true
}

resource "google_project_iam_member" "log_sink_bq_writer" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = google_logging_project_sink.http_requests_bq.writer_identity
}
