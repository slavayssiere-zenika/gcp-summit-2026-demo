# =========================================================
# Génération d'un mot de passe Administrateur initial
# =========================================================
resource "random_password" "admin_password" {
  length           = 16
  special          = true
  override_special = "!#$%&*-_=+"
}

# =========================================================
# Stockage dans GCP Secret Manager
# =========================================================
resource "google_secret_manager_secret" "admin_password" {
  secret_id = "admin-password-${terraform.workspace}"

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
}

resource "google_secret_manager_secret_version" "admin_password_version" {
  secret      = google_secret_manager_secret.admin_password.id
  secret_data = random_password.admin_password.result
}

# =========================================================
# OTel Collector Config
# =========================================================
resource "google_secret_manager_secret" "otel_config" {
  secret_id = "otel-config-${terraform.workspace}"

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
}

resource "google_secret_manager_secret_version" "otel_config_version" {
  secret      = google_secret_manager_secret.otel_config.id
  secret_data = file("${path.module}/otel-collector.yaml")
}

# =========================================================
# Stockage Mdp AlloyDB Postgres pour le Job Init
# =========================================================
resource "google_secret_manager_secret" "alloydb_password" {
  secret_id = "alloydb-password-${terraform.workspace}"

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
}

resource "google_secret_manager_secret_version" "alloydb_password_version" {
  secret      = google_secret_manager_secret.alloydb_password.id
  secret_data = random_password.alloydb_password.result
}

# =========================================================
# Google Chat Webhook URL — Notifications SRE Triage
# =========================================================
# Créer le webhook manuellement dans Google Chat :
#   Espace SRE → Apps & Integrations → Webhooks → Add webhook "SRE Triage Agent"
# Puis renseigner l'URL via :
#   echo -n "https://chat.googleapis.com/v1/spaces/..." | \
#     gcloud secrets versions add sre-chat-webhook-<env> --data-file=-
# La valeur est gérée hors Terraform (lifecycle ignore_changes sur la version).
resource "google_secret_manager_secret" "sre_chat_webhook" {
  secret_id = "sre-chat-webhook-${terraform.workspace}"

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
}

