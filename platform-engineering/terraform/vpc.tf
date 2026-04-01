# VPC Network
resource "google_compute_network" "main" {
  name                    = "vpc-${terraform.workspace}"
  auto_create_subnetworks = false
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
