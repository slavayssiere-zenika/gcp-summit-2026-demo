# Données pour accéder aux secrets existants
data "google_secret_manager_secret" "jwt_secret" {
  secret_id = "jwt-secret"
}

data "google_secret_manager_secret" "gemini_api_key" {
  secret_id = "gemini-api-key"
}

data "google_secret_manager_secret" "google_secret_id" {
  secret_id = "google-secret-id"
}

data "google_secret_manager_secret" "google_secret_key" {
  secret_id = "google-secret-key"
}

# Unique ID to bypass GCP Service Account soft-delete (30 days) for ephemeral environments
# IMPORTANT: ignore_changes = all prevents regeneration if Terraform state is partially lost.
# A new suffix would break all AlloyDB IAM grants and require full DB re-init.
resource "random_id" "sa_suffix" {
  byte_length = 2

  lifecycle {
    ignore_changes = all
  }
}

# ==============================================================
# Droits IAM spécifiques pour le Tracing et Monitoring
# (The rest of SAs, IAM, Backend logic have been migrated to the respective cr_*.tf files)
# ==============================================================

# ==============================================================
# Cloud Scheduler for Drive API background polling
# ==============================================================
resource "google_cloud_scheduler_job" "drive_sync_job" {
  name             = "drive-sync-trigger-${terraform.workspace}"
  description      = "Triggers Drive API /sync every hour"
  schedule         = "0 * * * *"
  time_zone        = "Europe/Paris"
  attempt_deadline = "320s"

  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_v2_service.drive_api.uri}/sync"

    oidc_token {
      service_account_email = google_service_account.drive_sa.email
    }
  }
}
