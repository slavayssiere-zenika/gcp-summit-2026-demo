#!/usr/bin/env bash
set -eo pipefail

ENV="${1:-dev}"
ENV_FILE="platform-engineering/envs/${ENV}.yaml"

if [ ! -f "$ENV_FILE" ]; then
  echo "❌ Fichier d'environnement introuvable : $ENV_FILE"
  echo "Usage: $0 [dev|uat|prd]"
  exit 1
fi

# Extraction du project_id et de la region depuis le fichier YAML
PROJECT_ID=$(grep -E "^project_id:" "$ENV_FILE" | sed -E 's/project_id:[[:space:]]*"([^"]+)"/\1/')
REGION=$(grep -E "^region:" "$ENV_FILE" | sed -E 's/region:[[:space:]]*"([^"]+)"/\1/' || echo "")

if [ -z "$PROJECT_ID" ]; then
  echo "❌ Impossible de lire project_id dans $ENV_FILE"
  exit 1
fi

if [ -z "$REGION" ]; then
  REGION="europe-west1"
fi

JOB_NAME="db-init-job-${ENV}"

echo "🚀 Lancement manuel du job d'initialisation de base de données :"
echo "   • Environnement : $ENV"
echo "   • Job Name      : $JOB_NAME"
echo "   • Project ID    : $PROJECT_ID"
echo "   • Region        : $REGION"
echo ""

gcloud run jobs execute "$JOB_NAME" \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --wait
