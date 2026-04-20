resource "google_cloud_run_v2_service" "agent_ops_api" {
  name     = "agent-ops-api-${terraform.workspace}"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  template {
    service_account = google_service_account.agent_ops_sa.email
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
      image   = var.image_agent_ops
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
        value = "/agent-ops-api"
      }
      env {
        name  = "PROMPTS_API_URL"
        value = "http://api.internal.zenika/api/prompts/"
      }
      env {
        name  = "DRIVE_MCP_URL"
        value = "http://api.internal.zenika/api/drive/"
      }
      env {
        name  = "MARKET_MCP_URL"
        value = "http://api.internal.zenika/api/market/"
      }
      env {
        name  = "LOKI_MCP_URL"
        value = "http://api.internal.zenika/loki-mcp/" # Proxy directly if internal
      }
      env {
        name  = "USERS_API_URL"
        value = "http://api.internal.zenika/api/users/"
      }
      env {
        name  = "ITEMS_API_URL"
        value = "http://api.internal.zenika/api/items/"
      }
      env {
        name  = "COMPETENCIES_API_URL"
        value = "http://api.internal.zenika/api/competencies/"
      }
      env {
        name  = "CV_API_URL"
        value = "http://api.internal.zenika/api/cv/"
      }
      env {
        name  = "MISSIONS_API_URL"
        value = "http://api.internal.zenika/api/missions/"
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
        value = "redis://${google_redis_instance.cache.host}:${google_redis_instance.cache.port}/11"
      }
      env {
        name  = "TRACE_EXPORTER"
        value = "gcp"
      }
      env {
        name  = "APP_VERSION"
        value = var.agent_ops_api_version
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
      client,
      client_version,

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
resource "google_service_account" "agent_ops_sa" {
  account_id                   = "sa-agent-ops-${terraform.workspace}-${random_id.sa_suffix.hex}"
  create_ignore_already_exists = true
}

resource "google_secret_manager_secret_iam_member" "agent_ops_jwt_access" {
  project   = data.google_secret_manager_secret.jwt_secret.project
  secret_id = data.google_secret_manager_secret.jwt_secret.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.agent_ops_sa.email}"
}

resource "google_project_iam_member" "agent_ops_otel_trace" {
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.agent_ops_sa.email}"
}

resource "google_project_iam_member" "agent_ops_otel_metric" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.agent_ops_sa.email}"
}

# Autorisation invocation interne LB
resource "google_cloud_run_v2_service_iam_member" "agent_ops_invoker" {
  project  = google_cloud_run_v2_service.agent_ops_api.project
  location = google_cloud_run_v2_service.agent_ops_api.location
  name     = google_cloud_run_v2_service.agent_ops_api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ==========================================
# Routage et Load Balancing
# ==========================================
resource "google_compute_region_network_endpoint_group" "agent_ops_neg" {
  name                  = "neg-agent-ops-${terraform.workspace}"
  network_endpoint_type = "SERVERLESS"
  region                = var.region
  cloud_run {
    service = google_cloud_run_v2_service.agent_ops_api.name
  }
}

# Backend service interne (LB régional interne — utilisé inter-services)
resource "google_compute_region_backend_service" "agent_ops_internal_backend" {
  name                  = "backend-internal-agent-ops-${terraform.workspace}"
  region                = var.region
  protocol              = "HTTP"
  load_balancing_scheme = "INTERNAL_MANAGED"
  backend {
    group           = google_compute_region_network_endpoint_group.agent_ops_neg.id
    balancing_mode  = "UTILIZATION"
    capacity_scaler = 1.0
  }
}

# Backend service externe (LB global HTTPS — exposé via /agent-ops-api/ dans lb.tf)
resource "google_compute_backend_service" "agent_ops_backend" {
  name                  = "backend-agent-ops-${terraform.workspace}"
  protocol              = "HTTPS"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  security_policy       = google_compute_security_policy.waf.id
  backend {
    group = google_compute_region_network_endpoint_group.agent_ops_neg.id
  }
}

resource "google_secret_manager_secret_iam_member" "agent_ops_gemini_access" {
  project   = data.google_secret_manager_secret.gemini_api_key.project
  secret_id = data.google_secret_manager_secret.gemini_api_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.agent_ops_sa.email}"
}

resource "google_project_iam_member" "agent_ops_logging_viewer" {
  project = var.project_id
  role    = "roles/logging.viewer"
  member  = "serviceAccount:${google_service_account.agent_ops_sa.email}"
}

# ==============================================================
# Monitoring Custom Service & SLOs
# Latence cible : 30 000ms (requêtes ops avec accès Drive MCP,
# Market MCP, Loki MCP + raisonnement LLM)
# Disponibilité : 99.5% sur 30 jours glissants
# ==============================================================
resource "google_monitoring_custom_service" "agent_ops_api_svc" {
  service_id   = "agent-ops-api-service-${terraform.workspace}"
  display_name = "Agent Ops API Service"

  telemetry {
    resource_name = "//run.googleapis.com/projects/${var.project_id}/locations/${var.region}/services/${google_cloud_run_v2_service.agent_ops_api.name}"
  }
}

resource "google_monitoring_slo" "agent_ops_api_availability" {
  service      = google_monitoring_custom_service.agent_ops_api_svc.service_id
  slo_id       = "agent-ops-api-availability-${terraform.workspace}"
  display_name = "Availability 99.5% - Agent Ops API"

  goal                = 0.995
  rolling_period_days = 30

  request_based_sli {
    good_total_ratio {
      good_service_filter = join(" ", [
        "metric.type=\"run.googleapis.com/request_count\"",
        "resource.type=\"cloud_run_revision\"",
        "resource.label.\"service_name\"=\"${google_cloud_run_v2_service.agent_ops_api.name}\"",
        "metric.label.\"response_code_class\"!=\"5xx\""
      ])
      total_service_filter = join(" ", [
        "metric.type=\"run.googleapis.com/request_count\"",
        "resource.type=\"cloud_run_revision\"",
        "resource.label.\"service_name\"=\"${google_cloud_run_v2_service.agent_ops_api.name}\""
      ])
    }
  }
}

resource "google_monitoring_slo" "agent_ops_api_latency" {
  service      = google_monitoring_custom_service.agent_ops_api_svc.service_id
  slo_id       = "agent-ops-api-latency-${terraform.workspace}"
  display_name = "Latency p95 < 30s - Agent Ops API"

  goal                = 0.95
  rolling_period_days = 30

  request_based_sli {
    distribution_cut {
      distribution_filter = join(" ", [
        "metric.type=\"run.googleapis.com/request_latencies\"",
        "resource.type=\"cloud_run_revision\"",
        "resource.label.\"service_name\"=\"${google_cloud_run_v2_service.agent_ops_api.name}\""
      ])
      range {
        max = 30.0 # 30 000ms — Drive/Market/Loki MCP + raisonnement LLM Ops
      }
    }
  }
}
