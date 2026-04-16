resource "google_cloud_run_v2_service" "market_mcp" {
  name     = "market-mcp-${terraform.workspace}"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  template {
    service_account = google_service_account.market_sa.email
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
      args    = ["-m", "uvicorn", "mcp_app:app", "--host", "0.0.0.0", "--port", "8080", "--no-server-header"]
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
        name  = "ROOT_PATH"
        value = ""
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
        value = "http://api.internal.zenika/api/users/" # Added for kill-switch HTTP call
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
}

# ==========================================
# Identité et Permissions
# ==========================================
resource "google_service_account" "market_sa" {
  account_id                   = "sa-market-${terraform.workspace}-${random_id.sa_suffix.hex}"
  create_ignore_already_exists = true
}

resource "google_secret_manager_secret_iam_member" "market_jwt_access" {
  project   = data.google_secret_manager_secret.jwt_secret.project
  secret_id = data.google_secret_manager_secret.jwt_secret.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.market_sa.email}"
}

resource "google_project_iam_member" "market_otel_trace" {
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.market_sa.email}"
}

resource "google_project_iam_member" "market_otel_metric" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.market_sa.email}"
}

# Autorisation invocation interne LB
resource "google_cloud_run_v2_service_iam_member" "market_invoker" {
  project  = google_cloud_run_v2_service.market_mcp.project
  location = google_cloud_run_v2_service.market_mcp.location
  name     = google_cloud_run_v2_service.market_mcp.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ==========================================
# Routage et Load Balancing
# ==========================================
resource "google_compute_region_network_endpoint_group" "market_neg" {
  name                  = "neg-market-${terraform.workspace}"
  network_endpoint_type = "SERVERLESS"
  region                = var.region
  cloud_run {
    service = google_cloud_run_v2_service.market_mcp.name
  }
}

resource "google_compute_region_backend_service" "market_internal_backend" {
  name                  = "backend-internal-market-${terraform.workspace}"
  region                = var.region
  protocol              = "HTTP"
  load_balancing_scheme = "INTERNAL_MANAGED"
  backend {
    group           = google_compute_region_network_endpoint_group.market_neg.id
    balancing_mode  = "UTILIZATION"
    capacity_scaler = 1.0
  }
}

# Backend global (EXTERNAL_MANAGED) pour accès via le LB externe (frontend AIOps, Admin)
resource "google_compute_backend_service" "market_backend" {
  name                  = "backend-market-${terraform.workspace}"
  protocol              = "HTTPS"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  security_policy       = google_compute_security_policy.waf.id
  backend {
    group = google_compute_region_network_endpoint_group.market_neg.id
  }
}

resource "google_project_iam_member" "market_bq_admin" {
  project = var.project_id
  role    = "roles/bigquery.admin"
  member  = "serviceAccount:${google_service_account.market_sa.email}"
}
resource "google_project_iam_member" "market_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.market_sa.email}"
}
resource "google_project_iam_member" "market_trace_user" {
  project = var.project_id
  role    = "roles/cloudtrace.user"
  member  = "serviceAccount:${google_service_account.market_sa.email}"
}

resource "google_project_iam_member" "market_logging_viewer" {
  project = var.project_id
  role    = "roles/logging.viewer"
  member  = "serviceAccount:${google_service_account.market_sa.email}"
}

resource "google_project_iam_member" "market_run_viewer" {
  project = var.project_id
  role    = "roles/run.viewer"
  member  = "serviceAccount:${google_service_account.market_sa.email}"
}

# ==============================================================
# Monitoring Custom Service & SLOs
# Latence cible : 1000ms (appels BigQuery FinOps + agrégations)
# Disponibilité : 99.5% sur 30 jours glissants
# Note : le service s'appelle market-mcp (pas market-api)
# ==============================================================
resource "google_monitoring_custom_service" "market_mcp_svc" {
  service_id   = "market-mcp-service-${terraform.workspace}"
  display_name = "Market & FinOps MCP Service"

  telemetry {
    resource_name = "//run.googleapis.com/projects/${var.project_id}/locations/${var.region}/services/${google_cloud_run_v2_service.market_mcp.name}"
  }
}

resource "google_monitoring_slo" "market_mcp_availability" {
  service      = google_monitoring_custom_service.market_mcp_svc.service_id
  slo_id       = "market-mcp-availability-${terraform.workspace}"
  display_name = "Availability 99.5% - Market & FinOps MCP"

  goal                = 0.995
  rolling_period_days = 30

  request_based_sli {
    good_total_ratio {
      good_service_filter = join(" ", [
        "metric.type=\"run.googleapis.com/request_count\"",
        "resource.type=\"cloud_run_revision\"",
        "resource.label.\"service_name\"=\"${google_cloud_run_v2_service.market_mcp.name}\"",
        "metric.label.\"response_code_class\"!=\"5xx\""
      ])
      total_service_filter = join(" ", [
        "metric.type=\"run.googleapis.com/request_count\"",
        "resource.type=\"cloud_run_revision\"",
        "resource.label.\"service_name\"=\"${google_cloud_run_v2_service.market_mcp.name}\""
      ])
    }
  }
}

resource "google_monitoring_slo" "market_mcp_latency" {
  service      = google_monitoring_custom_service.market_mcp_svc.service_id
  slo_id       = "market-mcp-latency-${terraform.workspace}"
  display_name = "Latency p95 < 1000ms - Market & FinOps MCP"

  goal                = 0.95
  rolling_period_days = 30

  request_based_sli {
    distribution_cut {
      distribution_filter = join(" ", [
        "metric.type=\"run.googleapis.com/request_latencies\"",
        "resource.type=\"cloud_run_revision\"",
        "resource.label.\"service_name\"=\"${google_cloud_run_v2_service.market_mcp.name}\""
      ])
      range {
        max = 1.0 # 1000ms — requêtes BigQuery FinOps + kill-switch
      }
    }
  }
}
