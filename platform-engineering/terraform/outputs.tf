output "frontend_bucket_name" {
  description = "Nom du bucket GCS généré dynamiquement pour le frontend"
  value       = google_storage_bucket.frontend.name
}

output "lb_ip" {
  description = "Adresse IP publique du Load Balancer (IPv4)"
  value       = google_compute_global_address.lb_ip.address
}

output "admin_password" {
  description = "Mot de passe généré dynamiquement pour seeder l'App avec l'Admin"
  value       = random_password.admin_password.result
  sensitive   = true
}


