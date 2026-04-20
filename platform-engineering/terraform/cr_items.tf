resource "google_cloud_run_v2_service" "items_api" {
  name     = "items-api-${terraform.workspace}"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  template {
    service_account = google_service_account.items_sa.email

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
      image   = var.image_items
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
        value = "postgresql://${replace(google_service_account.items_sa.email, ".gserviceaccount.com", "")}@${google_alloydb_instance.primary.ip_address}:5432/items"
      }
      env {
        name  = "ROOT_PATH"
        value = "/api/items"
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
        value = var.items_api_version
      }
      env {
        name  = "MCP_SIDECAR_URL"
        value = "http://localhost:8081"
      }
      env {
        name  = "USERS_API_URL"
        value = "http://api.internal.zenika/api/users/"
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
      image   = var.image_items
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
        value = var.items_api_version
      }
      env {
        name  = "ITEMS_API_URL"
        value = "http://localhost:8080"
      }
    }
  }

  lifecycle {
    ignore_changes = [
      client,
      client_version,

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
resource "google_service_account" "items_sa" {
  account_id                   = "sa-items-${terraform.workspace}-${random_id.sa_suffix.hex}"
  create_ignore_already_exists = true
}

resource "google_secret_manager_secret_iam_member" "items_jwt_access" {
  project   = data.google_secret_manager_secret.jwt_secret.project
  secret_id = data.google_secret_manager_secret.jwt_secret.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.items_sa.email}"
}

resource "google_project_iam_member" "items_otel_trace" {
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.items_sa.email}"
}

resource "google_project_iam_member" "items_otel_metric" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.items_sa.email}"
}

resource "google_project_iam_member" "items_alloydb_client" {
  project = var.project_id
  role    = "roles/alloydb.client"
  member  = "serviceAccount:${google_service_account.items_sa.email}"
}

resource "google_project_iam_member" "items_alloydb_databaseUser" {
  project = var.project_id
  role    = "roles/alloydb.databaseUser"
  member  = "serviceAccount:${google_service_account.items_sa.email}"
}

resource "google_alloydb_user" "items_db_user" {
  cluster    = google_alloydb_cluster.main.name
  user_id    = replace(google_service_account.items_sa.email, ".gserviceaccount.com", "")
  user_type  = "ALLOYDB_IAM_USER"
  depends_on = [google_alloydb_instance.primary]
  lifecycle {
    ignore_changes = [
    database_roles]
  }
}

# Autorisation invocation interne LB
resource "google_cloud_run_v2_service_iam_member" "items_invoker" {
  project  = google_cloud_run_v2_service.items_api.project
  location = google_cloud_run_v2_service.items_api.location
  name     = google_cloud_run_v2_service.items_api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ==========================================
# Routage et Load Balancing
# ==========================================
resource "google_compute_region_network_endpoint_group" "items_neg" {
  name                  = "neg-items-${terraform.workspace}"
  network_endpoint_type = "SERVERLESS"
  region                = var.region
  cloud_run {
    service = google_cloud_run_v2_service.items_api.name
  }
}

resource "google_compute_backend_service" "items_backend" {
  name                  = "backend-items-${terraform.workspace}"
  protocol              = "HTTPS"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  security_policy       = google_compute_security_policy.waf.id
  backend {
    group = google_compute_region_network_endpoint_group.items_neg.id
  }
}

resource "google_compute_region_backend_service" "items_internal_backend" {
  name                  = "backend-internal-items-${terraform.workspace}"
  region                = var.region
  protocol              = "HTTP"
  load_balancing_scheme = "INTERNAL_MANAGED"
  backend {
    group           = google_compute_region_network_endpoint_group.items_neg.id
    balancing_mode  = "UTILIZATION"
    capacity_scaler = 1.0
  }
}

# ==============================================================
# Monitoring Custom Service & SLOs
# Latence cible : 300ms (API REST catalogue/référentiel)
# Disponibilité : 99.9% sur 30 jours glissants
# ==============================================================
resource "google_monitoring_custom_service" "items_api_svc" {
  service_id   = "items-api-service-${terraform.workspace}"
  display_name = "Items API Service"

  telemetry {
    resource_name = "//run.googleapis.com/projects/${var.project_id}/locations/${var.region}/services/${google_cloud_run_v2_service.items_api.name}"
  }
}

resource "google_monitoring_slo" "items_api_availability" {
  service      = google_monitoring_custom_service.items_api_svc.service_id
  slo_id       = "items-api-availability-${terraform.workspace}"
  display_name = "Availability 99.9% - Items API"

  goal                = 0.999
  rolling_period_days = 30

  request_based_sli {
    good_total_ratio {
      good_service_filter = join(" ", [
        "metric.type=\"run.googleapis.com/request_count\"",
        "resource.type=\"cloud_run_revision\"",
        "resource.label.\"service_name\"=\"${google_cloud_run_v2_service.items_api.name}\"",
        "metric.label.\"response_code_class\"!=\"5xx\""
      ])
      total_service_filter = join(" ", [
        "metric.type=\"run.googleapis.com/request_count\"",
        "resource.type=\"cloud_run_revision\"",
        "resource.label.\"service_name\"=\"${google_cloud_run_v2_service.items_api.name}\""
      ])
    }
  }
}

resource "google_monitoring_slo" "items_api_latency" {
  service      = google_monitoring_custom_service.items_api_svc.service_id
  slo_id       = "items-api-latency-${terraform.workspace}"
  display_name = "Latency p95 < 300ms - Items API"

  goal                = 0.95
  rolling_period_days = 30

  request_based_sli {
    distribution_cut {
      distribution_filter = join(" ", [
        "metric.type=\"run.googleapis.com/request_latencies\"",
        "resource.type=\"cloud_run_revision\"",
        "resource.label.\"service_name\"=\"${google_cloud_run_v2_service.items_api.name}\""
      ])
      range {
        max = 0.3 # 300ms
      }
    }
  }
}
