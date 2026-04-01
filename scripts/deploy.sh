#!/usr/bin/env bash
set -e

# Configuration
PROJECT_ID="slavayssiere-sandbox-462015"
REGION="europe-west1"
REGISTRY="z-gcp-summit-services"
FRONTEND_BUCKET="z-gcp-summit-frontend"

# Docker registry prefix
DOCKER_REPO="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REGISTRY}"

echo "=== Préparation de l'environnement GCP ==="
gcloud config set project "$PROJECT_ID"
gcloud auth configure-docker "$REGION-docker.pkg.dev" --quiet

# Génération d'un tag (hash git, ou latest par défaut)
TAG=$(git rev-parse --short HEAD 2>/dev/null || echo "latest")
echo "-> Les images seront taggées avec : $TAG (et 'latest')"

# ==============================================================================
# 1. Build and Push des Microservices
# ==============================================================================
SERVICES=("users_api" "items_api" "competencies_api" "cv_api" "prompts_api")

for SERVICE in "${SERVICES[@]}"; do
  echo "--- Building $SERVICE ---"
  IMAGE_NAME="${DOCKER_REPO}/${SERVICE}"
  
  # Build pour Cloud Run (nécessite amd64)
  docker build --platform linux/amd64 -t "${IMAGE_NAME}:${TAG}" -t "${IMAGE_NAME}:latest" "./${SERVICE}"
  
  # Push
  echo "--- Pushing $SERVICE ---"
  docker push "${IMAGE_NAME}:${TAG}"
  docker push "${IMAGE_NAME}:latest"
done

# Cas particulier de l'Agent API (build context à la racine)
echo "--- Building agent_api ---"
AGENT_IMAGE_NAME="${DOCKER_REPO}/agent_api"
docker build --platform linux/amd64 -t "${AGENT_IMAGE_NAME}:${TAG}" -t "${AGENT_IMAGE_NAME}:latest" -f "agent_api/Dockerfile" .
echo "--- Pushing agent_api ---"
docker push "${AGENT_IMAGE_NAME}:${TAG}"
docker push "${AGENT_IMAGE_NAME}:latest"

# ==============================================================================
# 2. Build and Upload du Frontend
# ==============================================================================
echo "=== Traitement du Frontend ==="
cd frontend || { echo "Dossier frontend introuvable"; exit 1; }

echo "--- NPM Install && Build ---"
npm install
npm run build

cd ..

echo "--- Création de l'archive tar.gz ---"
TIMESTAMP=$(date +%Y%m%d%H%M%S)
ARCHIVE_NAME="frontend-${TIMESTAMP}-${TAG}.tar.gz"

tar -czvf "$ARCHIVE_NAME" frontend/dist/

echo "--- Upload vers Google Cloud Storage ($FRONTEND_BUCKET) ---"
gcloud storage cp "$ARCHIVE_NAME" "gs://${FRONTEND_BUCKET}/"

echo "=== Déploiement terminé avec succès ! ==="
