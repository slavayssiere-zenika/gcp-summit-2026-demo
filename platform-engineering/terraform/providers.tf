terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "6.50.0" # Pinned — dernière 6.x stable (2026-04-xx). Ne pas upgrader vers 7.x sans migration.
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
