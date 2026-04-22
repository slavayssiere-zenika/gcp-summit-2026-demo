# =========================================================
# 1. GCS Bucket pour le frontend
# =========================================================
resource "google_storage_bucket" "frontend_archives" {
  name          = var.bucket_frontend_name
  location      = var.region
  force_destroy = false

  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }
}

# =========================================================
# 2. Artifact Registry pour stocker les conteneurs
# =========================================================
resource "google_artifact_registry_repository" "services" {
  location      = var.region
  repository_id = var.artifact_registry_name
  description   = "Docker repository for Zenika Console microservices"
  format        = "DOCKER"

  # Politique de nettoyage active (dry_run=false = purge effective)
  cleanup_policy_dry_run = false

  # Règle 1 : conserver uniquement les N dernières versions par image
  cleanup_policies {
    id     = "keep-minimum-versions"
    action = "KEEP"
    most_recent_versions {
      keep_count = var.artifact_keep_count
    }
  }

  # Règle 2 : supprimer les images non-taguées (couches intermédiaires, builds ratés, etc.)
  cleanup_policies {
    id     = "delete-untagged"
    action = "DELETE"
    condition {
      tag_state  = "UNTAGGED"
      older_than = "${var.artifact_untagged_ttl_days * 24 * 3600}s"
    }
  }

  depends_on = [google_project_service.enabled_services]
}

# =========================================================
# 3. Secret Manager pour JWT Secret (Enveloppe seule)
# =========================================================
resource "google_secret_manager_secret" "jwt_secret" {
  secret_id = "jwt-secret"

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
}

# =========================================================
# 4. Secret Manager pour Gemini API Key (Enveloppe seule)
# =========================================================
resource "google_secret_manager_secret" "gemini_api_key" {
  secret_id = "gemini-api-key"

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
}

# =========================================================
# 5. GCS Bucket pour le Remote State Terraform
# =========================================================
resource "google_storage_bucket" "tfstate" {
  name          = var.bucket_tfstate_name
  location      = var.region
  force_destroy = false

  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }
}

# =========================================================
# Initialisation de fausses valeurs "latest" pour éviter que Terraform
# ne crashe sur Platform-Engineering, à substituer via la GUI par l'Ops
# =========================================================
resource "google_secret_manager_secret_version" "jwt" {
  secret      = google_secret_manager_secret.jwt_secret.id
  secret_data = "a-remplir-manuellement-dans-gcp"

  lifecycle {
    ignore_changes = [secret_data]
  }
}

resource "google_secret_manager_secret_version" "gemini" {
  secret      = google_secret_manager_secret.gemini_api_key.id
  secret_data = "a-remplir-manuellement-dans-gcp"

  lifecycle {
    ignore_changes = [secret_data]
  }
}

# =========================================================
# 6. Secret Manager pour Google OAuth
# =========================================================
resource "google_secret_manager_secret" "google_secret_id" {
  secret_id = "google-secret-id"
  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
}

resource "google_secret_manager_secret" "google_secret_key" {
  secret_id = "google-secret-key"
  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
}

resource "google_secret_manager_secret_version" "g_id" {
  secret      = google_secret_manager_secret.google_secret_id.id
  secret_data = "dummy"

  lifecycle {
    ignore_changes = [secret_data]
  }
}

resource "google_secret_manager_secret_version" "g_key" {
  secret      = google_secret_manager_secret.google_secret_key.id
  secret_data = "dummy"

  lifecycle {
    ignore_changes = [secret_data]
  }
}
