#!/usr/bin/env bash
# ==============================================================================
# Script de récupération (import) des utilisateurs AlloyDB existants en Production
# ==============================================================================
set -eo pipefail

echo "=== Sélection du workspace prd ==="
terraform workspace select prd || terraform workspace new prd

echo "=== Importation des utilisateurs dans le state Terraform ==="

# 1. Competencies DB User
echo "Importing competencies_db_user..."
terraform import google_alloydb_user.competencies_db_user \
  projects/prod-ia-staffing/locations/europe-west1/clusters/alloydb-prd/users/sa-competencies-prd-5cc8@prod-ia-staffing.iam || true

# 2. CV DB User
echo "Importing cv_db_user..."
terraform import google_alloydb_user.cv_db_user \
  projects/prod-ia-staffing/locations/europe-west1/clusters/alloydb-prd/users/sa-cv-prd-5cc8@prod-ia-staffing.iam || true

# 3. Drive DB User
echo "Importing drive_db_user..."
terraform import google_alloydb_user.drive_db_user \
  projects/prod-ia-staffing/locations/europe-west1/clusters/alloydb-prd/users/sa-drive-prd-v2@prod-ia-staffing.iam || true

# 4. Items DB User
echo "Importing items_db_user..."
terraform import google_alloydb_user.items_db_user \
  projects/prod-ia-staffing/locations/europe-west1/clusters/alloydb-prd/users/sa-items-prd-5cc8@prod-ia-staffing.iam || true

# 5. Missions DB User
echo "Importing missions_db_user..."
terraform import google_alloydb_user.missions_db_user \
  projects/prod-ia-staffing/locations/europe-west1/clusters/alloydb-prd/users/sa-missions-prd-5cc8@prod-ia-staffing.iam || true

# 6. Prompts DB User
echo "Importing prompts_db_user..."
terraform import google_alloydb_user.prompts_db_user \
  projects/prod-ia-staffing/locations/europe-west1/clusters/alloydb-prd/users/sa-prompts-prd-5cc8@prod-ia-staffing.iam || true

# 7. Users DB User
echo "Importing users_db_user..."
terraform import google_alloydb_user.users_db_user \
  projects/prod-ia-staffing/locations/europe-west1/clusters/alloydb-prd/users/sa-users-prd-5cc8@prod-ia-staffing.iam || true

# 8. Admin User
echo "Importing admin_user..."
terraform import google_alloydb_user.admin_user \
  projects/prod-ia-staffing/locations/europe-west1/clusters/alloydb-prd/users/sebastien.lavayssiere@zenika.com || true

echo "=== Import terminé avec succès ! ==="
