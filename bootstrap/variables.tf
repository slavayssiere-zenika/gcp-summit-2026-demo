variable "project_id" {
  description = "L'ID du projet GCP sur lequel déployer les ressources."
  type        = string
  default     = "slavayssiere-sandbox-462015"
}

variable "region" {
  description = "La région GCP où stocker les ressources."
  type        = string
  default     = "europe-west1"
}

variable "artifact_registry_name" {
  description = "Nom du dépôt Artifact Registry."
  type        = string
  default     = "z-gcp-summit-services"
}

variable "bucket_frontend_name" {
  description = "Nom du bucket GCS pour stocker les archives frontend."
  type        = string
  default     = "z-gcp-summit-frontend"
}

variable "bucket_tfstate_name" {
  description = "Nom du bucket GCS pour le remote state Terraform."
  type        = string
  default     = "z-gcp-summit-tf-state"
}
