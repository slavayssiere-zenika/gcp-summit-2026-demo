# ==============================================================
# Cloud Run Job — DB Init (IAM AlloyDB Schema Grants)
# ==============================================================
# Ce job initialise les bases de données AlloyDB et octroie les
# permissions IAM aux service accounts de chaque microservice.
#
# Image dédiée : db_init (cf. /db_init/Dockerfile)
# Exécution : via deploy.sh -> build + gcloud run jobs execute
# ==============================================================

# Le Service Account du job db_init dispose d'un accès au secret
# du mot de passe root AlloyDB (via le SA du service users_api pour
# éviter de créer un SA supplémentaire pour une tâche ponctuelle).
resource "google_secret_manager_secret_iam_member" "alloydb_password_access" {
  project   = google_secret_manager_secret.alloydb_password.project
  secret_id = google_secret_manager_secret.alloydb_password.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.users_sa.email}"
}

# Définition du Cloud Run Job (image dédiée db_init)
resource "google_cloud_run_v2_job" "db_init" {
  name                = "db-init-job-${terraform.workspace}"
  location            = var.region
  deletion_protection = false

  template {
    template {
      # Réutilise le SA de users_api (accès Secret Manager + AlloyDB IAM déjà configurés)
      service_account = google_service_account.users_sa.email

      # Accès VPC requis pour joindre l'IP privée AlloyDB
      vpc_access {
        network_interfaces {
          network    = google_compute_network.main.id
          subnetwork = google_compute_subnetwork.main.id
          tags       = ["cr-egress"]
        }
      }

      containers {
        # Image dédiée db_init — construite et poussée par deploy.sh
        # Source : /db_init/Dockerfile — asyncpg only, ~80MB, non-root
        image   = var.image_db_init
        command = ["python3"]
        args    = ["-m", "db_init"]

        # Mot de passe root AlloyDB (depuis Secret Manager)
        env {
          name = "ROOT_DB_URL"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.alloydb_password.secret_id
              version = "latest"
            }
          }
        }
        # IP privée de l'instance AlloyDB primary (accessible uniquement depuis le VPC)
        env {
          name  = "DB_IP"
          value = google_alloydb_instance.primary.ip_address
        }
        env {
          name  = "PROJECT_ID"
          value = var.project_id
        }
        env {
          name  = "ENV_VAL"
          value = terraform.workspace
        }
        env {
          name  = "SA_SUFFIX"
          value = random_id.sa_suffix.hex
        }
        env {
          name  = "ADMIN_USER"
          value = var.admin_user
        }
      }
    }
  }

  depends_on = [
    google_secret_manager_secret_iam_member.alloydb_password_access,
  ]
}

# Déclencheur du Cloud Run Job via local-exec
# Note : exécuté uniquement quand la définition du job change (trigger sur l'ID).
# Pour un déclenchement manuel : deploy.sh db_init
resource "null_resource" "run_db_init_job" {
  triggers = {
    job_updated = google_cloud_run_v2_job.db_init.id
  }

  provisioner "local-exec" {
    on_failure = continue # Ne pas bloquer l'apply si le job a déjà réussi
    command    = "gcloud run jobs execute ${google_cloud_run_v2_job.db_init.name} --region ${var.region} --project ${var.project_id} --wait"
  }

  depends_on = [
    google_cloud_run_v2_job.db_init,
    google_alloydb_user.users_db_user,
    google_alloydb_user.admin_user,
  ]
}
