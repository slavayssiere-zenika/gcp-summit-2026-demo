resource "google_cloud_run_v2_service" "missions_api" {
  name     = "missions-api-${terraform.workspace}"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  template {
    service_account = google_service_account.missions_sa.email

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
      image   = var.image_missions
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
        value = "postgresql://${replace(google_service_account.missions_sa.email, ".gserviceaccount.com", "")}@${google_alloydb_instance.primary.ip_address}:5432/missions"
      }
      env {
        name  = "ROOT_PATH"
        value = "/missions-api"
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
        value = var.missions_api_version
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

      env {
        name  = "USERS_API_URL"
        value = "http://api.internal.zenika/users-api/"
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
        name  = "PROMPTS_API_URL"
        value = "http://api.internal.zenika/prompts-api/"
      }
      env {
        name  = "COMPETENCIES_API_URL"
        value = "http://api.internal.zenika/comp-api/"
      }
      env {
        name  = "ITEMS_API_URL"
        value = "http://api.internal.zenika/items-api/"
      }
      env {
        name  = "DRIVE_API_URL"
        value = "http://api.internal.zenika/drive-api/"
      }
      env {
        name  = "MARKET_MCP_URL"
        value = "http://api.internal.zenika/market-mcp/"
      }
      env {
        name  = "CV_API_URL"
        value = "http://api.internal.zenika/cv-api/"
      }
    }

    # Conteneur Sidecar (MCP)
    containers {
      name    = "mcp"
      image   = var.image_missions
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
        value = "8081"
      }
      env {
        name  = "APP_VERSION"
        value = var.missions_api_version
      }
      env {
        name  = "MISSIONS_API_URL"
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
    null_resource.run_db_migrations_job
  ]
}


# ==========================================
# Identité et Permissions
# ==========================================
resource "google_service_account" "missions_sa" {
  account_id = "sa-missions-${terraform.workspace}-${random_id.sa_suffix.hex}"
  create_ignore_already_exists = true
}

resource "google_secret_manager_secret_iam_member" "missions_jwt_access" {
  project   = data.google_secret_manager_secret.jwt_secret.project
  secret_id = data.google_secret_manager_secret.jwt_secret.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.missions_sa.email}"
}

resource "google_project_iam_member" "missions_otel_trace" {
  project  = var.project_id
  role     = "roles/cloudtrace.agent"
  member   = "serviceAccount:${google_service_account.missions_sa.email}"
}

resource "google_project_iam_member" "missions_otel_metric" {
  project  = var.project_id
  role     = "roles/monitoring.metricWriter"
  member   = "serviceAccount:${google_service_account.missions_sa.email}"
}

resource "google_project_iam_member" "missions_alloydb_client" {
  project  = var.project_id
  role     = "roles/alloydb.client"
  member   = "serviceAccount:${google_service_account.missions_sa.email}"
}

resource "google_project_iam_member" "missions_alloydb_databaseUser" {
  project  = var.project_id
  role     = "roles/alloydb.databaseUser"
  member   = "serviceAccount:${google_service_account.missions_sa.email}"
}

resource "google_alloydb_user" "missions_db_user" {
  cluster    = google_alloydb_cluster.main.name
  user_id    = replace(google_service_account.missions_sa.email, ".gserviceaccount.com", "")
  user_type  = "ALLOYDB_IAM_USER"
  depends_on = [google_alloydb_instance.primary]
  lifecycle {
    ignore_changes = [database_roles]
  }
}

# Autorisation invocation interne LB
resource "google_cloud_run_v2_service_iam_member" "missions_invoker" {
  project  = google_cloud_run_v2_service.missions_api.project
  location = google_cloud_run_v2_service.missions_api.location
  name     = google_cloud_run_v2_service.missions_api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ==========================================
# Routage et Load Balancing
# ==========================================
resource "google_compute_region_network_endpoint_group" "missions_neg" {
  name                  = "neg-missions-${terraform.workspace}"
  network_endpoint_type = "SERVERLESS"
  region                = var.region
  cloud_run {
    service = google_cloud_run_v2_service.missions_api.name
  }
}

resource "google_compute_backend_service" "missions_backend" {
  name                  = "backend-missions-${terraform.workspace}"
  protocol              = "HTTPS"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  security_policy       = google_compute_security_policy.waf.id
  backend {
    group = google_compute_region_network_endpoint_group.missions_neg.id
  }
}

resource "google_compute_region_backend_service" "missions_internal_backend" {
  name                  = "backend-internal-missions-${terraform.workspace}"
  region                = var.region
  protocol              = "HTTP"
  load_balancing_scheme = "INTERNAL_MANAGED"
  backend {
    group           = google_compute_region_network_endpoint_group.missions_neg.id
    balancing_mode  = "UTILIZATION"
    capacity_scaler = 1.0
  }
}

resource "google_secret_manager_secret_iam_member" "missions_gemini_access" {
  project   = data.google_secret_manager_secret.gemini_api_key.project
  secret_id = data.google_secret_manager_secret.gemini_api_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.missions_sa.email}"
}

resource "google_project_iam_member" "missions_documentai_user" {
  project = var.project_id
  role    = "roles/documentai.apiUser"
  member  = "serviceAccount:${google_service_account.missions_sa.email}"
}
