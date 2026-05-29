# ==============================================================
# alert_policies_slo.tf — Burn Rate Alert Policies sur les SLOs
#
# Standard Google SRE : deux alertes par SLO.
#
# FAST BURN (14× sur 1h) :
#   Le budget d'erreur mensuel sera épuisé en ~2h si ça continue.
#   → Sévérité CRITICAL, notification immédiate SRE.
#
# SLOW BURN (2× sur 6h) :
#   Le budget d'erreur mensuel sera épuisé en ~3 jours si ça continue.
#   → Sévérité WARNING, triage planifié.
#
# Ces alertes remontent automatiquement dans list_alerts()
# et sont donc visibles par l'agent SRE en Phase 0c sans
# aucune modification du code Python.
#
# Couverture : 13 services × 2 SLOs × 2 fenêtres = 52 alert policies
# ==============================================================

# ─────────────────────────────────────────────────────────────
# Locals — map de tous les SLOs à couvrir
# ─────────────────────────────────────────────────────────────
locals {
  slo_burn_rate_targets = {

    # ── Agents IA ──────────────────────────────────────────────
    "agent-router-availability" = {
      svc_resource = google_monitoring_custom_service.agent_router_api_svc
      slo_resource = google_monitoring_slo.agent_router_api_availability
      label        = "Agent Router API — Disponibilité"
      severity     = "CRITICAL"
    }
    "agent-router-latency" = {
      svc_resource = google_monitoring_custom_service.agent_router_api_svc
      slo_resource = google_monitoring_slo.agent_router_api_latency
      label        = "Agent Router API — Latence P95"
      severity     = "CRITICAL"
    }
    "agent-hr-availability" = {
      svc_resource = google_monitoring_custom_service.agent_hr_api_svc
      slo_resource = google_monitoring_slo.agent_hr_api_availability
      label        = "Agent HR API — Disponibilité"
      severity     = "CRITICAL"
    }
    "agent-hr-latency" = {
      svc_resource = google_monitoring_custom_service.agent_hr_api_svc
      slo_resource = google_monitoring_slo.agent_hr_api_latency
      label        = "Agent HR API — Latence P95"
      severity     = "CRITICAL"
    }
    "agent-ops-availability" = {
      svc_resource = google_monitoring_custom_service.agent_ops_api_svc
      slo_resource = google_monitoring_slo.agent_ops_api_availability
      label        = "Agent Ops API — Disponibilité"
      severity     = "CRITICAL"
    }
    "agent-ops-latency" = {
      svc_resource = google_monitoring_custom_service.agent_ops_api_svc
      slo_resource = google_monitoring_slo.agent_ops_api_latency
      label        = "Agent Ops API — Latence P95"
      severity     = "WARNING"
    }
    "agent-missions-availability" = {
      svc_resource = google_monitoring_custom_service.agent_missions_api_svc
      slo_resource = google_monitoring_slo.agent_missions_api_availability
      label        = "Agent Missions API — Disponibilité"
      severity     = "CRITICAL"
    }
    "agent-missions-latency" = {
      svc_resource = google_monitoring_custom_service.agent_missions_api_svc
      slo_resource = google_monitoring_slo.agent_missions_api_latency
      label        = "Agent Missions API — Latence P95"
      severity     = "WARNING"
    }

    # ── APIs Data ──────────────────────────────────────────────
    "users-availability" = {
      svc_resource = google_monitoring_custom_service.users_api_svc
      slo_resource = google_monitoring_slo.users_api_availability
      label        = "Users API — Disponibilité"
      severity     = "CRITICAL"
    }
    "users-latency" = {
      svc_resource = google_monitoring_custom_service.users_api_svc
      slo_resource = google_monitoring_slo.users_api_latency
      label        = "Users API — Latence P95"
      severity     = "CRITICAL"
    }
    "items-availability" = {
      svc_resource = google_monitoring_custom_service.items_api_svc
      slo_resource = google_monitoring_slo.items_api_availability
      label        = "Items API — Disponibilité"
      severity     = "WARNING"
    }
    "items-latency" = {
      svc_resource = google_monitoring_custom_service.items_api_svc
      slo_resource = google_monitoring_slo.items_api_latency
      label        = "Items API — Latence P95"
      severity     = "WARNING"
    }
    "competencies-availability" = {
      svc_resource = google_monitoring_custom_service.competencies_api_svc
      slo_resource = google_monitoring_slo.competencies_api_availability
      label        = "Competencies API — Disponibilité"
      severity     = "CRITICAL"
    }
    "competencies-latency" = {
      svc_resource = google_monitoring_custom_service.competencies_api_svc
      slo_resource = google_monitoring_slo.competencies_api_latency
      label        = "Competencies API — Latence P95"
      severity     = "WARNING"
    }
    "cv-availability" = {
      svc_resource = google_monitoring_custom_service.cv_api_svc
      slo_resource = google_monitoring_slo.cv_api_availability
      label        = "CV API — Disponibilité"
      severity     = "CRITICAL"
    }
    "cv-latency" = {
      svc_resource = google_monitoring_custom_service.cv_api_svc
      slo_resource = google_monitoring_slo.cv_api_latency
      label        = "CV API — Latence P95"
      severity     = "WARNING"
    }
    "missions-availability" = {
      svc_resource = google_monitoring_custom_service.missions_api_svc
      slo_resource = google_monitoring_slo.missions_api_availability
      label        = "Missions API — Disponibilité"
      severity     = "CRITICAL"
    }
    "missions-latency" = {
      svc_resource = google_monitoring_custom_service.missions_api_svc
      slo_resource = google_monitoring_slo.missions_api_latency
      label        = "Missions API — Latence P95"
      severity     = "WARNING"
    }
    "drive-availability" = {
      svc_resource = google_monitoring_custom_service.drive_api_svc
      slo_resource = google_monitoring_slo.drive_api_availability
      label        = "Drive API — Disponibilité"
      severity     = "WARNING"
    }
    "drive-latency" = {
      svc_resource = google_monitoring_custom_service.drive_api_svc
      slo_resource = google_monitoring_slo.drive_api_latency
      label        = "Drive API — Latence P95"
      severity     = "WARNING"
    }
    "prompts-availability" = {
      svc_resource = google_monitoring_custom_service.prompts_api_svc
      slo_resource = google_monitoring_slo.prompts_api_availability
      label        = "Prompts API — Disponibilité"
      severity     = "CRITICAL"
    }
    "prompts-latency" = {
      svc_resource = google_monitoring_custom_service.prompts_api_svc
      slo_resource = google_monitoring_slo.prompts_api_latency
      label        = "Prompts API — Latence P95"
      severity     = "WARNING"
    }

    # ── Infrastructure MCP ─────────────────────────────────────
    "analytics-availability" = {
      svc_resource = google_monitoring_custom_service.analytics_mcp_svc
      slo_resource = google_monitoring_slo.analytics_mcp_availability
      label        = "Analytics MCP — Disponibilité"
      severity     = "WARNING"
    }
    "analytics-latency" = {
      svc_resource = google_monitoring_custom_service.analytics_mcp_svc
      slo_resource = google_monitoring_slo.analytics_mcp_latency
      label        = "Analytics MCP — Latence P95"
      severity     = "WARNING"
    }
    "monitoring-availability" = {
      svc_resource = google_monitoring_custom_service.monitoring_mcp_svc
      slo_resource = google_monitoring_slo.monitoring_mcp_availability
      label        = "Monitoring MCP — Disponibilité"
      severity     = "CRITICAL" # si le monitoring tombe, l'agent SRE est aveugle
    }
    "monitoring-latency" = {
      svc_resource = google_monitoring_custom_service.monitoring_mcp_svc
      slo_resource = google_monitoring_slo.monitoring_mcp_latency
      label        = "Monitoring MCP — Latence P95"
      severity     = "WARNING"
    }
  }
}

