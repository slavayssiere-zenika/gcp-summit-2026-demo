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



# Service Account mutualisé pour simplifier, ou un par service
resource "google_service_account" "cr_sa" {
  for_each   = toset(["users", "items", "competencies", "cv", "prompts", "agent", "drive"])
  account_id = "sa-${each.value}-${terraform.workspace}-v2"
}

# ==============================================================
# Modèle pour les services avec Sidecar MCP
# ==============================================================
locals {
  mcp_services = ["users", "items", "competencies", "cv"]
  mcp_images = {
    "users"        = var.image_users
    "items"        = var.image_items
    "competencies" = var.image_competencies
    "cv"           = var.image_cv
  }
}

resource "google_cloud_run_v2_service" "mcp_services" {
  for_each = toset(local.mcp_services)
  name     = "${each.value}-api-${terraform.workspace}"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  template {
    service_account = google_service_account.cr_sa[each.key].email

    scaling {
      min_instance_count = var.cloudrun_min_instances
      max_instance_count = var.cloudrun_max_instances
    }

    vpc_access {
      network_interfaces {
        network    = google_compute_network.main.id
        subnetwork = google_compute_subnetwork.main.id
        tags       = ["cr-egress"]
      }
    }

    # Conteneur principal (API)
    containers {
      name    = "api"
      image   = local.mcp_images[each.key] # géré par Terraform
      command = ["python"]
      args    = ["-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips", "*"]
      ports {
        container_port = 8080 # Le trafic Cloud Run arrive ici, GCP injecte le $PORT=8080 automatiquement
      }
      dynamic "startup_probe" {
        for_each = terraform.workspace == "dev" ? [] : [1]
        content {
          initial_delay_seconds = 15
          timeout_seconds       = 3
          period_seconds        = 5
          failure_threshold     = 20
          http_get {
            path = "/health"

          }
        }
      }
      dynamic "liveness_probe" {
        for_each = terraform.workspace == "dev" ? [] : [1]
        content {
          initial_delay_seconds = 15
          timeout_seconds       = 3
          period_seconds        = 10
          failure_threshold     = 3
          http_get {
            path = "/health"

          }
        }
      }
      resources {
        limits = {
          memory = "1024Mi"
        }
      }
      env {
        name  = "DATABASE_URL"
        value = "postgresql://${replace(google_service_account.cr_sa[each.key].email, ".gserviceaccount.com", "")}@${google_alloydb_instance.primary.ip_address}:5432/${each.key}"
      }
      env {
        name  = "ROOT_PATH"
        value = each.key == "competencies" ? "/comp-api" : "/${each.key}-api"
      }
      env {
        name  = "USE_IAM_AUTH"
        value = "true"
      }
      env {
        name  = "ALLOYDB_INSTANCE_URI"
        value = "projects/${var.project_id}/locations/${var.region}/clusters/${google_alloydb_cluster.main.cluster_id}/instances/${google_alloydb_instance.primary.instance_id}"
      }
      env {
        name  = "REDIS_URL"
        value = "redis://${google_redis_instance.cache.host}:${google_redis_instance.cache.port}/0"
      }
      env {
        name  = "TRACE_EXPORTER"
        value = "gcp"
      }
      env {
        name = "SECRET_KEY"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret.jwt_secret.secret_id
            version = "latest"
          }
        }
      }

      # Alimentation exclusive pour l'API Users responsable du seeding d'Admin
      dynamic "env" {
        for_each = each.key == "users" ? [1] : []
        content {
          name = "DEFAULT_ADMIN_PASSWORD"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.admin_password.secret_id
              version = "latest"
            }
          }
        }
      }

      dynamic "env" {
        for_each = each.key == "users" ? [1] : []
        content {
          name = "GOOGLE_SECRET_ID"
          value_source {
            secret_key_ref {
              secret  = data.google_secret_manager_secret.google_secret_id.secret_id
              version = "latest"
            }
          }
        }
      }

      dynamic "env" {
        for_each = each.key == "users" ? [1] : []
        content {
          name = "GOOGLE_SECRET_KEY"
          value_source {
            secret_key_ref {
              secret  = data.google_secret_manager_secret.google_secret_key.secret_id
              version = "latest"
            }
          }
        }
      }

      # Alimentation exclusive pour l'API CV responsable des embeddings RAG
      dynamic "env" {
        for_each = each.key == "cv" ? [1] : []
        content {
          name = "GOOGLE_API_KEY"
          value_source {
            secret_key_ref {
              secret  = data.google_secret_manager_secret.gemini_api_key.secret_id
              version = "latest"
            }
          }
        }
      }

      dynamic "env" {
        for_each = each.key == "cv" ? [1] : []
        content {
          name  = "PROMPTS_API_URL"
          value = "http://api.internal.zenika/prompts-api/"
        }
      }

      dynamic "env" {
        for_each = contains(["cv", "competencies"], each.key) ? [1] : []
        content {
          name  = "USERS_API_URL"
          value = "http://api.internal.zenika/users-api/"
        }
      }

      dynamic "env" {
        for_each = each.key == "cv" ? [1] : []
        content {
          name  = "COMPETENCIES_API_URL"
          value = "http://api.internal.zenika/comp-api/"
        }
      }
    }

    # Conteneur Sidecar (MCP)
    containers {
      name    = "mcp"
      image   = local.mcp_images[each.key] # géré par Terraform
      command = ["python"]
      args    = ["-m", "uvicorn", "mcp_app:app", "--host", "0.0.0.0", "--port", "8081"]
      dynamic "startup_probe" {
        for_each = terraform.workspace == "dev" ? [] : [1]
        content {
          initial_delay_seconds = 15
          timeout_seconds       = 3
          period_seconds        = 5
          failure_threshold     = 20
          http_get {
            path = "/health"
            port = 8081

          }
        }
      }
      dynamic "liveness_probe" {
        for_each = terraform.workspace == "dev" ? [] : [1]
        content {
          initial_delay_seconds = 15
          timeout_seconds       = 3
          period_seconds        = 10
          failure_threshold     = 3
          http_get {
            path = "/health"
            port = 8081

          }
        }
      }
      resources {
        limits = {
          memory = "512Mi"
        }
      }

      env {
        name  = "TRACE_EXPORTER"
        value = "gcp"
      }
      env {
        name  = "PORT"
        value = "8081" # Overrides standard PORT to prevent :8080 collisions
      }
      env {
        name  = "${upper(each.key)}_API_URL"
        value = "http://localhost:8080" # L'API est sur localhost nativement
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].resources[0].limits["cpu"],
      template[0].containers[1].resources[0].limits["cpu"]
    ]
  }

  depends_on = [
    time_sleep.wait_for_iam_propagation,
    null_resource.run_db_migrations_job
  ]
}

