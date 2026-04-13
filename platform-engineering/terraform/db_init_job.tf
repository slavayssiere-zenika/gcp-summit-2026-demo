# ==============================================================
# Cloud Run Job for IAM DB Initialisation (Grants Schema)
# ==============================================================

# Autorisation pour le Service Account "users" d'accéder au mot de passe root DB
resource "google_secret_manager_secret_iam_member" "alloydb_password_access" {
  project   = google_secret_manager_secret.alloydb_password.project
  secret_id = google_secret_manager_secret.alloydb_password.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cr_sa["users"].email}"
}

# Définition du Job Cloud Run
resource "google_cloud_run_v2_job" "db_init" {
  name     = "db-init-job-${terraform.workspace}"
  location = var.region

  template {
    template {
      service_account = google_service_account.cr_sa["users"].email

      vpc_access {
        network_interfaces {
          network    = google_compute_network.main.id
          subnetwork = google_compute_subnetwork.main.id
          tags       = ["cr-egress"]
        }
      }

      containers {
        image   = var.image_users
        command = ["python", "-c", "import os; exec(os.environ['SCRIPT_PAYLOAD'])"]

        env {
          name = "ROOT_DB_URL"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.alloydb_password.secret_id
              version = "latest"
            }
          }
        }
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
          name  = "SCRIPT_PAYLOAD"
          value = <<-EOT
import os
import asyncio
import asyncpg
import urllib.parse
import sys

root_pw = os.environ['ROOT_DB_URL']
root_pw_encoded = urllib.parse.quote(root_pw)
db_ip = os.environ['DB_IP']
project_id = os.environ["PROJECT_ID"]
env_name = os.environ["ENV_VAL"]
admin_user = os.environ.get("ADMIN_USER")

master_db_url = f"postgresql://postgres:{root_pw_encoded}@{db_ip}:5432/postgres?sslmode=require"
services = ["users", "items", "competencies", "cv", "prompts", "drive", "missions"]
all_iam_services = services + ["agent"]

async def main():
    try:
        print("[DB INIT] Stage 1: Creating Databases and Users from Master...")
        conn = await asyncpg.connect(master_db_url)





        for svc in services:
            try:
                await conn.execute(f"CREATE DATABASE \"{svc}\";")
                print(f"[DB INIT] Created database '{svc}'")
            except Exception as e:
                if "already exists" in str(e):
                    print(f"[DB INIT] Database '{svc}' already exists.")
                else:
                    print(f"[DB INIT] Warning creating DB '{svc}': {e}")

        await conn.close()
        
        print("\n[DB INIT] Stage 2: Granting Schema Permissions per Database...")
        for svc in all_iam_services:
            target_db = "users" if svc == "agent" else svc
            iam_user = f"sa-{svc}-{env_name}-v2@{project_id}.iam"
            svc_db_url = f"postgresql://postgres:{root_pw_encoded}@{db_ip}:5432/{target_db}?sslmode=require"
            
            try:
                svc_conn = await asyncpg.connect(svc_db_url)
                
                try:
                    await svc_conn.execute(f"GRANT ALL ON SCHEMA public TO \"{iam_user}\";")
                    await svc_conn.execute(f"GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO \"{iam_user}\";")
                    await svc_conn.execute(f"GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO \"{iam_user}\";")
                    await svc_conn.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON TABLES TO \"{iam_user}\";")
                    await svc_conn.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON SEQUENCES TO \"{iam_user}\";")
                    print(f"[DB INIT] Granted full permissions on '{target_db}' to '{iam_user}'")
                except Exception as e:
                    print(f"[DB INIT] Warning on {iam_user} for DB {target_db}: {e}")
                
                if admin_user:
                    try:
                        await svc_conn.execute(f"GRANT ALL ON SCHEMA public TO \"{admin_user}\";")
                        await svc_conn.execute(f"GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO \"{admin_user}\";")
                        await svc_conn.execute(f"GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO \"{admin_user}\";")
                        await svc_conn.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON TABLES TO \"{admin_user}\";")
                        await svc_conn.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON SEQUENCES TO \"{admin_user}\";")
                        print(f"[DB INIT] Granted full permissions on '{target_db}' to admin '{admin_user}'")
                    except Exception as e:
                        print(f"[DB INIT] Warning on admin {admin_user} for DB {target_db}: {e}")
                        
                await svc_conn.close()
            except Exception as e:
                print(f"[DB INIT] Global connection error on DB {target_db}: {e}")

        print("\n[DB INIT] Finished successfully.")
    except Exception as e:
        print(f"[DB INIT] Fatal error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    asyncio.run(main())
EOT
        }
        env {
          name  = "ADMIN_USER"
          value = var.admin_user
        }
      }
    }
  }

  depends_on = [
    google_secret_manager_secret_iam_member.alloydb_password_access
  ]
}

# Déclencheur du Cloud Run Job
# S'exécute quand la définition du job Cloud Run change
resource "null_resource" "run_db_init_job" {
  triggers = {
    job_updated = google_cloud_run_v2_job.db_init.id
  }

  provisioner "local-exec" {
    command = "gcloud run jobs execute ${google_cloud_run_v2_job.db_init.name} --region ${var.region} --project ${var.project_id} --wait"
  }

  depends_on = [
    google_cloud_run_v2_job.db_init,
    google_alloydb_user.iam_users,
    google_alloydb_user.admin_user
  ]
}
