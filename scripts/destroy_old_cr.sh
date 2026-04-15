#!/bin/bash
# Script à usage unique pour cibler et détruire uniquement les ANCIENS Cloud Runs 
# (avant qu'ils ne soient recréés par le nouveau code découpé)

ENV=${1:-dev}

echo "Passage sur le workspace Terraform: $ENV"
cd platform-engineering/terraform
terraform workspace select $ENV || (echo "Le workspace $ENV n'existe pas." && exit 1)

echo "Destruction uniquement des anciens Super-Blocs Cloud Run..."
terraform destroy \
  -target=google_cloud_run_v2_service.mcp_services \
  -target=google_cloud_run_v2_service.prompts_api \
  -target=google_cloud_run_v2_service.drive_api \
  -target=google_cloud_run_v2_service.agent_api \
  -target=local.mcp_services \
  -auto-approve

echo "Destruction ciblée terminée ! Vous pouvez maintenant 'deploy' les nouveaux."
