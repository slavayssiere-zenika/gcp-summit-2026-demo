# Un suffixe aléatoire pour l'unicité globale des noms de bucket GCS
resource "random_id" "bucket_suffix" {
  byte_length = 4
}

# Bucket Frontend (Servi par le Load Balancer)
# Ce bucket est potentiellement public ou accessible via le backend du LB avec un IAP / backend signé (ou direct pour un frontend pure static).
resource "google_storage_bucket" "frontend" {
  name          = "frontend-${terraform.workspace}-${var.project_id}-${random_id.bucket_suffix.hex}"
  location      = var.region
  force_destroy = true

  website {
    main_page_suffix = "index.html"
    not_found_page   = "index.html"
  }

  uniform_bucket_level_access = true

  # Pour un frontend derrière un LB, on autorise allUsers à lire
  # Sinon le backend storage du LB ne passera pas l'authentification
}

# Donner un accès public au bucket frontend
resource "google_storage_bucket_iam_member" "frontend_public" {
  bucket = google_storage_bucket.frontend.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

# NOTE P2-5 : Les buckets loki et tempo (Loki/Tempo monitoring local) ont été
# supprimés car ils ne sont pas utilisés sur GCP. L'observabilité est assurée
# par Cloud Trace, Cloud Logging et Cloud Monitoring natifs.
# Commande de nettoyage si les buckets existent encore dans le state :
#   terraform state rm google_storage_bucket.loki
#   terraform state rm google_storage_bucket.tempo

# Bucket dédié aux I/O du pipeline Batch Taxonomie (Vertex AI Batch Prediction)
# Les fichiers JSONL d'entrée et de sortie sont stockés ici temporairement.
# Un lifecycle rule purge automatiquement les objets après 7 jours.
resource "google_storage_bucket" "cv_batch" {
  name          = "cv-batch-${terraform.workspace}-${var.project_id}-${random_id.bucket_suffix.hex}"
  location      = var.region
  force_destroy = true

  uniform_bucket_level_access = true

  lifecycle_rule {
    condition {
      age = 7 # jours — nettoyage automatique des JSONL temporaires
    }
    action {
      type = "Delete"
    }
  }
}

