# =========================================================
# Zone DNS principale de l'environnement (persistante)
# ex: dev.zenika.slavayssiere.fr  /  prd.zenika.slavayssiere.fr
# =========================================================
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
# Délégation NS automatique vers la zone parente (sandbox)
# La zone racine "zenika.slavayssiere.fr" n'est jamais touchée.
# Seule la sous-zone de l'environnement est déléguée.
# =========================================================
data "google_dns_managed_zone" "parent_zone" {
  name    = var.parent_zone_name
  project = var.parent_zone_project_id
}

resource "google_dns_record_set" "ns_delegation" {
  name         = google_dns_managed_zone.env_zone.dns_name
  managed_zone = data.google_dns_managed_zone.parent_zone.name
  type         = "NS"
  ttl          = 300

  rrdatas = google_dns_managed_zone.env_zone.name_servers

  # La délégation est créée dans le projet de la zone parente (sandbox)
  project = var.parent_zone_project_id

  lifecycle {
    prevent_destroy = true
  }
}

# =========================================================
# Zones DNS additionnelles (optionnelles, ex: gen-skillz en prd)
# Déclarez-les dans extra_domains dans prd.yaml.
# Chaque zone est persistante (prevent_destroy = true).
# =========================================================
resource "google_dns_managed_zone" "extra_zones" {
  for_each = { for d in var.extra_domains : d.zone_name => d }

  name        = each.value.zone_name
  dns_name    = each.value.dns_name
  description = "Zone DNS additionnelle ${each.value.dns_name} — ${terraform.workspace}"

  lifecycle {
    prevent_destroy = true
  }
}

# Délégation NS vers la zone parente de chaque domaine additionnel
# (ex: le registrar znk.io doit pointer ses NS vers cette zone)
data "google_dns_managed_zone" "extra_parent_zones" {
  for_each = { for d in var.extra_domains : d.zone_name => d }

  name    = each.value.parent_zone_name
  project = each.value.parent_zone_project_id
}

resource "google_dns_record_set" "extra_ns_delegation" {
  for_each = { for d in var.extra_domains : d.zone_name => d }

  name         = google_dns_managed_zone.extra_zones[each.key].dns_name
  managed_zone = data.google_dns_managed_zone.extra_parent_zones[each.key].name
  type         = "NS"
  ttl          = 300

  rrdatas = google_dns_managed_zone.extra_zones[each.key].name_servers
  project = each.value.parent_zone_project_id

  lifecycle {
    prevent_destroy = true
  }
}

# Enregistrements A vers le LB pour chaque domaine additionnel
resource "google_dns_record_set" "extra_a" {
  for_each = { for d in var.extra_domains : d.zone_name => d }

  name         = google_dns_managed_zone.extra_zones[each.key].dns_name
  managed_zone = google_dns_managed_zone.extra_zones[each.key].name
  type         = "A"
  ttl          = 300

  rrdatas = [google_compute_global_address.lb_ip.address]

  lifecycle {
    prevent_destroy = true
  }
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

# Note: L'import de ces ressources est géré impérativement par manage_env.py
# via resource_exists_in_gcp() + import_persistent_resource() pour être conditionnel.
