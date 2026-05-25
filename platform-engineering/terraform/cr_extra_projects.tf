# =========================================================
# Extra Projects — Ressources plateforme créées par manage_env.py
#
# Pour chaque entrée dans extra_projects[] du YAML, la plateforme
# crée automatiquement :
#   1. Un Service Account dédié (identité Cloud Run du projet externe)
#   2. Les rôles IAM AlloyDB (client + databaseUser) sur le projet
#   3. Un utilisateur IAM AlloyDB lié au SA (pour l'authentification IAM)
#
# Le projet externe gère lui-même son Cloud Run, son NEG, son backend
# et ses routes LB via son propre répertoire terraform/.
#
# Les outputs exposés (service_account_emails, alloydb_ip, tf_state_bucket,
# vpc_network_id, vpc_subnet_id, alloydb_instance_uri) sont lus par
# manage_env.py et injectés en -var= lors du terraform apply du projet externe.
# =========================================================

variable "extra_projects" {
  description = <<-EOT
    Liste des projets externes intégrés à la plateforme.
    Chaque objet contient :
      - name             : nom kebab-case du service (ex: ia-dev-memory)
      - alloydb_database : nom de la base PostgreSQL (ex: ia_dev_memory)
    Les autres champs (path, lb_path, version) sont gérés par manage_env.py
    et ne sont pas transmis à Terraform.
  EOT
  type = list(object({
    name             = string
    alloydb_database = string
  }))
  default = []
}

# ─── Service Accounts ────────────────────────────────────────────────────────

resource "google_service_account" "extra_project_sa" {
  for_each = { for p in var.extra_projects : p.name => p }

  account_id   = "sa-${each.key}-${terraform.workspace}"
  display_name = "Service Account — extra project ${each.key} (${terraform.workspace})"
  project      = var.project_id

  create_ignore_already_exists = true
}

# ─── IAM Roles AlloyDB ───────────────────────────────────────────────────────

resource "google_project_iam_member" "extra_project_alloydb_client" {
  for_each = { for p in var.extra_projects : p.name => p }

  project = var.project_id
  role    = "roles/alloydb.client"
  member  = "serviceAccount:${google_service_account.extra_project_sa[each.key].email}"
}

resource "google_project_iam_member" "extra_project_alloydb_db_user" {
  for_each = { for p in var.extra_projects : p.name => p }

  project = var.project_id
  role    = "roles/alloydb.databaseUser"
  member  = "serviceAccount:${google_service_account.extra_project_sa[each.key].email}"
}

# ─── OTel / Observabilité ────────────────────────────────────────────────────

resource "google_project_iam_member" "extra_project_trace" {
  for_each = { for p in var.extra_projects : p.name => p }

  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.extra_project_sa[each.key].email}"
}

resource "google_project_iam_member" "extra_project_metrics" {
  for_each = { for p in var.extra_projects : p.name => p }

  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.extra_project_sa[each.key].email}"
}

# ─── Utilisateurs IAM AlloyDB ─────────────────────────────────────────────────
# Crée un utilisateur de type ALLOYDB_IAM_USER pour chaque SA de projet externe.
# Le user_id est l'email du SA sans le suffixe .gserviceaccount.com (convention AlloyDB).

resource "google_alloydb_user" "extra_project_db_user" {
  for_each = { for p in var.extra_projects : p.name => p }

  cluster   = google_alloydb_cluster.main.name
  user_id   = replace(google_service_account.extra_project_sa[each.key].email, ".gserviceaccount.com", "")
  user_type = "ALLOYDB_IAM_USER"

  depends_on = [google_alloydb_instance.primary]

  lifecycle {
    ignore_changes = [database_roles]
  }
}

# ─── Outputs : emails des SAs (lus par manage_env.py pour injection) ──────────

output "extra_project_sa_emails" {
  description = "Map {name → email SA} des projets externes. Injecté par manage_env.py en -var=service_account_email."
  value       = { for k, sa in google_service_account.extra_project_sa : k => sa.email }
}
