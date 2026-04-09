resource "google_bigquery_dataset" "market_data" {
  dataset_id                  = "market_data"
  friendly_name               = "Market Data Dataset"
  description                 = "Dataset containing job market data and related insights for LLM queries."
  location                    = "europe-west1"
  default_table_expiration_ms = null # Tables don't expire 
}

resource "google_bigquery_table" "job_offers" {
  dataset_id          = google_bigquery_dataset.market_data.dataset_id
  table_id            = "job_offers"
  description         = "Flattened job offers table, optimized for Agentic MCP LLM consumption."
  deletion_protection = false

  schema = <<EOF
[
  {
    "name": "offer_id",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "The unique identifier of the job offer from France Travail."
  },
  {
    "name": "job_title",
    "type": "STRING",
    "mode": "NULLABLE",
    "description": "Original job title as published in the offer."
  },
  {
    "name": "zenika_category",
    "type": "STRING",
    "mode": "NULLABLE",
    "description": "Corresponding Zenika business category, such as 'Data Engineer' or 'Développeur'."
  },
  {
    "name": "rome_code",
    "type": "STRING",
    "mode": "NULLABLE",
    "description": "ROME code attached to this job offer, defining the profession category."
  },
  {
    "name": "skills",
    "type": "STRING",
    "mode": "REPEATED",
    "description": "Flat list of professional skills extracted natively from the ROME reference for this job."
  },
  {
    "name": "creation_date",
    "type": "TIMESTAMP",
    "mode": "NULLABLE",
    "description": "Timestamp indicating when the job offer was created or published."
  },
  {
    "name": "description",
    "type": "STRING",
    "mode": "NULLABLE",
    "description": "Full text description of the job offer."
  },
  {
    "name": "agency_id",
    "type": "STRING",
    "mode": "NULLABLE",
    "description": "The identifier of the partner agency handling the job offer."
  },
  {
    "name": "agency_name",
    "type": "STRING",
    "mode": "NULLABLE",
    "description": "The name of the partner agency handling the job offer."
  }
]
EOF
}
