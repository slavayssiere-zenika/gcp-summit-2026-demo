resource "google_cloud_run_v2_service" "agent_hr_api" {
  name     = "agent-hr-api-${terraform.workspace}"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  template {
    service_account = google_service_account.agent_hr_sa.email # We reuse the agent service account
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
      image   = var.image_agent_hr
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
        value = "/agent-hr-api"
      }
      env {
        name  = "PROMPTS_API_URL"
        value = "http://api.internal.zenika/prompts-api/"
      }
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
        value = "redis://${google_redis_instance.cache.host}:${google_redis_instance.cache.port}/10"
      }
      env {
        name  = "TRACE_EXPORTER"
        value = "gcp"
      }
      env {
        name  = "APP_VERSION"
        value = var.agent_hr_api_version
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
    null_resource.run_db_migrations_job
  ]
}

# ==========================================
# Identité et Permissions
# ==========================================
resource "google_service_account" "agent_hr_sa" {
  account_id = "sa-agent-hr-${terraform.workspace}-${random_id.sa_suffix.hex}"
  create_ignore_already_exists = true
}

resource "google_secret_manager_secret_iam_member" "agent_hr_jwt_access" {
  project   = data.google_secret_manager_secret.jwt_secret.project
  secret_id = data.google_secret_manager_secret.jwt_secret.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.agent_hr_sa.email}"
}

resource "google_project_iam_member" "agent_hr_otel_trace" {
  project  = var.project_id
  role     = "roles/cloudtrace.agent"
  member   = "serviceAccount:${google_service_account.agent_hr_sa.email}"
}

resource "google_project_iam_member" "agent_hr_otel_metric" {
  project  = var.project_id
  role     = "roles/monitoring.metricWriter"
  member   = "serviceAccount:${google_service_account.agent_hr_sa.email}"
}

# Autorisation invocation interne LB
resource "google_cloud_run_v2_service_iam_member" "agent_hr_invoker" {
  project  = google_cloud_run_v2_service.agent_hr_api.project
  location = google_cloud_run_v2_service.agent_hr_api.location
  name     = google_cloud_run_v2_service.agent_hr_api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ==========================================
# Routage et Load Balancing
# ==========================================
resource "google_compute_region_network_endpoint_group" "agent_hr_neg" {
  name                  = "neg-agent-hr-${terraform.workspace}"
  network_endpoint_type = "SERVERLESS"
  region                = var.region
  cloud_run {
    service = google_cloud_run_v2_service.agent_hr_api.name
  }
}

resource "google_compute_region_backend_service" "agent_hr_internal_backend" {
  name                  = "backend-internal-agent-hr-${terraform.workspace}"
  region                = var.region
  protocol              = "HTTP"
  load_balancing_scheme = "INTERNAL_MANAGED"
  backend {
    group           = google_compute_region_network_endpoint_group.agent_hr_neg.id
    balancing_mode  = "UTILIZATION"
    capacity_scaler = 1.0
  }
}

resource "google_secret_manager_secret_iam_member" "agent_hr_gemini_access" {
  project   = data.google_secret_manager_secret.gemini_api_key.project
  secret_id = data.google_secret_manager_secret.gemini_api_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.agent_hr_sa.email}"
}

resource "google_project_iam_member" "agent_hr_logging_viewer" {
  project = var.project_id
  role    = "roles/logging.viewer"
  member  = "serviceAccount:${google_service_account.agent_hr_sa.email}"
}
