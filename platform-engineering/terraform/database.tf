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
}

resource "google_alloydb_user" "iam_users" {
  for_each = toset(["users", "items", "competencies", "cv", "prompts"])
  cluster  = google_alloydb_cluster.main.name
  # AlloyDB exige que l'on retire le suffixe '.gserviceaccount.com' pour les Service Accounts IAM
  user_id    = replace(google_service_account.cr_sa[each.key].email, ".gserviceaccount.com", "")
  user_type  = "ALLOYDB_IAM_USER"
  depends_on = [google_alloydb_instance.primary]
}

