# =========================================================
# Platform Engineering - Cloud Run Job & Service Account
# =========================================================

# Service Account dedicated to running Platform Engineering jobs
resource "google_service_account" "platform_engineering_sa" {
  account_id   = "sa-platform-eng"
  display_name = "Platform Engineering Execution SA"
  description  = "Service account for executing Manage Env scripts asynchronously"
}

# Assign required permissions for Terraform to deploy architecture
locals {
  platform_roles = [
    "roles/editor",
    "roles/resourcemanager.projectIamAdmin",
    "roles/iam.serviceAccountAdmin",
    "roles/iam.serviceAccountUser",
    "roles/secretmanager.admin",
    "roles/alloydb.admin",
    "roles/pubsub.admin",
    "roles/run.admin",
    "roles/bigquery.admin",
    "roles/compute.networkAdmin"
  ]
}

resource "google_project_iam_member" "platform_sa_roles" {
  for_each   = toset(local.platform_roles)
  project    = var.project_id
  role       = each.key
  member     = "serviceAccount:${google_service_account.platform_engineering_sa.email}"
  depends_on = [google_service_account.platform_engineering_sa]
}

# Secret Accessor to read the Gemini API Key into terraform
resource "google_secret_manager_secret_iam_member" "platform_sa_gemini_key_access" {
  secret_id = google_secret_manager_secret.gemini_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.platform_engineering_sa.email}"
}

# Define the Cloud Run v2 Job
resource "google_cloud_run_v2_job" "platform_engineering_job" {
  name     = "platform-engineering"
  location = var.region

  template {
    template {
      service_account = google_service_account.platform_engineering_sa.email
      timeout         = "86400s" # 24 Hours maximum execution time
      max_retries     = 0        # No retries on failure (deployment should fail fast if there's a problem)

      containers {
        # Lors du bootstrap initial, l'image n'existe pas encore dans GAR.
        # Nous utilisons une image Dummy pour valider Terraform.
        # Le trigger asynchrone (async_manage_env.sh) viendra écraser cette image avec la vraie locale.
        image = "us-docker.pkg.dev/cloudrun/container/job:latest"

        resources {
          limits = {
            cpu    = "1000m"
            memory = "512Mi"
          }
        }

        # Mount the Google API Key as an environment variable
        env {
          name = "GOOGLE_API_KEY"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.gemini_api_key.id
              version = "latest"
            }
          }
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [
      client,
      client_version,

      template[0].template[0].containers[0].image,
      template[0].template[0].containers[0].args,
      template[0].template[0].containers[0].env,
    ]
  }

  depends_on = [
    google_project_iam_member.platform_sa_roles
  ]
}

# =========================================================
# Google Drive API Service Accounts (Persistent)
# =========================================================
resource "google_service_account" "drive_sa_dev" {
  account_id   = "sa-drive-dev-v2"
  display_name = "Drive API Service Account (dev)"
  description  = "Service Account interact with Drive API in dev environment"
}

resource "google_service_account" "drive_sa_staging" {
  account_id   = "sa-drive-staging-v2"
  display_name = "Drive API Service Account (staging)"
  description  = "Service Account interact with Drive API in staging environment"
}
