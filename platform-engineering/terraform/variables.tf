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

variable "admin_user" {
  description = "Utilisateur administrateur principal"
  type        = string
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

variable "image_users" {
  description = "Image for Users API container"
  type        = string
}

variable "image_items" {
  description = "Image for Items API container"
  type        = string
}

variable "image_competencies" {
  description = "Image for Competencies API container"
  type        = string
}

variable "image_cv" {
  description = "Image for CV API container"
  type        = string
}

variable "image_missions" {
  description = "Image for Missions API container"
  type        = string
}

variable "image_drive" {
  description = "Image for Drive API container"
  type        = string
}

variable "image_prompts" {
  description = "Image for Prompts API container"
  type        = string
}

variable "image_agent_router" {
  description = "Image for Agent Router API container"
  type        = string
}

variable "image_agent_hr" {
  description = "Image for Agent HR API container"
  type        = string
}

variable "image_agent_ops" {
  description = "Image for Agent Ops API container"
  type        = string
}

variable "image_agent_missions" {
  description = "Image for Agent Missions API container"
  type        = string
}

variable "image_market" {
  description = "Image for Market & FinOps MCP container"
  type        = string
}

variable "image_monitoring" {
  description = "Image for Monitoring MCP container"
  type        = string
}

variable "image_db_migrations" {
  description = "Image for DB Migrations container"
  type        = string
}

variable "gemini_api_key" {
  description = "Google Gemini API Key envoyée via manage_env"
  type        = string
  sensitive   = true
  default     = ""
}

variable "gemini_model" {
  description = "Modèle Gemini par défaut à utiliser"
  type        = string
  default     = "gemini-3.1-flash-lite-preview"
}

# Les objectifs SLO (disponibilité, latence) sont définis
# directement dans chaque fichier cr_<service>.tf pour permettre
# une configuration granulaire par service.

# Versions par composant (automatiquement alimentés par manage_env.py)
variable "agent_router_api_version" { type = string }
variable "agent_hr_api_version" { type = string }
variable "agent_ops_api_version" { type = string }
variable "agent_missions_api_version" { type = string }
variable "users_api_version" { type = string }
variable "items_api_version" { type = string }
variable "competencies_api_version" { type = string }
variable "cv_api_version" { type = string }
variable "missions_api_version" { type = string }
variable "prompts_api_version" { type = string }
variable "drive_api_version" { type = string }
variable "market_mcp_version" { type = string }
variable "monitoring_mcp_version" { type = string }
variable "db_migrations_version" { type = string }
variable "frontend_version" { type = string }

variable "finops_anomaly_threshold" {
  description = "Seuil critique de tokens déclenchant le kill-switch utilisateur"
  type        = number
  default     = 500000
}

# SEC-F06 — Semantic Cache LLM
variable "gemini_embedding_model" {
  description = "Modèle Gemini Embedding pour le cache sémantique (agent_router_api)"
  type        = string
  default     = "gemini-embedding-001"
}
