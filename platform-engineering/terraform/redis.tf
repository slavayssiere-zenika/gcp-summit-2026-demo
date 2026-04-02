resource "google_redis_instance" "cache" {
  name           = "redis-${terraform.workspace}"
  tier           = "BASIC"
  memory_size_gb = 1
  region         = var.region

  authorized_network = google_compute_network.main.id
  connect_mode       = "PRIVATE_SERVICE_ACCESS"

  depends_on = [
    google_service_networking_connection.private_vpc_connection
  ]
}
