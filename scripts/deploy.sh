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

# Génération de la version Sémantique depuis les tags Git
LATEST_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "v0.0.0")

# Extraction des parties major, minor, patch de vX.Y.Z
if [[ $LATEST_TAG =~ ^v([0-9]+)\.([0-9]+)\.([0-9]+)$ ]]; then
  MAJOR="${BASH_REMATCH[1]}"
  MINOR="${BASH_REMATCH[2]}"
  PATCH="${BASH_REMATCH[3]}"
else
  MAJOR=0
  MINOR=0
  PATCH=0
fi

# Increment du patch pour le nouveau déploiement
NEW_PATCH=$((PATCH + 1))
TAG="v${MAJOR}.${MINOR}.${NEW_PATCH}"

echo "-> Dernière version: $LATEST_TAG | Nouvelle version ciblée: $TAG"

# Création du tag Git localement (s'il n'existe pas déjà)
if ! git rev-parse "$TAG" >/dev/null 2>&1; then
  git tag "$TAG"
  echo "-> Tag Git local $TAG créé avec succès."
fi

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
      "--update-env-vars" "APP_VERSION=$TAG"
    )
    
    if [[ "$SERVICE" == "users_api" || "$SERVICE" == "items_api" || "$SERVICE" == "competencies_api" || "$SERVICE" == "cv_api" || "$SERVICE" == "drive_api" ]]; then
      CMD_ARGS+=( "--container" "mcp" "--image" "$IMAGE_NAME" )
    fi
    
    "${CMD_ARGS[@]}"
  else
    echo "--- dev.zenika.slavayssiere.fr n'est pas prêt (HTTP $HTTP_CODE), saut du déploiement Cloud Run pour $SERVICE ---"
  fi
}

run_db_init_job() {
  local JOB_NAME="db-init-job-dev"
  
  if gcloud run jobs describe "$JOB_NAME" --region "$REGION" --project "$PROJECT_ID" >/dev/null 2>&1; then
    echo "--- Lancement du Cloud Run Job: $JOB_NAME ---"
    gcloud run jobs execute "$JOB_NAME" \
      --region "$REGION" \
      --project "$PROJECT_ID" \
      --wait
  else
    echo "--- Cloud Run Job $JOB_NAME introuvable, impossible de l'exécuter ---"
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
    # Chaine automatiquement avec le init_job
    run_db_init_job

    local CLEAN_NAME="${SERVICE//_/-}"
    local JOB_NAME="${CLEAN_NAME}-job-dev"
    
    if gcloud run jobs describe "$JOB_NAME" --region "$REGION" --project "$PROJECT_ID" >/dev/null 2>&1; then
      echo "--- Mise à jour de l'image du Cloud Run Job: $JOB_NAME ---"
      gcloud run jobs update "$JOB_NAME" \
        --region "$REGION" \
        --project "$PROJECT_ID" \
        --image "${IMAGE_NAME}:latest"
      
      echo "--- Lancement du Cloud Run Job: $JOB_NAME ---"
      gcloud run jobs execute "$JOB_NAME" \
        --region "$REGION" \
        --project "$PROJECT_ID" \
        --wait
    else
      echo "--- Skipping update_cloudrun for $SERVICE (Cloud Run Job $JOB_NAME introuvable) ---"
    fi
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

  echo "--- Déploiement vers le bucket de l'environnement DEV et gestion du cache ---"
  local DEV_BUCKET
  DEV_BUCKET=$(cd platform-engineering/terraform && terraform workspace select dev >/dev/null 2>&1 && terraform output -raw frontend_bucket_name 2>/dev/null || echo "")

  if [ -n "$DEV_BUCKET" ]; then
    echo "-> Synchronisation des fichiers vers gs://${DEV_BUCKET}..."
    gcloud storage rsync frontend/dist/ "gs://${DEV_BUCKET}/" --recursive --delete-unmatched-destination-objects
    
    echo "-> Configuration des entêtes Cache-Control..."
    # Désactiver le cache pour index.html
    gcloud storage objects update "gs://${DEV_BUCKET}/index.html" --cache-control="no-store, no-cache, must-revalidate, max-age=0"
    # Mettre en cache les assets statiques (js, css, etc.) pour 1 an
    gcloud storage objects update "gs://${DEV_BUCKET}/assets/**" --cache-control="public, max-age=31536000, immutable" 2>/dev/null || true

    echo "-> Invalidation du cache CDN (Google Cloud CDN)..."
    gcloud compute url-maps invalidate-cdn-cache "lb-dev" --path "/*" --async --project "$PROJECT_ID" || echo "/!\ Attention: impossible d'invalider le cache CDN"
  else
    echo "-> /!\ Impossible de récupérer le nom du bucket dev depuis Terraform."
  fi
}

# ==============================================================================
# Main logic
# ==============================================================================
SERVICES=("db_migrations" "users_api" "items_api" "competencies_api" "cv_api" "prompts_api" "drive_api")
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
elif [ "$TARGET_SERVICE" = "db_init" ]; then
  run_db_init_job
elif [ "$TARGET_SERVICE" = "agent_api" ]; then
  build_and_push_agent
elif [ "$TARGET_SERVICE" = "frontend" ]; then
  build_and_upload_frontend
else
  echo "Erreur : Service '$1' inconnu."
  echo "Services valides : all, db_init, ${SERVICES[*]}, agent_api, frontend"
  exit 1
fi

echo "=== Déploiement terminé avec succès ! ==="
