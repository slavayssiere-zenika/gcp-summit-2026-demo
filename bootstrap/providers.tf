terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.15.0"
    }
  }

  # Décommentez et configurez le backend GCS si vous souhaitez persister l'état sur GCP.
  # backend "gcs" {
  #   bucket  = "STATE_BUCKET_NAME"
  #   prefix  = "terraform/state"
  # }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