# ==============================================================
# Services standards
# ==============================================================
resource "google_cloud_run_v2_service" "prompts_api" {
  name     = "prompts-api-${terraform.workspace}"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  template {
    service_account = google_service_account.cr_sa["prompts"].email
    scaling {
      min_instance_count = var.cloudrun_min_instances
      max_instance_count = var.cloudrun_max_instances
    }
    vpc_access {
      network_interfaces {
        network    = google_compute_network.main.id
        subnetwork = google_compute_subnetwork.main.id
        tags       = ["cr-egress"]
      }
    }
    containers {
      name    = "api"
      image   = var.image_prompts
      command = ["python"]
      args    = ["-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips", "*"]
      ports {
        container_port = 8080
      }
      dynamic "startup_probe" {
        for_each = terraform.workspace == "dev" ? [] : [1]
        content {
          initial_delay_seconds = 15
          timeout_seconds       = 3
          period_seconds        = 5
          failure_threshold     = 20
          http_get {
            path = "/health"

          }
        }
      }
      dynamic "liveness_probe" {
        for_each = terraform.workspace == "dev" ? [] : [1]
        content {
          initial_delay_seconds = 15
          timeout_seconds       = 3
          period_seconds        = 10
          failure_threshold     = 3
          http_get {
            path = "/health"

          }
        }
      }
      resources {
        limits = {
          memory = "1024Mi"
        }
      }
      env {
        name = "GOOGLE_API_KEY"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret.gemini_api_key.secret_id
            version = "latest"
          }
        }
      }
      env {
        name  = "DATABASE_URL"
        value = "postgresql://${replace(google_service_account.cr_sa["prompts"].email, ".gserviceaccount.com", "")}@${google_alloydb_instance.primary.ip_address}:5432/prompts"
      }
      env {
        name  = "ROOT_PATH"
        value = "/prompts-api"
      }
      env {
        name  = "USE_IAM_AUTH"
        value = "true"
      }
      env {
        name  = "ALLOYDB_INSTANCE_URI"
        value = "projects/${var.project_id}/locations/${var.region}/clusters/${google_alloydb_cluster.main.cluster_id}/instances/${google_alloydb_instance.primary.instance_id}"
      }
      env {
        name  = "REDIS_URL"
        value = "redis://${google_redis_instance.cache.host}:${google_redis_instance.cache.port}/0"
      }
      env {
        name  = "TRACE_EXPORTER"
        value = "gcp"
      }
      env {
        name = "SECRET_KEY"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret.jwt_secret.secret_id
            version = "latest"
          }
        }
      }
    }

  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].resources[0].limits["cpu"]
    ]
  }

  depends_on = [
    time_sleep.wait_for_iam_propagation,
    null_resource.run_db_migrations_job
  ]
}

