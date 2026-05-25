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

# =========================================================
# Références réseau — injectées automatiquement dans les
# projets externes (extra_projects) via manage_env.py
# =========================================================
output "vpc_network_id" {
  description = "ID complet du VPC principal (injecté dans les modules Terraform des extra_projects)"
  value       = google_compute_network.main.id
}

output "vpc_subnet_id" {
  description = "ID complet du sous-réseau principal (injecté dans les modules Terraform des extra_projects)"
  value       = google_compute_subnetwork.main.id
}

output "alloydb_instance_uri" {
  description = "URI complet de l'instance AlloyDB primaire (injecté dans les modules Terraform des extra_projects)"
  value       = "projects/${var.project_id}/locations/${var.region}/clusters/${google_alloydb_cluster.main.cluster_id}/instances/${google_alloydb_instance.primary.instance_id}"
}

output "alloydb_ip" {
  description = "Adresse IP privée de l'instance AlloyDB primaire (injectée dans les extra_projects)"
  value       = google_alloydb_instance.primary.ip_address
}

output "tf_state_bucket" {
  description = "Nom du bucket GCS utilisé comme backend Terraform (injecté dans les extra_projects pour leur propre backend)"
  value       = "z-gcp-summit-tf-state"
}
