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

