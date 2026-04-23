terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }

  # Décommentez et configurez le backend GCS si vous souhaitez persister l'état sur GCP.
  # backend "gcs" {
  #   bucket  = "STATE_BUCKET_NAME"
  #   prefix  = "terraform/state"
  # }
}

provider "google" {
  add_terraform_attribution_label = false
  project                         = var.project_id
  region                          = var.region
}
