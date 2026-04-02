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
# Helper Functions
# ==============================================================================

update_cloudrun() {
  local SERVICE=$1
  
  local HTTP_CODE
  HTTP_CODE=$(curl -k -s -o /dev/null -w "%{http_code}" "https://dev.zenika.slavayssiere.fr" || echo "000")
  if [ "$HTTP_CODE" = "200" ]; then
    echo "--- Déploiement de $SERVICE sur Cloud Run (dev) ---"
    local CLEAN_NAME="${SERVICE//_/-}"
    local SVC_NAME="${CLEAN_NAME}-dev"
    local IMAGE_NAME="${DOCKER_REPO}/${SERVICE}:latest"
    
    local CMD_ARGS=(
      "gcloud" "run" "services" "update" "$SVC_NAME"
      "--region" "$REGION"
      "--project" "$PROJECT_ID"
      "--container" "api" "--image" "$IMAGE_NAME"
    )
    
    if [[ "$SERVICE" == "users_api" || "$SERVICE" == "items_api" || "$SERVICE" == "competencies_api" || "$SERVICE" == "cv_api" || "$SERVICE" == "drive_api" ]]; then
      CMD_ARGS+=( "--container" "mcp" "--image" "$IMAGE_NAME" )
    fi
    
    "${CMD_ARGS[@]}"
  else
    echo "--- dev.zenika.slavayssiere.fr n'est pas prêt (HTTP $HTTP_CODE), saut du déploiement Cloud Run pour $SERVICE ---"
  fi
}

build_and_push_standard() {
  local SERVICE=$1
  echo "--- Building $SERVICE ---"
  local IMAGE_NAME="${DOCKER_REPO}/${SERVICE}"
  
  # Build pour Cloud Run (nécessite amd64)
  docker build --platform linux/amd64 -t "${IMAGE_NAME}:${TAG}" -t "${IMAGE_NAME}:latest" "./${SERVICE}"
  
  # Push
  echo "--- Pushing $SERVICE ---"
  docker push "${IMAGE_NAME}:${TAG}"
  docker push "${IMAGE_NAME}:latest"
  
  if [ "$SERVICE" != "db_migrations" ]; then
    update_cloudrun "$SERVICE"
  else
    echo "--- Skipping update_cloudrun for $SERVICE (managed as a Cloud Run Job) ---"
  fi
}

build_and_push_agent() {
  # Cas particulier de l'Agent API (build context à la racine)
  echo "--- Building agent_api ---"
  local AGENT_IMAGE_NAME="${DOCKER_REPO}/agent_api"
  docker build --platform linux/amd64 -t "${AGENT_IMAGE_NAME}:${TAG}" -t "${AGENT_IMAGE_NAME}:latest" -f "agent_api/Dockerfile" .
  echo "--- Pushing agent_api ---"
  docker push "${AGENT_IMAGE_NAME}:${TAG}"
  docker push "${AGENT_IMAGE_NAME}:latest"
  
  update_cloudrun "agent_api"
}

build_and_upload_frontend() {
  echo "=== Traitement du Frontend ==="
  if [ ! -d "frontend" ]; then
    echo "Dossier frontend introuvable"
    exit 1
  fi
  cd frontend
  echo "--- NPM Install && Build ---"
  npm install
  npm run build
  cd ..

  echo "--- Création de l'archive tar.gz ---"
  local TIMESTAMP=$(date +%Y%m%d%H%M%S)
  local ARCHIVE_NAME="frontend-${TIMESTAMP}-${TAG}.tar.gz"

  tar -czvf "$ARCHIVE_NAME" frontend/dist/

  echo "--- Upload vers Google Cloud Storage ($FRONTEND_BUCKET) ---"
  gcloud storage cp "$ARCHIVE_NAME" "gs://${FRONTEND_BUCKET}/"
}

# ==============================================================================
# Main logic
# ==============================================================================
SERVICES=("users_api" "items_api" "competencies_api" "cv_api" "prompts_api" "drive_api" "db_migrations")
TARGET_SERVICE="${1:-all}"
# Normalize input (e.g. agent-api -> agent_api)
TARGET_SERVICE=${TARGET_SERVICE//-/_}

if [ "$TARGET_SERVICE" = "all" ]; then
  # 1. Build and Push des Microservices
  for SERVICE in "${SERVICES[@]}"; do
    build_and_push_standard "$SERVICE"
  done
  build_and_push_agent
  
  # 2. Build and Upload du Frontend
  build_and_upload_frontend
elif [[ " ${SERVICES[*]} " == *" $TARGET_SERVICE "* ]]; then
  build_and_push_standard "$TARGET_SERVICE"
elif [ "$TARGET_SERVICE" = "agent_api" ]; then
  build_and_push_agent
elif [ "$TARGET_SERVICE" = "frontend" ]; then
  build_and_upload_frontend
else
  echo "Erreur : Service '$1' inconnu."
  echo "Services valides : all, ${SERVICES[*]}, agent-api, frontend"
  exit 1
fi

echo "=== Déploiement terminé avec succès ! ==="
