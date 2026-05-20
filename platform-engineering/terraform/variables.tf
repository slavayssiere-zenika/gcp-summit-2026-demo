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
  description = "Nom de la zone parente Google Cloud DNS pour injecter les records NS (obligatoire, défini dans envs/*.yaml)"
  type        = string
  # Pas de valeur par défaut : une erreur dès le plan si le YAML ne fournit pas cette variable.
  # Prévient toute modification accidentelle de la zone parente réelle.
}

variable "parent_zone_project_id" {
  description = "Project ID contenant la zone parente (obligatoire, défini dans envs/*.yaml)"
  type        = string
  # Pas de valeur par défaut : aligné sur parent_zone_name pour cohérence.
}

variable "admin_user" {
  description = "Utilisateur administrateur principal"
  type        = string
}

variable "cloudrun_min_instances" {
  description = "Nombre minimum d'instances Cloud Run (global)"
  type        = number
}

variable "cloudrun_max_instances" {
  description = "Nombre maximum d'instances Cloud Run"
  type        = number
}

variable "cloudrun_concurrency" {
  description = "Nombre maximum de requêtes concurrentes par instance Cloud Run"
  type        = number
}

# =========================================================
# Scaling per-service pour le pipeline Bulk Reanalyse CVs
# Ces APIs reçoivent jusqu'à 15 requêtes simultanées depuis
# cv_api pendant la phase APPLY (BULK_APPLY_SEMAPHORE=5).
# En prod : min_instances=0 globalement (optimisation coûts),
# mais ces services doivent être warm pour éviter les cold starts
# (AlloyDB IAM auth ~15s) qui déclenchent des retries en cascade.
# Valeur recommandée en prd : 1 (coût fixe : ~2 instances actives).
# =========================================================
variable "competencies_api_min_instances" {
  description = "Min instances pour competencies_api. Override cloudrun_min_instances pendant le bulk reanalyse."
  type        = number
  default     = 1
}

# =========================================================
# Throttling Pipeline CV Ingestion
# cv_api est le service le plus mémoire-intensif (LLM Gemini
# + connexions AlloyDB). Son max_instances DOIT être plafonné
# indépendamment du global cloudrun_max_instances pour éviter
# la saturation du pool SQL (QueuePool TimeoutError).
# Règle : cv_api_max_instances × pool_size ≤ alloydb_max_connections
# Avec alloydb_cpu=2 → ~400 connexions max → 8 instances × 50 = 400.
# =========================================================
variable "cv_api_max_instances" {
  description = "Nombre maximum d'instances EXCLUSIF pour cv_api (pipeline LLM). Indépendant de cloudrun_max_instances. Limiter à alloydb_max_connections/pool_size."
  type        = number
  default     = 10
}

variable "max_drive_cv_import" {
  description = "Nombre max de CVs publié dans Pub/Sub par cycle d'ingestion drive_api. Robinet principal du pipeline : réduire si AlloyDB sature."
  type        = number
  default     = 5
}

