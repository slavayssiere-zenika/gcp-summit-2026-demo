# ==============================================================================
# Autorisation de lecture sur l'Artifact Registry (Cross-Project)
# ==============================================================================
# Lorsque l'environnement est déployé dans un projet différent de celui du
# registre d'images (comme en Production "prd", où project_id="prod-ia-staffing"
# et image_registry est hébergé dans "slavayssiere-sandbox-462015"), l'agent de
# service Cloud Run doit impérativement avoir le rôle de lecture sur le registre
# pour pouvoir télécharger les images Docker.
# ==============================================================================

resource "google_project_iam_member" "cloudrun_cross_project_registry_reader" {
  # On n'applique cette ressource que si le projet cible est différent du projet parent/registre
  # pour éviter les permissions redondantes dans les environnements mono-projet (dev/uat).
  count = var.project_id != var.parent_zone_project_id ? 1 : 0

  project = var.parent_zone_project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:service-${data.google_project.project.number}@serverless-robot-prod.iam.gserviceaccount.com"
}
