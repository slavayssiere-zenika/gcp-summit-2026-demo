resource "random_password" "alloydb_password" {
  length  = 16
  special = true
}

resource "google_alloydb_cluster" "main" {
  cluster_id = "alloydb-${terraform.workspace}"
  location   = var.region

  network_config {
    network = google_compute_network.main.id
  }

  initial_user {
    user     = "postgres"
    password = random_password.alloydb_password.result
  }

  depends_on = [
    google_service_networking_connection.private_vpc_connection
  ]
}

resource "google_alloydb_instance" "primary" {
  cluster       = google_alloydb_cluster.main.name
  instance_id   = "primary-${terraform.workspace}"
  instance_type = "PRIMARY"

  machine_config {
    cpu_count = var.alloydb_cpu
  }

  database_flags = {
    "alloydb.iam_authentication" = "on"
  }
}

