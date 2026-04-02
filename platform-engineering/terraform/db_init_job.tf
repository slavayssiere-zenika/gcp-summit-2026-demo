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
import psycopg2

root_pw = os.environ['ROOT_DB_URL']
db_ip = os.environ['DB_IP']
project_id = os.environ["PROJECT_ID"]
env_name = os.environ["ENV_VAL"]
admin_user = os.environ.get("ADMIN_USER")

master_db_url = f"postgresql://postgres:{root_pw}@{db_ip}:5432/postgres?sslmode=require"
services = ["users", "items", "competencies", "cv", "prompts"]

try:
    print("[DB INIT] Stage 1: Creating Databases and Users from Master...")
    conn = psycopg2.connect(master_db_url)
    conn.autocommit = True
    cur = conn.cursor()

    if admin_user:
        try:
            cur.execute(f'CREATE ROLE "{admin_user}" WITH LOGIN IN ROLE alloydb_iam_user;')
            print(f"[DB INIT] Created admin user '{admin_user}'")
        except Exception as e:
            print(f"[DB INIT] Info on admin user '{admin_user}': {e}")

    # L'API Agent possède aussi un service_account
    all_iam_services = services + ["agent"]
    
    # Etape de nettoyage: Pour éviter "cannot drop role... dependencies"
    for svc in services + ["agent"]:
        target_db = "users" if svc == "agent" else svc
        svc_db_url = f"postgresql://postgres:{root_pw}@{db_ip}:5432/{target_db}?sslmode=require"
        try:
            conn_cl = psycopg2.connect(svc_db_url)
            conn_cl.autocommit = True
            cur_cl = conn_cl.cursor()
            for iam_svc in all_iam_services:
                iam_user = f"sa-{iam_svc}-{env_name}-v2@{project_id}.iam"
                try:
                    cur_cl.execute(f'REASSIGN OWNED BY "{iam_user}" TO postgres;')
                    cur_cl.execute(f'DROP OWNED BY "{iam_user}";')
                except Exception:
                    pass
            cur_cl.close()
            conn_cl.close()
        except Exception:
            pass

    for svc in all_iam_services:
        iam_user = f"sa-{svc}-{env_name}-v2@{project_id}.iam"
        try:
            # We DONT create it. We DROP it if it exists from the previous run to fix the Terraform ALLOYDB_IAM_USER conflict.
            cur.execute(f'DROP ROLE IF EXISTS "{iam_user}";')
            print(f"[DB INIT] Cleaned up built-in DB user '{iam_user}'")
        except Exception as e:
            print(f"[DB INIT] Info on user '{iam_user}': {e}")

    for svc in services:
        try:
            cur.execute(f"CREATE DATABASE \"{svc}\";")
            print(f"[DB INIT] Created database '{svc}'")
        except Exception as e:
            if "already exists" in str(e):
                print(f"[DB INIT] Database '{svc}' already exists.")
            else:
                print(f"[DB INIT] Warning creating DB '{svc}': {e}")
                
    cur.close()
    conn.close()
    
    print("\n[DB INIT] Stage 2: Granting Schema Permissions per Database...")
    for svc in services + ["agent"]:
        # Si c'est l'agent, on va dire qu'on le connecte/l'authorise à la bdd 'users' pour ex
        target_db = "users" if svc == "agent" else svc
        iam_user = f"sa-{svc}-{env_name}-v2@{project_id}.iam"
        svc_db_url = f"postgresql://postgres:{root_pw}@{db_ip}:5432/{target_db}?sslmode=require"
        
        try:
            svc_conn = psycopg2.connect(svc_db_url)
            svc_conn.autocommit = True
            svc_cur = svc_conn.cursor()
            svc_cur.execute(f"GRANT ALL ON SCHEMA public TO \"{iam_user}\";")
            svc_cur.close()
            svc_conn.close()
            print(f"[DB INIT] Granted schema public on '{target_db}' to '{iam_user}'")
            
            # Si un utilisateur admin est défini, on lui donne aussi accès au schéma de cette DB
            if admin_user:
                svc_cur.execute(f"GRANT ALL ON SCHEMA public TO \"{admin_user}\";")
                # Optionnellement, s'il a besoin d'être propriétaire de tables/objets créés par les microservices, 
                # on pourrait l'ajouter ici, mais le GRANT ALL sur le schema permet de démarrer.
                # AlloyDB IAM Auth exige typiquement le "user_id" sans '@domaine' pour certain types,
                # mais le Cloud Run Job passe l'identifiant, alors assurons-nous que le script gère l'email.
                print(f"[DB INIT] Granted schema public on '{target_db}' to admin '{admin_user}'")
        except Exception as e:
            print(f"[DB INIT] Warning on {iam_user} or {admin_user} for DB {target_db}: {e}")

    print("\n[DB INIT] Finished successfully.")
    
except Exception as e:
    print(f"[DB INIT] Fatal error: {e}")
    import sys
    sys.exit(1)
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
    google_cloud_run_v2_job.db_init
  ]
}
