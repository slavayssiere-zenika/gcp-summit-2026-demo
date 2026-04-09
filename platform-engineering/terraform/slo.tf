# ==============================================================
# Services Personnalisés pour le Suivi Monitoring / SLO
# ==============================================================
resource "google_monitoring_custom_service" "api_services" {
  for_each     = toset(["users", "items", "competencies", "cv", "prompts", "drive", "agent"])
  service_id   = "${each.key}-api-service-${terraform.workspace}"
  display_name = "${title(each.key)} API Service"

  telemetry {
    resource_name = "//run.googleapis.com/projects/${var.project_id}/locations/${var.region}/services/${each.key}-api-${terraform.workspace}"
  }
}

# ==============================================================
# SLO : Disponibilité
# ==============================================================
resource "google_monitoring_slo" "availability" {
  for_each     = google_monitoring_custom_service.api_services
  service      = each.value.service_id
  slo_id       = "${each.key}-availability-slo-${terraform.workspace}"
  display_name = "Availability ${var.slo_availability_goal * 100}% - ${title(each.key)} API"

  goal                = var.slo_availability_goal
  rolling_period_days = 30

  request_based_sli {
    good_total_ratio {
      good_service_filter = join(" ", [
        "metric.type=\"run.googleapis.com/request_count\"",
        "resource.type=\"cloud_run_revision\"",
        "resource.label.\"service_name\"=\"${each.key}-api-${terraform.workspace}\"",
        "metric.label.\"response_code_class\"!=\"5xx\""
      ])
      total_service_filter = join(" ", [
        "metric.type=\"run.googleapis.com/request_count\"",
        "resource.type=\"cloud_run_revision\"",
        "resource.label.\"service_name\"=\"${each.key}-api-${terraform.workspace}\""
      ])
    }
  }
}

# ==============================================================
# SLO : Latence
# ==============================================================
resource "google_monitoring_slo" "latency" {
  for_each     = google_monitoring_custom_service.api_services
  service      = each.value.service_id
  slo_id       = "${each.key}-latency-slo-${terraform.workspace}"
  display_name = "Latency p${var.slo_latency_goal * 100} < ${var.slo_latency_threshold_ms}ms - ${title(each.key)} API"

  goal                = var.slo_latency_goal
  rolling_period_days = 30

  request_based_sli {
    distribution_cut {
      distribution_filter = join(" ", [
        "metric.type=\"run.googleapis.com/request_latencies\"",
        "resource.type=\"cloud_run_revision\"",
        "resource.label.\"service_name\"=\"${each.key}-api-${terraform.workspace}\""
      ])
      range {
        max = var.slo_latency_threshold_ms / 1000.0
      }
    }
  }
}
