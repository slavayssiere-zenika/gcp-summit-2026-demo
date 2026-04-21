variable "project_id" {
  description = "L'ID du projet GCP sur lequel déployer les ressources."
  type        = string
}

variable "region" {
  description = "La région GCP où stocker les ressources."
  type        = string
  default     = "europe-west1"
}

variable "artifact_registry_name" {
  description = "Nom du dépôt Artifact Registry."
  type        = string
}

variable "bucket_frontend_name" {
  description = "Nom du bucket GCS pour stocker les archives frontend."
  type        = string
}

variable "bucket_tfstate_name" {
  description = "Nom du bucket GCS pour le remote state Terraform."
  type        = string
}

variable "source_artifact_project_id" {
  description = "L'ID du projet source (ex: sandbox) contenant l'Artifact Registry des images."
  type        = string
  default     = ""
}

variable "source_artifact_registry_name" {
  description = "Nom de l'Artifact Registry source."
  type        = string
  default     = ""
}
