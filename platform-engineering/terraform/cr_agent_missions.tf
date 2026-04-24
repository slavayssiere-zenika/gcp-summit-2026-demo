resource "google_cloud_run_v2_service" "agent_missions_api" {
  name                = "agent-missions-api-${terraform.workspace}"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
  deletion_protection = false

  template {
    service_account = google_service_account.agent_missions_sa.email
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
    # Timeout étendu : le pipeline de staffing (get_mission + search_best_candidates
    # + get_candidate_rag_context x3 + LLM) peut prendre jusqu'à 90s.
    timeout = "120s"
    containers {
      name    = "api"
      image   = var.image_agent_missions
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
          # Plus de mémoire que HR : le contexte RAG des candidats est plus volumineux
          memory = "1536Mi"
        }
      }

      # ── Secrets (jamais en clair dans le Dockerfile) ──────────────────────
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
        name = "SECRET_KEY"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret.jwt_secret.secret_id
            version = "latest"
          }
        }
      }

      # ── Comportement applicatif ────────────────────────────────────────────
      env {
        name  = "GEMINI_MODEL"
        value = var.gemini_model
      }
      env {
        name  = "ROOT_PATH"
        value = "/agent-missions-api"
      }
      env {
        name  = "APP_VERSION"
        value = var.agent_missions_api_version
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
        name  = "TRACE_EXPORTER"
        value = "gcp"
      }
      env {
        name  = "TRACE_SAMPLING_RATE"
        value = var.trace_sampling_rate
      }

      # ── Infrastructure ─────────────────────────────────────────────────────
      # Redis DB 12 — distinct de HR (10), Ops (11), Router (9), missions_api REST (8)
      env {
        name  = "REDIS_URL"
        value = "redis://${google_redis_instance.cache.host}:${google_redis_instance.cache.port}/12"
      }

      # ── MCP Sidecars via LB interne ────────────────────────────────────────
      # Note : ces URLs pointent vers les endpoints /mcp/tools et /mcp/call
      # exposés publiquement (sans JWT) sur chaque microservice REST.
      env {
        name  = "MISSIONS_MCP_URL"
        value = "http://api.internal.zenika/api/missions/"
      }
      env {
        name  = "CV_MCP_URL"
        value = "http://api.internal.zenika/api/cv/"
      }
      env {
        name  = "USERS_MCP_URL"
        value = "http://api.internal.zenika/api/users/"
      }
      env {
        name  = "COMPETENCIES_MCP_URL"
        value = "http://api.internal.zenika/api/competencies/"
      }

      # ── Services support ───────────────────────────────────────────────────
      env {
        name  = "PROMPTS_API_URL"
        value = "http://api.internal.zenika/api/prompts/"
      }
      env {
        name  = "ANALYTICS_MCP_URL"
        value = "http://api.internal.zenika/api/analytics/"
      }
      env {
        name  = "MONITORING_MCP_URL"
        value = "http://api.internal.zenika/monitoring-mcp/"
      }
    }
  }

  lifecycle {
    ignore_changes = [
      client,
      client_version,
      scaling,

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
resource "google_service_account" "agent_missions_sa" {
  account_id                   = "sa-agent-missions-${terraform.workspace}-${random_id.sa_suffix.hex}"
  create_ignore_already_exists = true
}

# Accès JWT Secret
resource "google_secret_manager_secret_iam_member" "agent_missions_jwt_access" {
  project   = data.google_secret_manager_secret.jwt_secret.project
  secret_id = data.google_secret_manager_secret.jwt_secret.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.agent_missions_sa.email}"
}

# Accès Gemini API Key
resource "google_secret_manager_secret_iam_member" "agent_missions_gemini_access" {
  project   = data.google_secret_manager_secret.gemini_api_key.project
  secret_id = data.google_secret_manager_secret.gemini_api_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.agent_missions_sa.email}"
}

# OTel Trace
resource "google_project_iam_member" "agent_missions_otel_trace" {
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.agent_missions_sa.email}"
}

# Prometheus Metrics
resource "google_project_iam_member" "agent_missions_otel_metric" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.agent_missions_sa.email}"
}

# Logging Viewer (pour OTel log export GCP)
resource "google_project_iam_member" "agent_missions_logging_viewer" {
  project = var.project_id
  role    = "roles/logging.viewer"
  member  = "serviceAccount:${google_service_account.agent_missions_sa.email}"
}

