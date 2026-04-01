# Zone DNS pour l'environnement (ex: dev.slavayssiere-zenika.com)
resource "google_dns_managed_zone" "env_zone" {
  name        = "zone-${terraform.workspace}"
  dns_name    = "${terraform.workspace}.${var.base_domain}."
  description = "Zone DNS pour l'environnement ${terraform.workspace}"

  # Ne pas détruire cette ressource lors de la suppression de l'environnement
  lifecycle {
    prevent_destroy = true
  }
}

# =========================================================
# Délégation NS automatique vers la zone parente
# =========================================================
data "google_dns_managed_zone" "parent_zone" {
  name = var.parent_zone_name
}

resource "google_dns_record_set" "ns_delegation" {
  name         = google_dns_managed_zone.env_zone.dns_name
  managed_zone = data.google_dns_managed_zone.parent_zone.name
  type         = "NS"
  ttl          = 300

  rrdatas = google_dns_managed_zone.env_zone.name_servers
}

# =========================================================
# DNS Privé (VPC Interne)
# =========================================================
resource "google_dns_managed_zone" "internal_zone" {
  name        = "internal-zone-${terraform.workspace}"
  dns_name    = "internal.zenika."
  description = "Zone DNS privée pour le routage interne VPC"
  visibility  = "private"

  private_visibility_config {
    networks {
      network_url = google_compute_network.main.id
    }
  }
}

resource "google_dns_record_set" "internal_api_a" {
  name         = "api.${google_dns_managed_zone.internal_zone.dns_name}"
  managed_zone = google_dns_managed_zone.internal_zone.name
  type         = "A"
  ttl          = 300

  rrdatas = [google_compute_forwarding_rule.internal_rule.ip_address]
}

import {
  to = google_dns_managed_zone.env_zone
  id = "projects/${var.project_id}/managedZones/zone-${terraform.workspace}"
}
