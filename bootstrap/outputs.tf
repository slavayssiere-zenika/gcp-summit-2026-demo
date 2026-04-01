output "bucket_frontend_url" {
  description = "URL du bucket GCS pour le frontend"
  value       = google_storage_bucket.frontend_archives.url
}

output "artifact_registry_repo_id" {
  description = "ID de l'Artifact Registry"
  value       = google_artifact_registry_repository.services.repository_id
}

output "artifact_registry_docker_url" {
  description = "URL au format Docker pour pusher les conteneurs"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.services.repository_id}"
}

output "secret_manager_jwt_id" {
  description = "ID secret manager du secret JWT"
  value       = google_secret_manager_secret.jwt_secret.id
}

output "secret_manager_gemini_id" {
  description = "ID secret manager du secret Gemini API Key"
  value       = google_secret_manager_secret.gemini_api_key.id
}
