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

resource "google_alloydb_user" "iam_users" {
  for_each   = google_service_account.cr_sa
  cluster    = google_alloydb_cluster.main.name
  user_id    = replace(each.value.email, ".gserviceaccount.com", "")
  user_type  = "ALLOYDB_IAM_USER"
  depends_on = [google_alloydb_instance.primary]

  lifecycle {
    ignore_changes = [database_roles]
  }
}

resource "google_alloydb_user" "admin_user" {
  cluster    = google_alloydb_cluster.main.name
  user_id    = var.admin_user
  user_type  = "ALLOYDB_IAM_USER"
  depends_on = [google_alloydb_instance.primary]

  lifecycle {
    ignore_changes = [database_roles]
  }
}

resource "google_project_iam_member" "admin_database_user" {
  project = var.project_id
  role    = "roles/alloydb.databaseUser"
  member  = "user:${var.admin_user}"
}