# ─────────────────────────────────────────────────────────────
# FAST BURN — 14× sur 1h
# Budget épuisé en ~2h → notification immédiate, on-call
#
# Logique : si le taux d'erreur est 14× supérieur à l'objectif
# SLO sur la dernière heure, le budget d'erreur mensuel (30j)
# sera consommé en moins de 2 heures.
# ─────────────────────────────────────────────────────────────
resource "google_monitoring_alert_policy" "slo_fast_burn" {
  for_each = local.slo_burn_rate_targets

  display_name = "[SLO-FAST-BURN] ${each.value.label} — ${terraform.workspace}"
  combiner     = "OR"
  enabled      = true
  project      = var.project_id

  severity = each.value.severity

  conditions {
    display_name = "Burn rate > 14× sur 1h — ${each.value.label}"
    condition_threshold {
      # select_slo_burn_rate() calcule le taux de consommation du budget d'erreur
      # relativement à l'objectif du SLO sur la fenêtre spécifiée.
      filter = join("", [
        "select_slo_burn_rate(\"projects/${var.project_id}/services/",
        "${each.value.svc_resource.service_id}/serviceLevelObjectives/",
        "${each.value.slo_resource.slo_id}\", \"3600s\")"
      ])
      comparison      = "COMPARISON_GT"
      threshold_value = 14.4
      duration        = "0s"

      aggregations {
        alignment_period   = "3600s"
        per_series_aligner = "ALIGN_MEAN"
      }
    }
  }

  notification_channels = concat(
    [for ch in google_monitoring_notification_channel.sre_email : ch.name],
    [google_monitoring_notification_channel.sre_chat.name]
  )

  documentation {
    content = join("\n", [
      "## 🔴 SLO Fast Burn — ${each.value.label}",
      "",
      "**Burn rate** : >14× sur la dernière heure.",
      "**Impact** : le budget d'erreur mensuel sera épuisé en **~2 heures** si rien n'est fait.",
      "",
      "### Actions immédiates",
      "1. Consulter les logs Cloud Run du service concerné",
      "2. Vérifier le dashboard Grafana SRE Data Quality",
      "3. Déclencher manuellement `/tasks/sre-triage` avec `hours=1` pour un diagnostic immédiat",
      "",
      "SLO : `projects/${var.project_id}/services/${each.value.svc_resource.service_id}`"
    ])
    mime_type = "text/markdown"
  }

  alert_strategy {
    # Auto-fermeture si le burn rate repasse sous le seuil pendant 30min
    auto_close = "1800s"
  }
}