resource "google_cloud_run_v2_service" "drive_api" {
  name     = "drive-api-${terraform.workspace}"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  template {
    service_account = google_service_account.cr_sa["drive"].email
    scaling {
      min_instance_count = var.cloudrun_min_instances
      max_instance_count = var.cloudrun_max_instances
    }
    vpc_access {
      network_interfaces {
        network    = google_compute_network.main.id
        subnetwork = google_compute_subnetwork.main.id
        tags       = ["cr-egress"]
      }
    }
    containers {
      name    = "api"
      image   = var.image_drive
      command = ["python"]
      args    = ["-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips", "*"]
      ports {
        container_port = 8080
      }
      dynamic "startup_probe" {
        for_each = terraform.workspace == "dev" ? [] : [1]
        content {
          initial_delay_seconds = 15
          timeout_seconds       = 3
          period_seconds        = 5
          failure_threshold     = 20
          http_get {
            path = "/health"

          }
        }
      }
      dynamic "liveness_probe" {
        for_each = terraform.workspace == "dev" ? [] : [1]
        content {
          initial_delay_seconds = 15
          timeout_seconds       = 3
          period_seconds        = 10
          failure_threshold     = 3
          http_get {
            path = "/health"

          }
        }
      }
      resources {
        limits = {
          memory = "1024Mi"
        }
      }
      env {
        name  = "DATABASE_URL"
        value = "postgresql://${replace(google_service_account.cr_sa["drive"].email, ".gserviceaccount.com", "")}@${google_alloydb_instance.primary.ip_address}:5432/drive"
      }
      env {
        name  = "ROOT_PATH"
        value = "/drive-api"
      }
      env {
        name  = "USE_IAM_AUTH"
        value = "true"
      }
      env {
        name  = "ALLOYDB_INSTANCE_URI"
        value = "projects/${var.project_id}/locations/${var.region}/clusters/${google_alloydb_cluster.main.cluster_id}/instances/${google_alloydb_instance.primary.instance_id}"
      }
      env {
        name  = "REDIS_URL"
        value = "redis://${google_redis_instance.cache.host}:${google_redis_instance.cache.port}/6"
      }
      env {
        name  = "CV_API_URL"
        value = "http://api.internal.zenika/cv-api/"
      }
      env {
        name  = "USERS_API_URL"
        value = "http://api.internal.zenika/users-api/"
      }
      env {
        name  = "TRACE_EXPORTER"
        value = "gcp"
      }
      env {
        name = "SECRET_KEY"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret.jwt_secret.secret_id
            version = "latest"
          }
        }
      }
    }

    # Conteneur Sidecar (MCP)
    containers {
      name    = "mcp"
      image   = var.image_drive
      command = ["python"]
      args    = ["-m", "uvicorn", "mcp_app:app", "--host", "0.0.0.0", "--port", "8081"]
      dynamic "startup_probe" {
        for_each = terraform.workspace == "dev" ? [] : [1]
        content {
          initial_delay_seconds = 15
          timeout_seconds       = 3
          period_seconds        = 5
          failure_threshold     = 20
          http_get {
            path = "/health"
            port = 8081

          }
        }
      }
      dynamic "liveness_probe" {
        for_each = terraform.workspace == "dev" ? [] : [1]
        content {
          initial_delay_seconds = 15
          timeout_seconds       = 3
          period_seconds        = 10
          failure_threshold     = 3
          http_get {
            path = "/health"
            port = 8081

          }
        }
      }
      resources {
        limits = {
          memory = "256Mi"
        }
      }

      env {
        name  = "TRACE_EXPORTER"
        value = "gcp"
      }
      env {
        name  = "PORT"
        value = "8081"
      }
      env {
        name  = "DRIVE_API_URL"
        value = "http://localhost:8080"
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].resources[0].limits["cpu"],
      template[0].containers[1].resources[0].limits["cpu"]
    ]
  }

  depends_on = [
    time_sleep.wait_for_iam_propagation,
    null_resource.run_db_migrations_job
  ]
}

