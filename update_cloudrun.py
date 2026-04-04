import re

with open("platform-engineering/terraform/cloudrun.tf.orig", "r") as f:
    text = f.read()

text = text.replace("  depends_on = [\n", "  depends_on = [\n    google_project_iam_member.alloydb_client,\n    google_project_iam_member.alloydb_databaseUser,\n")

envs = """      env {
        name  = "USERS_MCP_URL"
        value = "http://api.internal.zenika/mcp-users/"
      }
      env {
        name  = "ITEMS_MCP_URL"
        value = "http://api.internal.zenika/mcp-items/"
      }
      env {
        name  = "COMPETENCIES_MCP_URL"
        value = "http://api.internal.zenika/mcp-comp/"
      }
      env {
        name  = "CV_MCP_URL"
        value = "http://api.internal.zenika/mcp-cv/"
      }
      env {
        name  = "DRIVE_MCP_URL"
        value = "http://api.internal.zenika/mcp-drive/"
      }
      env {"""
text = text.replace("      env {\n        name  = \"ITEMS_API_URL\"", envs + "\n        name  = \"ITEMS_API_URL\"")

pattern = r"    # Conteneur Sidecar \(MCP\)\n    containers \{\n      name    = \"mcp\".*?env \{\n        name  = \"[A-Z_]+API_URL\"\n        value = \"http://(?:localhost:8080|api\.internal\.zenika/.*)\".*?\n      \}\n    \}\n"
text = re.sub(pattern, "", text, flags=re.DOTALL)

text = re.sub(r",\n\s+template\[0\]\.containers\[1\]\.resources\[0\]\.limits\[\"cpu\"\]", "", text)

new_services = """
# ==============================================================
# Standalone MCP Services
# ==============================================================
resource "google_cloud_run_v2_service" "standalone_mcp" {
  for_each = toset(local.mcp_services)
  name     = "mcp-${each.value}-api-${terraform.workspace}"
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

    containers {
      name    = "mcp"
      image   = local.mcp_images[each.key]
      command = ["python"]
      args    = ["mcp_app.py"]
      ports {
        container_port = 8080
      }
      startup_probe {
        initial_delay_seconds = 5
        timeout_seconds       = 3
        period_seconds        = 5
        failure_threshold     = 5
        http_get {
          path = "/health"
          port = 8080
        }
      }
      liveness_probe {
        initial_delay_seconds = 10
        timeout_seconds       = 3
        period_seconds        = 10
        failure_threshold     = 3
        http_get {
          path = "/health"
          port = 8080
        }
      }
      resources {
        limits = {
          memory = "512Mi"
        }
      }

      env {
        name  = "${upper(each.key)}_API_URL"
        value = "http://api.internal.zenika/${each.key}-api/" 
      }
      env {
        name  = "USE_GCP_LOGGING"
        value = "true"
      }
      env {
        name  = "MCP_PORT"
        value = "8080"
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].resources[0].limits["cpu"]
    ]
  }

  depends_on = [
    google_project_iam_member.alloydb_client,
    google_project_iam_member.alloydb_databaseUser,
    google_secret_manager_secret_iam_member.jwt_secret_access,
    google_secret_manager_secret_iam_member.gemini_secret_access,
    google_secret_manager_secret_iam_member.admin_password_access,
    null_resource.run_db_migrations_job
  ]
}

resource "google_cloud_run_v2_service_iam_member" "standalone_mcp_invoker" {
  for_each = toset(local.mcp_services)
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.standalone_mcp[each.key].name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_compute_region_network_endpoint_group" "standalone_mcp_neg" {
  for_each              = toset(local.mcp_services)
  name                  = "neg-mcp-${each.value}-${terraform.workspace}"
  network_endpoint_type = "SERVERLESS"
  region                = var.region
  cloud_run {
    service = google_cloud_run_v2_service.standalone_mcp[each.key].name
  }
}

resource "google_cloud_run_v2_service" "standalone_drive_mcp" {
  name     = "mcp-drive-api-${terraform.workspace}"
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
      name    = "mcp"
      image   = var.image_drive
      command = ["python"]
      args    = ["mcp_app.py"]
      ports {
        container_port = 8080
      }
      startup_probe {
        initial_delay_seconds = 5
        timeout_seconds       = 3
        period_seconds        = 5
        failure_threshold     = 5
        http_get {
          path = "/health"
          port = 8080
        }
      }
      liveness_probe {
        initial_delay_seconds = 10
        timeout_seconds       = 3
        period_seconds        = 10
        failure_threshold     = 3
        http_get {
          path = "/health"
          port = 8080
        }
      }
      resources {
        limits = {
          memory = "512Mi"
        }
      }

      env {
        name  = "DRIVE_API_URL"
        value = "http://api.internal.zenika/drive-api/"
      }
      env {
        name  = "USE_GCP_LOGGING"
        value = "true"
      }
      env {
        name  = "MCP_PORT"
        value = "8080"
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].resources[0].limits["cpu"]
    ]
  }

  depends_on = [
    google_project_iam_member.alloydb_client,
    google_project_iam_member.alloydb_databaseUser,
    google_secret_manager_secret_iam_member.jwt_secret_access,
    google_secret_manager_secret_iam_member.gemini_secret_access,
    null_resource.run_db_migrations_job
  ]
}

resource "google_cloud_run_v2_service_iam_member" "standalone_drive_mcp_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.standalone_drive_mcp.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_compute_region_network_endpoint_group" "standalone_drive_mcp_neg" {
  name                  = "neg-mcp-drive-${terraform.workspace}"
  network_endpoint_type = "SERVERLESS"
  region                = var.region
  cloud_run {
    service = google_cloud_run_v2_service.standalone_drive_mcp.name
  }
}
"""
text += new_services

with open("platform-engineering/terraform/cloudrun.tf", "w") as f:
    f.write(text)