# ─────────────────────────────────────────────────────────────
# SLOW BURN — 2× sur 6h
# Budget épuisé en ~3 jours → warning, triage planifié
#
# Logique : si le taux d'erreur est 2× supérieur à l'objectif
# SLO sur les 6 dernières heures, le budget d'erreur mensuel
# sera consommé en ~3 jours sans intervention.
# ─────────────────────────────────────────────────────────────
resource "google_monitoring_alert_policy" "slo_slow_burn" {
  for_each = local.slo_burn_rate_targets

  display_name = "[SLO-SLOW-BURN] ${each.value.label} — ${terraform.workspace}"
  combiner     = "OR"
  enabled      = true
  project      = var.project_id

  severity = "WARNING"

  conditions {
    display_name = "Burn rate > 2× sur 6h — ${each.value.label}"
    condition_threshold {
      filter = join("", [
        "select_slo_burn_rate(\"projects/${var.project_id}/services/",
        "${each.value.svc_resource.service_id}/serviceLevelObjectives/",
        "${each.value.slo_resource.slo_id}\", \"21600s\")"
      ])
      comparison      = "COMPARISON_GT"
      threshold_value = 2.0
      duration        = "0s"

      aggregations {
        alignment_period   = "21600s"
        per_series_aligner = "ALIGN_MEAN"
      }
    }
  }

  notification_channels = concat(
    [for ch in google_monitoring_notification_channel.sre_email : ch.name],
    [google_monitoring_notification_channel.sre_chat.name]
  )

  documentation {
    content = join("\n", [
      "## ⚠️ SLO Slow Burn — ${each.value.label}",
      "",
      "**Burn rate** : >2× sur les 6 dernières heures.",
      "**Impact** : le budget d'erreur mensuel sera épuisé en **~3 jours** si rien n'est fait.",
      "",
      "### Actions recommandées",
      "1. Analyser la tendance dans le dashboard Grafana SRE Data Quality",
      "2. Créer un ticket de remédiation si la tendance persiste",
      "3. Le prochain triage SRE automatique (2h) inclura ce service en priorité",
      "",
      "SLO : `projects/${var.project_id}/services/${each.value.svc_resource.service_id}`"
    ])
    mime_type = "text/markdown"
  }

  alert_strategy {
    auto_close = "86400s"
  }
}
