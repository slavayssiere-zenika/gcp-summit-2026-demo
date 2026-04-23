# ==============================================================
# Cloud Run Job for Liquibase Migrations
# ==============================================================

resource "google_cloud_run_v2_job" "db_migrations" {
  name                = "db-migrations-job-${terraform.workspace}"
  location            = var.region
  deletion_protection = false

  template {
    template {
      service_account = google_service_account.users_sa.email

      vpc_access {
        network_interfaces {
          network    = google_compute_network.main.id
          subnetwork = google_compute_subnetwork.main.id
          tags       = ["cr-egress"]
        }
      }

      containers {
        image = var.image_db_migrations

        env {
          name = "DB_PASSWORD"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.alloydb_password.secret_id
              version = "latest"
            }
          }
        }
        env {
          name  = "DB_HOST"
          value = google_alloydb_instance.primary.ip_address
        }
        env {
          name  = "DB_USER"
          value = "postgres"
        }
      }
    }
  }

  depends_on = [
    google_secret_manager_secret_iam_member.alloydb_password_access,
    google_cloud_run_v2_job.db_init
  ]
}

resource "null_resource" "run_db_migrations_job" {
  triggers = {
    job_updated = google_cloud_run_v2_job.db_migrations.id
  }

  provisioner "local-exec" {
    command = "gcloud run jobs execute ${google_cloud_run_v2_job.db_migrations.name} --region ${var.region} --project ${var.project_id} --wait"
  }

  depends_on = [
    google_cloud_run_v2_job.db_migrations,
    null_resource.run_db_init_job
  ]
}
