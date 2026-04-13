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
    uri         = "https://api.internal.zenika/market-mcp/admin/finops/detect"

    # Authentification via le Service Account Agent_API (ou IAM specifique si configuré)
    # Pour s'assurer que c'est une requête de confiance
    oidc_token {
      service_account_email = google_service_account.cr_sa["agent"].email
      audience              = "https://api.internal.zenika/market-mcp"
    }
  }
}
