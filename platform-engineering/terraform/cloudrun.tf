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



# Service Account par service
resource "google_service_account" "cr_sa" {
  for_each   = toset(local.cr_sa_keys)
  account_id = "sa-${each.value}-${terraform.workspace}-v2"
}

# ==============================================================
# Modèle pour les services avec Sidecar MCP
# ==============================================================
locals {
  mcp_services = ["users", "items", "competencies", "cv", "missions"]
  cr_sa_keys   = ["users", "items", "competencies", "cv", "missions", "prompts", "agent", "drive", "market"]
  mcp_images = {
    "users"        = var.image_users
    "items"        = var.image_items
    "competencies" = var.image_competencies
    "cv"           = var.image_cv
    "missions"     = var.image_missions
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
      args    = ["-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips", "*", "--no-server-header"]
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
        name = "APP_VERSION"
        value = lookup({
          "users"        = var.users_api_version
          "items"        = var.items_api_version
          "competencies" = var.competencies_api_version
          "cv"           = var.cv_api_version
          "missions"     = var.missions_api_version
        }, each.key, "unknown")
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

      dynamic "env" {
        for_each = each.key == "users" ? [1] : []
        content {
          name  = "CV_API_URL"
          value = "http://api.internal.zenika/cv-api/"
        }
      }

      dynamic "env" {
        for_each = each.key == "users" ? [1] : []
        content {
          name  = "ITEMS_API_URL"
          value = "http://api.internal.zenika/items-api/"
        }
      }

      dynamic "env" {
        for_each = each.key == "users" ? [1] : []
        content {
          name  = "COMPETENCIES_API_URL"
          value = "http://api.internal.zenika/comp-api/"
        }
      }

      dynamic "env" {
        for_each = each.key == "users" ? [1] : []
        content {
          name  = "GCP_PROJECT_ID"
          value = var.project_id
        }
      }

      dynamic "env" {
        for_each = each.key == "users" ? [1] : []
        content {
          name  = "USER_EVENTS_TOPIC"
          value = google_pubsub_topic.user_events.name
        }
      }

      # Alimentation exclusive pour l'API CV responsable des embeddings RAG
      dynamic "env" {
        for_each = contains(["cv", "missions"], each.key) ? [1] : []
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
        for_each = contains(["cv", "missions"], each.key) ? [1] : []
        content {
          name  = "PROMPTS_API_URL"
          value = "http://api.internal.zenika/prompts-api/"
        }
      }

      dynamic "env" {
        for_each = contains(["cv", "competencies", "missions"], each.key) ? [1] : []
        content {
          name  = "USERS_API_URL"
          value = "http://api.internal.zenika/users-api/"
        }
      }

      dynamic "env" {
        for_each = contains(["cv", "missions"], each.key) ? [1] : []
        content {
          name  = "COMPETENCIES_API_URL"
          value = "http://api.internal.zenika/comp-api/"
        }
      }

      dynamic "env" {
        for_each = contains(["cv", "missions"], each.key) ? [1] : []
        content {
          name  = "ITEMS_API_URL"
          value = "http://api.internal.zenika/items-api/"
        }
      }

      dynamic "env" {
        for_each = each.key == "missions" ? [1] : []
        content {
          name  = "CV_API_URL"
          value = "http://api.internal.zenika/cv-api/"
        }
      }

      dynamic "env" {
        for_each = contains(["cv", "missions"], each.key) ? [1] : []
        content {
          name  = "DRIVE_API_URL"
          value = "http://api.internal.zenika/drive-api/"
        }
      }

      dynamic "env" {
        for_each = contains(["cv", "missions"], each.key) ? [1] : []
        content {
          name  = "MARKET_MCP_URL"
          value = "http://api.internal.zenika/market-mcp/"
        }
      }
    }

    # Conteneur Sidecar (MCP)
    containers {
      name    = "mcp"
      image   = local.mcp_images[each.key] # géré par Terraform
      command = ["python"]
      args    = ["-m", "uvicorn", "mcp_app:app", "--host", "0.0.0.0", "--port", "8081", "--no-server-header"]
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
        name = "APP_VERSION"
        value = lookup({
          "users"        = var.users_api_version
          "items"        = var.items_api_version
          "competencies" = var.competencies_api_version
          "cv"           = var.cv_api_version
          "missions"     = var.missions_api_version
        }, each.key, "unknown")
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
      args    = ["-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips", "*", "--no-server-header"]
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
        name  = "APP_VERSION"
        value = var.prompts_api_version
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
      args    = ["-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips", "*", "--no-server-header"]
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
        name  = "APP_VERSION"
        value = var.drive_api_version
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
      args    = ["-m", "uvicorn", "mcp_app:app", "--host", "0.0.0.0", "--port", "8081", "--no-server-header"]
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
        name  = "APP_VERSION"
        value = var.drive_api_version
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
      args    = ["-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips", "*", "--no-server-header"]
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
        name  = "GEMINI_MODEL"
        value = var.gemini_model
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
        name  = "MISSIONS_API_URL"
        value = "http://api.internal.zenika/missions-api/"
      }
      env {
        name = "DRIVE_MCP_URL"
        # We target the Cloud Run internal LB URL with the drive-api suffix and fallback in agent to 8081 if local.
        # However, following the pattern we point to the API base URL.
        value = "http://api.internal.zenika/drive-api/"
      }
      env {
        name  = "MARKET_MCP_URL"
        value = "http://api.internal.zenika/market-mcp/"
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
        name  = "APP_VERSION"
        value = var.agent_api_version
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
# Standalone services (Standalone MCP)
# ==============================================================
resource "google_cloud_run_v2_service" "market_mcp" {
  name     = "market-mcp-${terraform.workspace}"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  template {
    service_account = google_service_account.cr_sa["market"].email
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
      image   = var.image_market
      command = ["python"]
      args    = ["mcp_app.py"]
      ports {
        container_port = 8080
      }
      startup_probe {
        initial_delay_seconds = 10
        timeout_seconds       = 3
        period_seconds        = 5
        failure_threshold     = 10
        http_get {
          path = "/health"
        }
      }
      liveness_probe {
        initial_delay_seconds = 15
        timeout_seconds       = 3
        period_seconds        = 10
        failure_threshold     = 3
        http_get {
          path = "/health"
        }
      }
      resources {
        limits = {
          memory = "1024Mi"
        }
      }
      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "TRACE_EXPORTER"
        value = "gcp"
      }
      env {
        name  = "REDIS_URL"
        value = "redis://${google_redis_instance.cache.host}:${google_redis_instance.cache.port}/0"
      }
      env {
        name  = "APP_VERSION"
        value = var.market_mcp_version
      }
      env {
        name  = "FINOPS_ANOMALY_THRESHOLD"
        value = tostring(var.finops_anomaly_threshold)
      }
      env {
        name  = "USERS_API_URL"
        value = "http://api.internal.zenika/users-api/" # Added for kill-switch HTTP call
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
    time_sleep.wait_for_iam_propagation
  ]
}

# ==============================================================
# Droits IAM pour l'accès aux Secrets
# ==============================================================
resource "google_secret_manager_secret_iam_member" "jwt_secret_access" {
  for_each  = toset(local.cr_sa_keys)
  project   = data.google_secret_manager_secret.jwt_secret.project
  secret_id = data.google_secret_manager_secret.jwt_secret.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cr_sa[each.key].email}"
}

resource "google_secret_manager_secret_iam_member" "gemini_secret_access" {
  for_each  = toset(local.cr_sa_keys)
  project   = data.google_secret_manager_secret.gemini_api_key.project
  secret_id = data.google_secret_manager_secret.gemini_api_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cr_sa[each.key].email}"
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
  for_each = toset(local.cr_sa_keys)
  project  = var.project_id
  role     = "roles/cloudtrace.agent"
  member   = "serviceAccount:${google_service_account.cr_sa[each.key].email}"
}

