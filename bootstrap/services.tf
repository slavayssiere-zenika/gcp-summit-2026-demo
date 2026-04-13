# Liste de toutes les APIs nécessaires au bon fonctionnement
# de la stack complète (Bootstrap + Platform Engineering)

locals {
  services = [
    "compute.googleapis.com",              # VPC, Load Balancer, Subnets, adresses IP globales
    "storage.googleapis.com",              # Buckets GCS (Frontend, Remote State, Loki, Tempo)
    "artifactregistry.googleapis.com",     # Artifact Registry
    "secretmanager.googleapis.com",        # Secret Manager
    "servicenetworking.googleapis.com",    # Private Services Access (Peering interne pour AlloyDB)
    "dns.googleapis.com",                  # Cloud DNS
    "alloydb.googleapis.com",              # Base de données AlloyDB
    "run.googleapis.com",                  # Cloud Run (Compute sans serveur)
    "iam.googleapis.com",                  # Création de Service Accounts Cloud Run
    "cloudresourcemanager.googleapis.com", # API de base pour manipuler le projet et politiques
    "certificatemanager.googleapis.com",   # Si nous utilisons de l'auto-provisionnage de certificats lourds SSL
    "redis.googleapis.com",                # Redis
    "cloudscheduler.googleapis.com",       # Cloud Scheduler
    "bigquery.googleapis.com",             # BigQuery
    "drive.googleapis.com",                # Drive
    "documentai.googleapis.com"            # Document AI (OCR / Sandbox RCE PDF)
  ]
}

resource "google_project_service" "enabled_services" {
  for_each                   = toset(local.services)
  project                    = var.project_id
  service                    = each.key
  disable_dependent_services = false
  disable_on_destroy         = false # Permet de ne pas casser le projet si l'on détruit le bootstrap
}