# Autorisation invocation LB interne (allUsers pour le LB interne)
resource "google_cloud_run_v2_service_iam_member" "agent_missions_invoker" {
  project  = google_cloud_run_v2_service.agent_missions_api.project
  location = google_cloud_run_v2_service.agent_missions_api.location
  name     = google_cloud_run_v2_service.agent_missions_api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ==========================================
# Routage et Load Balancing
# ==========================================
resource "google_compute_region_network_endpoint_group" "agent_missions_neg" {
  name                  = "neg-agent-missions-${terraform.workspace}"
  network_endpoint_type = "SERVERLESS"
  region                = var.region
  cloud_run {
    service = google_cloud_run_v2_service.agent_missions_api.name
  }
}

# Backend interne (accès inter-services via LB interne régional)
resource "google_compute_region_backend_service" "agent_missions_internal_backend" {
  name                  = "backend-internal-agent-missions-${terraform.workspace}"
  region                = var.region
  protocol              = "HTTP"
  load_balancing_scheme = "INTERNAL_MANAGED"
  backend {
    group           = google_compute_region_network_endpoint_group.agent_missions_neg.id
    balancing_mode  = "UTILIZATION"
    capacity_scaler = 1.0
  }
}

# Backend externe (LB global HTTPS — exposé via /api/agent-missions/ dans lb.tf)
resource "google_compute_backend_service" "agent_missions_backend" {
  name                  = "backend-agent-missions-${terraform.workspace}"
  protocol              = "HTTPS"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  security_policy       = google_compute_security_policy.waf.id
  backend {
    group = google_compute_region_network_endpoint_group.agent_missions_neg.id
  }
}

# ==============================================================
# Monitoring Custom Service & SLOs
#
# Latence cible : 60 000ms  — Pipeline staffing multi-étapes :
#   get_mission (MCP) + search_best_candidates (PgVector) +
#   get_candidate_rag_context x3 + raisonnement LLM Gemini.
#   Plus long que HR (30s) car le RAG contextuel est séquentiel.
#
# Disponibilité : 99.5% sur 30 jours glissants
# ==============================================================
resource "google_monitoring_custom_service" "agent_missions_api_svc" {
  service_id   = "agent-missions-api-service-${terraform.workspace}"
  display_name = "Agent Missions API Service"

  telemetry {
    resource_name = "//run.googleapis.com/projects/${var.project_id}/locations/${var.region}/services/${google_cloud_run_v2_service.agent_missions_api.name}"
  }
}

resource "google_monitoring_slo" "agent_missions_api_availability" {
  service      = google_monitoring_custom_service.agent_missions_api_svc.service_id
  slo_id       = "agent-missions-api-availability-${terraform.workspace}"
  display_name = "Availability 99.5% - Agent Missions API"

  goal                = 0.995
  rolling_period_days = 30

  request_based_sli {
    good_total_ratio {
      good_service_filter = join(" ", [
        "metric.type=\"run.googleapis.com/request_count\"",
        "resource.type=\"cloud_run_revision\"",
        "resource.label.\"service_name\"=\"${google_cloud_run_v2_service.agent_missions_api.name}\"",
        "metric.label.\"response_code_class\"!=\"5xx\""
      ])
      total_service_filter = join(" ", [
        "metric.type=\"run.googleapis.com/request_count\"",
        "resource.type=\"cloud_run_revision\"",
        "resource.label.\"service_name\"=\"${google_cloud_run_v2_service.agent_missions_api.name}\""
      ])
    }
  }
}

resource "google_monitoring_slo" "agent_missions_api_latency" {
  service      = google_monitoring_custom_service.agent_missions_api_svc.service_id
  slo_id       = "agent-missions-api-latency-${terraform.workspace}"
  display_name = "Latency p95 < 60s - Agent Missions API"

  goal                = 0.95
  rolling_period_days = 30

  request_based_sli {
    distribution_cut {
      distribution_filter = join(" ", [
        "metric.type=\"run.googleapis.com/request_latencies\"",
        "resource.type=\"cloud_run_revision\"",
        "resource.label.\"service_name\"=\"${google_cloud_run_v2_service.agent_missions_api.name}\""
      ])
      range {
        max = 60.0 # 60 000ms — pipeline staffing (MCP + PgVector + RAG + LLM)
      }
    }
  }
}
