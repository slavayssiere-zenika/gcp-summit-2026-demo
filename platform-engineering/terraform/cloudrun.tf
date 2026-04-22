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