resource "google_cloud_run_v2_service" "agent_api" {
  name     = "agent-api-${terraform.workspace}"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  template {
    service_account = google_service_account.cr_sa["agent"].email
    scaling {
      min_instance_count = var.cloudrun_min_instances
      max_instance_count = var.cloudrun_max_instances
    }
    vpc_access {
      network_interfaces {
        network    = google_compute_network.main.id
        subnetwork = google_compute_subnetwork.main.id
        tags       = ["cr-egress"]
      }
    }
    containers {
      name    = "api"
      image   = var.image_agent
      command = ["python"]
      args    = ["-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips", "*"]
      ports {
        container_port = 8080
      }
      dynamic "startup_probe" {
        for_each = terraform.workspace == "dev" ? [] : [1]
        content {
          initial_delay_seconds = 15
          timeout_seconds       = 3
          period_seconds        = 5
          failure_threshold     = 20
          http_get {
            path = "/health"

          }
        }
      }
      dynamic "liveness_probe" {
        for_each = terraform.workspace == "dev" ? [] : [1]
        content {
          initial_delay_seconds = 15
          timeout_seconds       = 3
          period_seconds        = 10
          failure_threshold     = 3
          http_get {
            path = "/health"

          }
        }
      }
      resources {
        limits = {
          memory = "1024Mi"
        }
      }
      env {
        name = "GOOGLE_API_KEY"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret.gemini_api_key.secret_id
            version = "latest"
          }
        }
      }
      env {
        name  = "ROOT_PATH"
        value = "/api"
      }
      # L'agent a besoin des URLs des Cloud Run.
      # Remarque: avec l'ingress INTERNAL_LOAD_BALANCER, l'agent peut quand même
      # joindre les autres Cloud Run internes en utilisant le VPC grâce au Direct Egress.
      env {
        name  = "USERS_API_URL"
        value = "http://api.internal.zenika/users-api/"
      }
      env {
        name  = "ITEMS_API_URL"
        value = "http://api.internal.zenika/items-api/"
      }
      env {
        name  = "COMPETENCIES_API_URL"
        value = "http://api.internal.zenika/comp-api/"
      }
      env {
        name  = "CV_API_URL"
        value = "http://api.internal.zenika/cv-api/"
      }
      env {
        name = "DRIVE_MCP_URL"
        # We target the Cloud Run internal LB URL with the drive-api suffix and fallback in agent to 8081 if local.
        # However, following the pattern we point to the API base URL.
        value = "http://api.internal.zenika/drive-api/"
      }
      env {
        name  = "USE_GCP_LOGGING"
        value = "true"
      }
      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "REDIS_URL"
        value = "redis://${google_redis_instance.cache.host}:${google_redis_instance.cache.port}/1"
      }
      env {
        name  = "TRACE_EXPORTER"
        value = "gcp"
      }
      env {
        name = "SECRET_KEY"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret.jwt_secret.secret_id
            version = "latest"
          }
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].resources[0].limits["cpu"]
    ]
  }

  depends_on = [
    time_sleep.wait_for_iam_propagation,
    null_resource.run_db_migrations_job
  ]
}

# ==============================================================
# Droits IAM pour l'accès aux Secrets
# ==============================================================
resource "google_secret_manager_secret_iam_member" "jwt_secret_access" {
  for_each  = google_service_account.cr_sa
  project   = data.google_secret_manager_secret.jwt_secret.project
  secret_id = data.google_secret_manager_secret.jwt_secret.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${each.value.email}"
}

resource "google_secret_manager_secret_iam_member" "gemini_secret_access" {
  for_each  = google_service_account.cr_sa
  project   = data.google_secret_manager_secret.gemini_api_key.project
  secret_id = data.google_secret_manager_secret.gemini_api_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${each.value.email}"
}

resource "google_secret_manager_secret_iam_member" "admin_password_access" {
  project   = google_secret_manager_secret.admin_password.project
  secret_id = google_secret_manager_secret.admin_password.secret_id
  role      = "roles/secretmanager.secretAccessor"
  # Uniquement l'API Users a besoin d'accéder à ce mot de passe de Boot.
  member = "serviceAccount:${google_service_account.cr_sa["users"].email}"
}

resource "google_secret_manager_secret_iam_member" "google_secret_id_access" {
  project   = data.google_secret_manager_secret.google_secret_id.project
  secret_id = data.google_secret_manager_secret.google_secret_id.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cr_sa["users"].email}"
}

