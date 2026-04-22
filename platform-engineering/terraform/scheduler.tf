# Tâche planifiée pour l'Anomaly Detection FinOps (Run toutes les 15 minutes)

resource "google_cloud_scheduler_job" "finops_anomaly_detector" {
  name             = "finops-anomaly-detector-${terraform.workspace}"
  description      = "Trigger FinOps anomaly detection script in market-mcp to prevent denial of wallet."
  schedule         = "*/15 * * * *"
  time_zone        = "Europe/Paris"
  attempt_deadline = "320s"
  region           = var.region
  project          = var.project_id

  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_v2_service.market_mcp.uri}/admin/finops/detect"

    # Authentification via le Service Account Agent_API (ou IAM specifique si configuré)
    # Pour s'assurer que c'est une requête de confiance
    oidc_token {
      service_account_email = google_service_account.agent_router_sa.email
      audience              = google_cloud_run_v2_service.market_mcp.uri
    }
  }
}

# ==============================================================
# DLQ Drain Automatique — Pipeline CV
# Toutes les heures : remet en PENDING les CVs en erreur ou bloqués
# (STATUS=ERROR ou STATUS=QUEUED/PROCESSING depuis > 30 min)
# Le prochain /sync les republiera automatiquement dans Pub/Sub.
# ==============================================================
resource "google_cloud_scheduler_job" "dlq_drain_drive" {
  name             = "dlq-drain-drive-${terraform.workspace}"
  description      = "Drain automatique DLQ CV ingestion : reset ERROR + zombies QUEUED/PROCESSING → PENDING pour retry Pub/Sub."
  schedule         = "0 * * * *" # Toutes les heures
  time_zone        = "Europe/Paris"
  attempt_deadline = "120s"
  region           = var.region
  project          = var.project_id

  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_v2_service.drive_api.uri}/scheduled/retry-errors"

    # OIDC : le SA drive_sa appelle son propre service Cloud Run
    # Conforme AGENTS.md §4 — pas de JWT applicatif pour les tâches automatisées
    oidc_token {
      service_account_email = data.google_service_account.drive_sa.email
      audience              = google_cloud_run_v2_service.drive_api.uri
    }
  }
}

# ==============================================================
# Drive API /sync — Découverte + publication Pub/Sub des CVs
# Toutes les heures : remonte les PENDING en QUEUED dans Pub/Sub
# (Migré depuis cloudrun.tf pour cohérence d'organisation)
# ==============================================================
resource "google_cloud_scheduler_job" "drive_sync_job" {
  name             = "drive-sync-trigger-${terraform.workspace}"
  description      = "Triggers Drive API /sync every hour — discovers new Drive files and publishes PENDING CVs to Pub/Sub."
  schedule         = "0 * * * *"
  time_zone        = "Europe/Paris"
  attempt_deadline = "320s"
  region           = var.region
  project          = var.project_id

  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_v2_service.drive_api.uri}/sync"

    oidc_token {
      service_account_email = data.google_service_account.drive_sa.email
      audience              = google_cloud_run_v2_service.drive_api.uri
    }
  }
}
