terraform {
  required_version = ">= 1.9.0, < 2.0.0" # Bumped from >= 1.5.0 — exclut les futures versions 2.x. Dernière CLI stable : 1.15.1.

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "6.50.0" # TODO: migration 6→7 planifiée (7.30.0 GA depuis août 2025).
      # ATTENTION: breaking changes sur google_cloud_run_v2_service, google_redis_instance, google_alloydb_cluster.
      # Procédure : 1) terraform init -upgrade  2) terraform plan  3) corriger les ressources  4) terraform apply
    }
  }

  backend "gcs" {
    bucket = "z-gcp-summit-tf-state"
    prefix = "terraform/state"
  }
}

provider "google" {
  add_terraform_attribution_label = false
  project                         = var.project_id
  region                          = var.region
}