resource "google_secret_manager_secret_iam_member" "google_secret_key_access" {
  project   = data.google_secret_manager_secret.google_secret_key.project
  secret_id = data.google_secret_manager_secret.google_secret_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cr_sa["users"].email}"
}

# ==============================================================
# Droits IAM spécifiques pour le Tracing et Monitoring
# ==============================================================
resource "google_project_iam_member" "otel_trace_writer" {
  for_each = google_service_account.cr_sa
  project  = var.project_id
  role     = "roles/cloudtrace.agent"
  member   = "serviceAccount:${each.value.email}"
}

resource "google_project_iam_member" "otel_metric_writer" {
  for_each = google_service_account.cr_sa
  project  = var.project_id
  role     = "roles/monitoring.metricWriter"
  member   = "serviceAccount:${each.value.email}"
}

resource "google_project_iam_member" "alloydb_client" {
  for_each = google_service_account.cr_sa
  project  = var.project_id
  role     = "roles/alloydb.client"
  member   = "serviceAccount:${each.value.email}"
}

resource "google_project_iam_member" "alloydb_databaseUser" {
  for_each = google_service_account.cr_sa
  project  = var.project_id
  role     = "roles/alloydb.databaseUser"
  member   = "serviceAccount:${each.value.email}"
}

# ==============================================================
# Droits IAM spécifiques pour l'Agent (Logging)
# ==============================================================
resource "google_project_iam_member" "agent_logging_viewer" {
  project = var.project_id
  role    = "roles/logging.viewer"
  member  = "serviceAccount:${google_service_account.cr_sa["agent"].email}"
}

# ==============================================================
# Timer de propagation IAM (Evite les crashs Cloud Run / DB)
# ==============================================================
resource "time_sleep" "wait_for_iam_propagation" {
  depends_on = [
    google_secret_manager_secret_iam_member.jwt_secret_access,
    google_secret_manager_secret_iam_member.gemini_secret_access,
    google_secret_manager_secret_iam_member.admin_password_access,
    google_secret_manager_secret_iam_member.google_secret_id_access,
    google_secret_manager_secret_iam_member.google_secret_key_access,
    google_project_iam_member.otel_trace_writer,
    google_project_iam_member.otel_metric_writer,
    google_project_iam_member.alloydb_client,
    google_project_iam_member.alloydb_databaseUser,
    google_project_iam_member.agent_logging_viewer
  ]
  create_duration = "45s"
}

# ==============================================================
# Autorisation d'invocation anonyme (via Load Balancer uniquement)
# ==============================================================
# NB: L'ingress 'INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER' garantit 
# qu'aucun trafic public direct (*.run.app) ne peut joindre le conteneur.
# Mettre "allUsers" permet donc au Load Balancer de router la requête sans jeton IAM.

resource "google_cloud_run_v2_service_iam_member" "mcp_invoker" {
  for_each = google_cloud_run_v2_service.mcp_services
  project  = each.value.project
  location = each.value.location
  name     = each.value.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "prompts_invoker" {
  project  = google_cloud_run_v2_service.prompts_api.project
  location = google_cloud_run_v2_service.prompts_api.location
  name     = google_cloud_run_v2_service.prompts_api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "agent_invoker" {
  project  = google_cloud_run_v2_service.agent_api.project
  location = google_cloud_run_v2_service.agent_api.location
  name     = google_cloud_run_v2_service.agent_api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "drive_invoker" {
  project  = google_cloud_run_v2_service.drive_api.project
  location = google_cloud_run_v2_service.drive_api.location
  name     = google_cloud_run_v2_service.drive_api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ==============================================================
# Cloud Scheduler for Drive API background polling
# ==============================================================
resource "google_cloud_scheduler_job" "drive_sync_job" {
  name             = "drive-sync-trigger-${terraform.workspace}"
  description      = "Triggers Drive API /sync every 5 minutes"
  schedule         = "*/5 * * * *"
  time_zone        = "Europe/Paris"
  attempt_deadline = "320s"

  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_v2_service.drive_api.uri}/sync"

    # We do not strictly need OIDC because we use Ingress Internal LB and it's exposed internally,
    # but since Scheduler is outside the VPC, it accesses the public endpoint of Cloud Run.
    # Actually wait! The Cloud Run `ingress = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"`.
    # Cloud Scheduler CANNOT hit it directly unless we route it via HTTP target with OIDC OR use an Internal LB endpoint.
    # Let's just use the native Cloud Run URI with OIDC token of the drive SA.
    oidc_token {
      service_account_email = google_service_account.cr_sa["drive"].email
    }
  }
}
