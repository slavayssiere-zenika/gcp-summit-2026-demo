resource "google_redis_instance" "cache" {
  name           = "redis-${terraform.workspace}"
  tier           = "BASIC"
  memory_size_gb = 1
  region         = var.region

  # Redis 7.2 requis pour Vector Search HNSW (SEC-F06 SemanticCache)
  # Ref: https://cloud.google.com/memorystore/docs/redis/vector-search
  redis_version = "REDIS_7_2"

  authorized_network = google_compute_network.main.id
  connect_mode       = "PRIVATE_SERVICE_ACCESS"

  depends_on = [
    google_service_networking_connection.private_vpc_connection
  ]
}
