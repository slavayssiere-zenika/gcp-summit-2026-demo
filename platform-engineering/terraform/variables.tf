variable "project_id" {
  description = "Project ID GCP"
  type        = string
  default     = "slavayssiere-sandbox-462015"
}

variable "region" {
  description = "GCP Region"
  type        = string
  default     = "europe-west1"
}

variable "base_domain" {
  description = "Domaine parent. L'environnement sera env.base_domain"
  type        = string
  default     = "zenika.slavayssiere.fr"
}

variable "parent_zone_name" {
  description = "Nom de la zone parente Google Cloud DNS pour injecter les records NS"
  type        = string
  default     = "zenika-slavayssiere-fr"
}

variable "cloudrun_min_instances" {
  description = "Nombre minimum d'instances Cloud Run"
  type        = number
}

variable "cloudrun_max_instances" {
  description = "Nombre maximum d'instances Cloud Run"
  type        = number
}

variable "alloydb_cpu" {
  description = "Nombre de vCPUs pour la base de données AlloyDB"
  type        = number
}

variable "waf_rate_limit" {
  description = "Limite de requêtes par IP pour le pare-feu"
  type        = number
}