variable "items_api_min_instances" {
  description = "Min instances pour items_api. Override cloudrun_min_instances pendant le bulk reanalyse."
  type        = number
  default     = 1
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

variable "image_analytics" {
  description = "Image for Analytics & FinOps MCP container"
  type        = string
}

variable "image_monitoring" {
  description = "Image for Monitoring MCP container"
  type        = string
}

variable "image_db_migrations" {
  description = "Image for DB Migrations container (Liquibase)"
  type        = string
}

variable "image_db_init" {
  description = "Image for DB Init Job container (asyncpg IAM grants)"
  type        = string
}


# =========================================================
# Modèles Gemini — Configuration per-agent (AGENTS.md §1.4)
# Chaque agent peut utiliser un modèle distinct pour optimiser
# le coût FinOps et la qualité de raisonnement.
# =========================================================

variable "gemini_model" {
  description = "[LEGACY] Modèle Gemini par défaut — utilisé uniquement comme fallback si la variable per-agent est absente."
  type        = string
  default     = "gemini-3.1-flash-lite-preview"
}

variable "gemini_router_model" {
  description = "Modèle Gemini pour agent_router_api — orchestration complexe, raisonnement ambigu. Recommandé : gemini-3.1-pro-preview."
  type        = string
  default     = "gemini-3.1-pro-preview"
}

variable "gemini_hr_model" {
  description = "Modèle Gemini pour agent_hr_api — RAG multi-outils, coaching CV. Recommandé : gemini-3.1-flash-lite-preview."
  type        = string
  default     = "gemini-3.1-flash-lite-preview"
}

variable "gemini_ops_model" {
  description = "Modèle Gemini pour agent_ops_api — SQL BigQuery, logs Cloud. Recommandé : gemini-3.1-flash-lite-preview."
  type        = string
  default     = "gemini-3.1-flash-lite-preview"
}

variable "gemini_missions_model" {
  description = "Modèle Gemini pour agent_missions_api — matching staffing. Recommandé : gemini-3.1-flash-lite-preview."
  type        = string
  default     = "gemini-3.1-flash-lite-preview"
}

variable "gemini_cv_model" {
  description = "Modèle Gemini pour cv_api — extraction JSON contrainte (CV parsing + taxonomy). Recommandé : gemini-3.1-flash-lite-preview."
  type        = string
  default     = "gemini-3.1-flash-lite-preview"
}

variable "gemini_pro_model" {
  description = "Modele Gemini Pro pour Taxonomy Reduce (Vertex AI Batch) — etape critique de restructuration taxonomique. Ne pas changer sans tests qualitatifs."
  type        = string
  default     = "gemini-2.5-pro"
}

variable "gemini_batch_model" {
  description = "Modele Gemini pour Taxonomy Map+Sweep (Vertex AI Batch) — etapes simples (extraction/assignment). Recommande : gemini-2.5-flash (14x moins cher que Pro, meme context window)."
  type        = string
  default     = "gemini-2.5-flash"
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
variable "analytics_mcp_version" { type = string }
variable "monitoring_mcp_version" { type = string }
variable "db_migrations_version" { type = string }
variable "db_init_version" { type = string }
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

# =========================================================
# Parallélisme du pipeline Bulk Reanalyse CVs
# Contrôle la vitesse de la phase APPLY (post-Vertex AI Batch).
# À ajuster selon le pool AlloyDB et les quotas Gemini Embedding.
# =========================================================
variable "bulk_apply_semaphore" {
  description = "Nombre de CVs appliqués simultanément (phase APPLY du pipeline bulk-reanalyse). Défaut 5 pour AlloyDB pool_size=20."
  type        = number
  default     = 5
}

variable "bulk_embed_semaphore" {
  description = "Nombre d'appels Gemini Embedding API simultanés lors du pré-calcul batch. Défaut 10 (conservative vs 600 QPM Vertex AI)."
  type        = number
  default     = 10
}

variable "bulk_scale_min_instances" {
  description = "Min instances injectées sur competencies-api et items-api pendant la phase APPLY du bulk-reanalyse. Défaut 1 (suffit pour BULK_APPLY_SEMAPHORE≤10). Monter à 2 si SEMAPHORE>10."
  type        = number
  default     = 1
}

# =========================================================
# Domaines DNS additionnels (ex: gen-skillz.znk.io en prd)
# =========================================================
variable "extra_domains" {
  description = <<-EOT
    Liste de domaines DNS additionnels à lier à cet environnement.
    Chaque objet contient :
      - zone_name       : nom de la zone GCP Cloud DNS existante (ex: "gen-skillz")
      - dns_name        : nom DNS complet terminé par un point (ex: "gen-skillz.znk.io.")
      - parent_zone_project_id : projet GCP contenant cette zone existante
    Si vide (défaut), aucun domaine additionnel n'est géré.
  EOT
  type = list(object({
    zone_name              = string
    dns_name               = string
    parent_zone_project_id = string
  }))
  default = []
}

variable "trace_sampling_rate" {
  description = "Sampling rate for OpenTelemetry traces (0.0 to 1.0)"
  type        = string
  default     = "1.0"
}

variable "bq_location" {
  description = "Localisation par défaut pour les datasets BigQuery (ex: europe-west1)"
  type        = string
  default     = "europe-west1"
}

variable "enable_output_schema" {
  description = "Active output_schema Pydantic (StaffingResponse/MissionAnalysis) comme source de vérité pour display_type dans agent_hr_api, agent_ops_api et agent_missions_api. false = render_ui_widgets reste seul mécanisme actif (défaut stable)."
  type        = string
  default     = "false"
}