resource "google_project_iam_member" "otel_metric_writer" {
  for_each = toset(local.cr_sa_keys)
  project  = var.project_id
  role     = "roles/monitoring.metricWriter"
  member   = "serviceAccount:${google_service_account.cr_sa[each.key].email}"
}

resource "google_project_iam_member" "alloydb_client" {
  for_each = toset(local.cr_sa_keys)
  project  = var.project_id
  role     = "roles/alloydb.client"
  member   = "serviceAccount:${google_service_account.cr_sa[each.key].email}"
}

resource "google_project_iam_member" "alloydb_databaseUser" {
  for_each = toset(local.cr_sa_keys)
  project  = var.project_id
  role     = "roles/alloydb.databaseUser"
  member   = "serviceAccount:${google_service_account.cr_sa[each.key].email}"
}

# BigQuery roles for Market service
resource "google_project_iam_member" "market_bq_admin" {
  project = var.project_id
  role    = "roles/bigquery.admin"
  member  = "serviceAccount:${google_service_account.cr_sa["market"].email}"
}

resource "google_project_iam_member" "market_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.cr_sa["market"].email}"
}

resource "google_project_iam_member" "market_trace_user" {
  project = var.project_id
  role    = "roles/cloudtrace.user"
  member  = "serviceAccount:${google_service_account.cr_sa["market"].email}"
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
# Droits IAM spécifiques pour Missions (DocumentAI Sandbox)
# ==============================================================
resource "google_project_iam_member" "missions_documentai_user" {
  project = var.project_id
  role    = "roles/documentai.apiUser"
  member  = "serviceAccount:${google_service_account.cr_sa["missions"].email}"
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
    google_project_iam_member.agent_logging_viewer,
    google_project_iam_member.missions_documentai_user
  ]
  create_duration = "45s"
}

# ==============================================================
# Autorisation d'invocation anonyme (via Load Balancer uniquement)
# ==============================================================
# DOCUMENTATION ZERO-TRUST : L'ingress 'INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER' garantit 
# qu'aucun trafic public direct (*.run.app) ne peut joindre le conteneur.
# L'assignation de `roles/run.invoker` à "allUsers" permet au Load Balancer Interne (ou aux autres microservices 
# via VPC) de router la requête HTTP standard sans avoir à générer des jetons d'identité GCP OIDC complexes pour chaque Call inter-service.
# La VRAIE sécurité (Zero-Trust) est gérée au niveau applicatif : chaque microservice vérifie strictement 
# le JWT Bearer via FastAPI (Dependencies) interdisant toute action non authentifiée, même en réseau interne.

resource "google_cloud_run_v2_service_iam_member" "mcp_invoker" {
  for_each = toset(local.mcp_services)
  project  = google_cloud_run_v2_service.mcp_services[each.key].project
  location = google_cloud_run_v2_service.mcp_services[each.key].location
  name     = google_cloud_run_v2_service.mcp_services[each.key].name
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

resource "google_cloud_run_v2_service_iam_member" "market_invoker" {
  project  = google_cloud_run_v2_service.market_mcp.project
  location = google_cloud_run_v2_service.market_mcp.location
  name     = google_cloud_run_v2_service.market_mcp.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

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
