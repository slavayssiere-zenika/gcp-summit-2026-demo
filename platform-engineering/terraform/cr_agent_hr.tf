resource "google_cloud_run_v2_service" "agent_hr_api" {
  name                = "agent-hr-api-${terraform.workspace}"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
  deletion_protection = false

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
      egress = "PRIVATE_RANGES_ONLY"
    }
    containers {
      name    = "api"
      image   = var.image_agent_hr
      command = ["python3"]
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
        value = "http://api.internal.zenika/api/prompts/"
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
        name  = "MARKET_MCP_URL"
        value = "http://api.internal.zenika/api/market/"
      }
      env {
        name  = "MONITORING_MCP_URL"
        value = "http://api.internal.zenika/monitoring-mcp/"
      }
      # MCP Sidecars: /mcp/tools and /mcp/call are now public endpoints (no JWT)
      # on each API service. They proxy to the co-located MCP sidecar (port 8081).
      # These URLs must NOT go through the EXTERNAL LB — they use the INTERNAL LB.
      env {
        name  = "USERS_MCP_URL"
        value = "http://api.internal.zenika/api/users/"
      }
      env {
        name  = "ITEMS_MCP_URL"
        value = "http://api.internal.zenika/api/items/"
      }
      env {
        name  = "COMPETENCIES_MCP_URL"
        value = "http://api.internal.zenika/api/competencies/"
      }
      env {
        name  = "CV_MCP_URL"
        value = "http://api.internal.zenika/api/cv/"
      }
      env {
        name  = "MISSIONS_MCP_URL"
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
resource "google_service_account" "agent_hr_sa" {
  account_id                   = "sa-agent-hr-${terraform.workspace}-${random_id.sa_suffix.hex}"
  create_ignore_already_exists = true
}

resource "google_secret_manager_secret_iam_member" "agent_hr_jwt_access" {
  project   = data.google_secret_manager_secret.jwt_secret.project
  secret_id = data.google_secret_manager_secret.jwt_secret.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.agent_hr_sa.email}"
}

resource "google_project_iam_member" "agent_hr_otel_trace" {
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.agent_hr_sa.email}"
}

resource "google_project_iam_member" "agent_hr_otel_metric" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.agent_hr_sa.email}"
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

# Backend service interne (LB régional interne — utilisé inter-services)
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

# Backend service externe (LB global HTTPS — exposé via /agent-hr-api/ dans lb.tf)
resource "google_compute_backend_service" "agent_hr_backend" {
  name                  = "backend-agent-hr-${terraform.workspace}"
  protocol              = "HTTPS"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  security_policy       = google_compute_security_policy.waf.id
  backend {
    group = google_compute_region_network_endpoint_group.agent_hr_neg.id
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

# ==============================================================
# Monitoring Custom Service & SLOs
# Latence cible : 30 000ms (requêtes RH avec appels MCP chaînés
# vers users, competencies, cv, missions + raisonnement LLM)
# Disponibilité : 99.5% sur 30 jours glissants
# ==============================================================
resource "google_monitoring_custom_service" "agent_hr_api_svc" {
  service_id   = "agent-hr-api-service-${terraform.workspace}"
  display_name = "Agent HR API Service"

  telemetry {
    resource_name = "//run.googleapis.com/projects/${var.project_id}/locations/${var.region}/services/${google_cloud_run_v2_service.agent_hr_api.name}"
  }
}

resource "google_monitoring_slo" "agent_hr_api_availability" {
  service      = google_monitoring_custom_service.agent_hr_api_svc.service_id
  slo_id       = "agent-hr-api-availability-${terraform.workspace}"
  display_name = "Availability 99.5% - Agent HR API"

  goal                = 0.995
  rolling_period_days = 30

  request_based_sli {
    good_total_ratio {
      good_service_filter = join(" ", [
        "metric.type=\"run.googleapis.com/request_count\"",
        "resource.type=\"cloud_run_revision\"",
        "resource.label.\"service_name\"=\"${google_cloud_run_v2_service.agent_hr_api.name}\"",
        "metric.label.\"response_code_class\"!=\"5xx\""
      ])
      total_service_filter = join(" ", [
        "metric.type=\"run.googleapis.com/request_count\"",
        "resource.type=\"cloud_run_revision\"",
        "resource.label.\"service_name\"=\"${google_cloud_run_v2_service.agent_hr_api.name}\""
      ])
    }
  }
}

resource "google_monitoring_slo" "agent_hr_api_latency" {
  service      = google_monitoring_custom_service.agent_hr_api_svc.service_id
  slo_id       = "agent-hr-api-latency-${terraform.workspace}"
  display_name = "Latency p95 < 30s - Agent HR API"

  goal                = 0.95
  rolling_period_days = 30

  request_based_sli {
    distribution_cut {
      distribution_filter = join(" ", [
        "metric.type=\"run.googleapis.com/request_latencies\"",
        "resource.type=\"cloud_run_revision\"",
        "resource.label.\"service_name\"=\"${google_cloud_run_v2_service.agent_hr_api.name}\""
      ])
      range {
        max = 30.0 # 30 000ms — appels MCP chaînés + raisonnement LLM RH
      }
    }
  }
}
