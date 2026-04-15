# VPC Network
resource "google_compute_network" "main" {
  name                    = "vpc-${terraform.workspace}"
  auto_create_subnetworks = false
}

resource "google_project_service" "cloudtrace" {
  project            = var.project_id
  service            = "cloudtrace.googleapis.com"
  disable_on_destroy = false
}

# Subnetwork pour le Load Balancer serverless et usage interne
resource "google_compute_subnetwork" "main" {
  name          = "subnet-${terraform.workspace}"
  ip_cidr_range = "10.0.0.0/20"
  region        = var.region
  network       = google_compute_network.main.id
}

# Plage d'adresses IP privées pour AlloyDB (Private Services Access)
resource "google_compute_global_address" "private_ip_alloc" {
  name          = "alloydb-peering-${terraform.workspace}"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 20
  network       = google_compute_network.main.id
}

resource "google_service_networking_connection" "private_vpc_connection" {
  network                 = google_compute_network.main.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip_alloc.name]
}

# Sous-réseau spécifique pour Internal Load Balancing (obligatoire pour L7 interne)
resource "google_compute_subnetwork" "proxy_only" {
  name          = "proxy-only-${terraform.workspace}"
  ip_cidr_range = "10.129.0.0/23" # Plage distincte
  region        = var.region
  network       = google_compute_network.main.id
  purpose       = "REGIONAL_MANAGED_PROXY"
  role          = "ACTIVE"
}

# =========================================================
# FIREWALL RULES (ZERO-TRUST EGRESS FOR CLOUD RUN)
# =========================================================

# 1. Règle "Deny All" Egress pour toutes les instances tagguées "cr-egress".
resource "google_compute_firewall" "deny_all_egress" {
  name      = "fw-deny-egress-${terraform.workspace}"
  network   = google_compute_network.main.id
  direction = "EGRESS"
  priority  = 65534

  deny {
    protocol = "all"
  }

  destination_ranges = ["0.0.0.0/0"]
  target_tags        = ["cr-egress"]
}

# 2. Règle "Allow" Egress vers AlloyDB (Port 5432).
resource "google_compute_firewall" "allow_alloydb_egress" {
  name      = "fw-allow-alloydb-egress-${terraform.workspace}"
  network   = google_compute_network.main.id
  direction = "EGRESS"
  priority  = 1000

  allow {
    protocol = "tcp"
    ports    = ["5432", "5433"]
  }

  destination_ranges = ["${google_compute_global_address.private_ip_alloc.address}/${google_compute_global_address.private_ip_alloc.prefix_length}"]
  target_tags        = ["cr-egress"]
}

# 2.bis. Règle "Allow" Ingress depuis les APIs vers AlloyDB (Port 5432).
resource "google_compute_firewall" "allow_alloydb_ingress" {
  name      = "fw-allow-alloydb-ingress-${terraform.workspace}"
  network   = google_compute_network.main.id
  direction = "INGRESS"
  priority  = 1000

  allow {
    protocol = "tcp"
    ports    = ["5432", "5433"]
  }

  # Le traffic provient du subnet principal (où Cloud Run s'attache via Direct VPC Egress)
  source_ranges = [google_compute_subnetwork.main.ip_cidr_range]
}

# 3. Règle "Allow" Egress vers le Load Balancer Interne (Port 80) / Reste du VPC.
resource "google_compute_firewall" "allow_ilb_egress" {
  name      = "fw-allow-ilb-egress-${terraform.workspace}"
  network   = google_compute_network.main.id
  direction = "EGRESS"
  priority  = 1000

  allow {
    protocol = "tcp"
    ports    = ["80"]
  }

  destination_ranges = [google_compute_subnetwork.main.ip_cidr_range]
  target_tags        = ["cr-egress"]
}

# 4. Règle "Allow" Egress vers Redis (Port 6379).
resource "google_compute_firewall" "allow_redis_egress" {
  name      = "fw-allow-redis-egress-${terraform.workspace}"
  network   = google_compute_network.main.id
  direction = "EGRESS"
  priority  = 1000

  allow {
    protocol = "tcp"
    ports    = ["6379"]
  }

  destination_ranges = ["${google_compute_global_address.private_ip_alloc.address}/${google_compute_global_address.private_ip_alloc.prefix_length}"]
  target_tags        = ["cr-egress"]
}

# 5. Règle "Allow" Egress vers Google APIs (HTTPS Port 443).
# Utilise les plages Private Google Access (restricted + private) pour le Zero-Trust.
# Indispensable pour Cloud Trace, Logging, Gemini API, BigQuery, etc.
resource "google_compute_firewall" "allow_google_apis_egress" {
  name      = "fw-allow-google-apis-egress-${terraform.workspace}"
  network   = google_compute_network.main.id
  direction = "EGRESS"
  priority  = 1000

  allow {
    protocol = "tcp"
    ports    = ["443"]
  }

  # restricted.googleapis.com (199.36.153.4/30) + private.googleapis.com (199.36.153.8/30)
  destination_ranges = ["199.36.153.4/30", "199.36.153.8/30"]
  target_tags        = ["cr-egress"]
}
