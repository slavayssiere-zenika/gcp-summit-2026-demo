# ==============================================================================
# Service Cloud Run - Grafana
# ==============================================================================

# 1. Compte de service dédié à Grafana
resource "google_service_account" "grafana_sa" {
  account_id   = "grafana-sa-${terraform.workspace}"
  display_name = "Service Account for Grafana on Cloud Run"
}

# 2. Rôles IAM requis pour interroger l'observabilité GCP (Zéro-Trust)
resource "google_project_iam_member" "grafana_trace" {
  project = var.project_id
  role    = "roles/cloudtrace.user"
  member  = "serviceAccount:${google_service_account.grafana_sa.email}"
}

resource "google_project_iam_member" "grafana_monitoring" {
  project = var.project_id
  role    = "roles/monitoring.viewer"
  member  = "serviceAccount:${google_service_account.grafana_sa.email}"
}

resource "google_project_iam_member" "grafana_logging" {
  project = var.project_id
  role    = "roles/logging.viewer"
  member  = "serviceAccount:${google_service_account.grafana_sa.email}"
}

# Accès au mot de passe DB et aux clés Google OAuth2 dans Secret Manager
resource "google_secret_manager_secret_iam_member" "grafana_db_pass" {
  secret_id = google_secret_manager_secret.grafana_db_password.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.grafana_sa.email}"
}

resource "google_secret_manager_secret_iam_member" "grafana_oauth_id_pass" {
  secret_id = data.google_secret_manager_secret.google_secret_id.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.grafana_sa.email}"
}

resource "google_secret_manager_secret_iam_member" "grafana_oauth_key_pass" {
  secret_id = data.google_secret_manager_secret.google_secret_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.grafana_sa.email}"
}

# 3. Service Cloud Run Grafana (Interne au Load Balancer)
resource "google_cloud_run_v2_service" "grafana" {
  name                = "grafana-${terraform.workspace}"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
  deletion_protection = false

  template {
    max_instance_request_concurrency = var.cloudrun_concurrency
    service_account                  = google_service_account.grafana_sa.email

    scaling {
      min_instance_count = 1
      max_instance_count = 2
    }

    # Connexion au VPC pour joindre AlloyDB via son IP privée
    vpc_access {
      network_interfaces {
        network    = google_compute_network.main.id
        subnetwork = google_compute_subnetwork.main.id
        tags       = ["cr-egress"]
      }
      egress = "PRIVATE_RANGES_ONLY"
    }

    containers {
      name  = "grafana"
      image = var.image_grafana

      ports {
        container_port = 8080
      }

      # Connexion DB (AlloyDB)
      env {
        name  = "GF_DATABASE_TYPE"
        value = "postgres"
      }
      env {
        name  = "GF_DATABASE_HOST"
        value = "${google_alloydb_instance.primary.ip_address}:5432"
      }
      env {
        name  = "GF_DATABASE_NAME"
        value = "grafana"
      }
      env {
        name  = "GF_DATABASE_USER"
        value = "grafana"
      }
      env {
        name = "GF_DATABASE_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.grafana_db_password.secret_id
            version = "latest"
          }
        }
      }
      env {
        name  = "GF_DATABASE_SSL_MODE"
        value = "require"
      }

      # Configuration Google OAuth2
      env {
        name  = "GF_AUTH_GOOGLE_ENABLED"
        value = "true"
      }
      env {
        name = "GF_AUTH_GOOGLE_CLIENT_ID"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret.google_secret_id.secret_id
            version = var.google_secret_version
          }
        }
      }
      env {
        name = "GF_AUTH_GOOGLE_CLIENT_SECRET"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret.google_secret_key.secret_id
            version = var.google_secret_version
          }
        }
      }
      env {
        name  = "GF_AUTH_GOOGLE_ALLOWED_DOMAINS"
        value = "zenika.ca zenika.com"
      }
      # Assignation dynamique du rôle d'administrateur pour l'email de la variable admin_user
      env {
        name  = "GF_AUTH_GOOGLE_ROLE_ATTRIBUTE_PATH"
        value = "email == '${var.admin_user}' && 'Admin' || 'Viewer'"
      }
      env {
        name  = "GF_SERVER_ROOT_URL"
        value = "https://grafana.${terraform.workspace}.${var.base_domain}"
      }
    }
  }

  depends_on = [
    null_resource.run_db_init_job
  ]
}

resource "google_compute_region_network_endpoint_group" "grafana_neg" {
  name                  = "neg-grafana-${terraform.workspace}"
  network_endpoint_type = "SERVERLESS"
  region                = var.region
  cloud_run {
    service = google_cloud_run_v2_service.grafana.name
  }
}

resource "google_compute_backend_service" "grafana_backend" {
  name                  = "backend-grafana-${terraform.workspace}"
  protocol              = "HTTPS"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  security_policy       = google_compute_security_policy.waf.id
  backend {
    group = google_compute_region_network_endpoint_group.grafana_neg.id
  }
}

