#!/usr/bin/env bash
set -e

# Configuration
PROJECT_ID="slavayssiere-sandbox-462015"
REGION="europe-west1"
REGISTRY="z-gcp-summit-services"
FRONTEND_BUCKET="z-gcp-summit-frontend"

# Docker registry prefix
DOCKER_REPO="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REGISTRY}"

# Colors for Zenika Branding
RED='\033[0;31m'
GREY='\033[1;30m'
RESET='\033[0m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'

# Aide (vérifié avant tout autre traitement)
if [[ "$1" == "-h" || "$1" == "--help" ]]; then
  # show_help est défini plus bas, mais on peut le définir ici ou appeler un bloc dédié
  # Pour simplifier, on s'assure que show_help est accessible ou on déplace sa définition
  echo -e "${RED}Zenika Console - Déploiement GCP${RESET}"
  echo ""
  echo "Usage: $0 [SERVICE...] [BUMP_TYPE]"
  echo ""
  echo "Services:"
  echo -e "  all            Déploie tous les microservices applicatifs et le frontend"
  echo -e "  users_api      Microservice Utilisateurs"
  echo -e "  items_api      Microservice Items"
  echo -e "  cv_api         Microservice CVs"
  echo -e "  missions_api   Microservice Missions"
  echo -e "  agent_router_api   Orchestrateur A2A"
  echo -e "  agent_hr_api       Agent HR (A2A Worker)"
  echo -e "  agent_ops_api      Agent Ops (A2A Worker)"
  echo -e "  agent_missions_api Agent Missions/Staffing (A2A Worker)"
  echo -e "  frontend       Frontend Vue.js"
  echo -e "  db_migrations  Migrations de base de données (non inclus dans 'all')"
  echo -e "  db_init       Initialise la base de données via Cloud Run Job"
  echo -e "  sync_prompts  Synchronise uniquement les system prompts vers prompts_api"
  echo ""
  echo "Bump Types (SemVer):"
  echo "  patch (défaut), minor, major, none"
  echo "Note: sync_prompts est aussi exécuté automatiquement après tout déploiement."
  echo ""
  echo "Exemples:"

  echo "  $0 all minor"
  echo "  $0 users_api cv_api minor"
  echo "  $0 db_migrations"
  exit 0
fi

echo -e "${RED}=== Préparation de l'environnement GCP ===${RESET}"
gcloud config set project "$PROJECT_ID"
gcloud auth configure-docker "$REGION-docker.pkg.dev" --quiet

# ==============================================================================
# Versioning Helpers
# ==============================================================================

get_service_tag() {
  local SERVICE=$1
  local BUMP_TYPE=${2:-"none"}
  local VERSION_FILE="${SERVICE}/VERSION"
  
  if [ ! -f "$VERSION_FILE" ]; then
    echo "v0.0.1" > "$VERSION_FILE"
  fi
  
  local CURRENT_VERSION=$(cat "$VERSION_FILE")
  
  # if BUMP_TYPE is "none", just return current
  if [ "$BUMP_TYPE" == "none" ]; then
    echo "$CURRENT_VERSION"
    return
  fi

  # Extraction des parties major, minor, patch de vX.Y.Z
  if [[ $CURRENT_VERSION =~ ^v([0-9]+)\.([0-9]+)\.([0-9]+)$ ]]; then
    local MAJOR="${BASH_REMATCH[1]}"
    local MINOR="${BASH_REMATCH[2]}"
    local PATCH="${BASH_REMATCH[3]}"
  else
    local MAJOR=0
    local MINOR=0
    local PATCH=0
  fi

  case $BUMP_TYPE in
    major)
      MAJOR=$((MAJOR + 1))
      MINOR=0
      PATCH=0
      ;;
    minor)
      MINOR=$((MINOR + 1))
      PATCH=0
      ;;
    patch)
      PATCH=$((PATCH + 1))
      ;;
  esac

  local NEW_TAG="v${MAJOR}.${MINOR}.${PATCH}"
  echo "$NEW_TAG" > "$VERSION_FILE"
  
  # Création du tag Git spécifique au service
  local GIT_TAG="${SERVICE}-${NEW_TAG}"
  if ! git rev-parse "$GIT_TAG" >/dev/null 2>&1; then
    git tag "$GIT_TAG"
    echo "-> Tag Git $GIT_TAG créé." >&2
  fi
  
  echo "$NEW_TAG"
}

# ==============================================================================
# Helper Functions
# ==============================================================================

update_cloudrun() {
  local SERVICE=$1
  local TAG=$2
  
  echo "--- Déploiement de $SERVICE sur Cloud Run (dev) ---"
  local CLEAN_NAME="${SERVICE//_/-}"
  local SVC_NAME="${CLEAN_NAME}-dev"
  local IMAGE_URL="${DOCKER_REPO}/${SERVICE}:${TAG}"
  
  local CMD_ARGS=(
    "gcloud" "run" "services" "update" "$SVC_NAME"
    "--region" "$REGION"
    "--project" "$PROJECT_ID"
    "--container" "api" "--image" "$IMAGE_URL"
    "--update-env-vars" "APP_VERSION=$TAG"
  )
  
  if [[ "$SERVICE" == "users_api" || "$SERVICE" == "items_api" || "$SERVICE" == "competencies_api" || "$SERVICE" == "cv_api" || "$SERVICE" == "drive_api" || "$SERVICE" == "missions_api" ]]; then
    CMD_ARGS+=( "--container" "mcp" "--image" "$IMAGE_URL" )
  fi
  
  "${CMD_ARGS[@]}" || echo "/!\ Échec partiel du déploiement Cloud Run pour $SERVICE"
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
    echo -e "${RED}--- Cloud Run Job $JOB_NAME introuvable, impossible de l'exécuter ---${RESET}"
  fi
}

show_progress() {
  local CURRENT=$1
  local DONE_TASKS=()
  local TODO_TASKS=()
  local FOUND=false
  
  for task in "${ALL_TASKS[@]}"; do
    if [ "$task" == "$CURRENT" ]; then
      FOUND=true
      continue
    fi
    if [ "$FOUND" = false ]; then
      DONE_TASKS+=("$task")
    else
      TODO_TASKS+=("$task")
    fi
  done
  
  echo -e "\n${GREY}------------------------------------------------------------${RESET}"
  echo -e "${RED}🚀 BUILDING: ${CURRENT}${RESET}"
  
  if [ ${#DONE_TASKS[@]} -gt 0 ]; then
    echo -e "${GREEN}✅ COMPLETED: ${DONE_TASKS[*]}${RESET}"
  fi
  
  if [ ${#TODO_TASKS[@]} -gt 0 ]; then
    echo -e "${GREY}⏳ REMAINING: ${TODO_TASKS[*]}${RESET}"
  fi
  echo -e "${GREY}------------------------------------------------------------${RESET}\n"
}

build_and_push_standard() {
  local SERVICE=$1
  local BUMP=${2:-"patch"}
  
  local TAG=$(get_service_tag "$SERVICE" "$BUMP")
  echo "--- Building $SERVICE ($TAG) ---"
  local IMAGE_NAME="${DOCKER_REPO}/${SERVICE}"
  
  # Build pour Cloud Run (nécessite amd64)
  docker build --platform linux/amd64 -t "${IMAGE_NAME}:${TAG}" -t "${IMAGE_NAME}:latest" "./${SERVICE}"
  
  # Push
  echo "--- Pushing $SERVICE ---"
  docker push "${IMAGE_NAME}:${TAG}"
  docker push "${IMAGE_NAME}:latest"
  
  if [ "$SERVICE" != "db_migrations" ]; then
    update_cloudrun "$SERVICE" "$TAG"
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
        --image "${IMAGE_NAME}:${TAG}"
      
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
  local SERVICE=$1
  local BUMP=${2:-"patch"}
  local TAG=$(get_service_tag "$SERVICE" "$BUMP")
  
  # Build context doit être le dossier de l'agent
  echo "--- Building $SERVICE ($TAG) ---"
  local AGENT_IMAGE_NAME="${DOCKER_REPO}/${SERVICE}"
  docker build --platform linux/amd64 -t "${AGENT_IMAGE_NAME}:${TAG}" -t "${AGENT_IMAGE_NAME}:latest" "./${SERVICE}"
  echo "--- Pushing $SERVICE ---"
  docker push "${AGENT_IMAGE_NAME}:${TAG}"
  docker push "${AGENT_IMAGE_NAME}:latest"
  
  update_cloudrun "$SERVICE" "$TAG"
}

build_and_upload_frontend() {
  local BUMP=${1:-"patch"}
  local TAG=$(get_service_tag "frontend" "$BUMP")

  echo "=== Traitement du Frontend ($TAG) ==="
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

sync_system_prompts() {
  echo -e "\n${RED}=== Synchronisation des System Prompts (Grounding) ===${RESET}"
  
  # 1. Récupération des infos via Terraform
  echo "[*] Récupération du mot de passe admin et de la configuration..."
  local TF_DIR="platform-engineering/terraform"
  local ADMIN_PWD=$(cd "$TF_DIR" && terraform workspace select dev >/dev/null 2>&1 && terraform output -raw admin_password 2>/dev/null || echo "")
  
  if [ -z "$ADMIN_PWD" ]; then
    echo -e "${YELLOW}[!] Impossible de récupérer le mot de passe admin via Terraform. Skip sync.${RESET}"
    return
  fi
  
  # 2. Détermination de l'URL (via dev.yaml ou convention)
  local BASE_DOMAIN="zenika.slavayssiere.fr" # Valeur par défaut ou extraite du yaml
  if [ -f "platform-engineering/envs/dev.yaml" ]; then
    BASE_DOMAIN=$(grep "base_domain:" platform-engineering/envs/dev.yaml | cut -d'"' -f2)
  fi
  local API_URL="https://api.dev.${BASE_DOMAIN}/api/prompts"
  
  # 3. Exécution du script Python
  python3 scripts/sync_prompts.py --url "$API_URL" --password "$ADMIN_PWD"
}

# ==============================================================================
# Main logic
# ==============================================================================
# Liste des services applicatifs (déployés par 'all')
APP_MICROSERVICES=("users_api" "items_api" "competencies_api" "cv_api" "prompts_api" "drive_api" "missions_api" "market_mcp")
# Liste de tous les services possibles pour la validation
VALID_SERVICES=("db_migrations" "db_init" "sync_prompts" "agent_router_api" "agent_hr_api" "agent_ops_api" "agent_missions_api" "frontend" "${APP_MICROSERVICES[@]}")

BUMP_TYPE="patch"
TARGET_SERVICES=()

for arg in "$@"; do
  if [[ "$arg" == "patch" || "$arg" == "minor" || "$arg" == "major" || "$arg" == "none" ]]; then
    BUMP_TYPE="$arg"
  else
    # Normalize input (e.g. agent-api -> agent_api)
    TARGET_SERVICES+=("${arg//-/_}")
  fi
done

if [ ${#TARGET_SERVICES[@]} -eq 0 ]; then
  TARGET_SERVICES=("all")
fi

# Si "all" est dans la liste, on le place seul et on ignore le reste
for svc in "${TARGET_SERVICES[@]}"; do
  if [ "$svc" == "all" ]; then
    TARGET_SERVICES=("all")
    break
  fi
done

if [ "${TARGET_SERVICES[0]}" = "all" ]; then
  ALL_TASKS=("${APP_MICROSERVICES[@]}" "agent_router_api" "agent_hr_api" "agent_ops_api" "agent_missions_api" "frontend")
else
  ALL_TASKS=("${TARGET_SERVICES[@]}")
fi

for TARGET_SERVICE in "${TARGET_SERVICES[@]}"; do
  if [ "$TARGET_SERVICE" = "all" ]; then
    # 1. Build and Push des Microservices Applicatifs
    for SERVICE in "${APP_MICROSERVICES[@]}"; do
      show_progress "$SERVICE"
      build_and_push_standard "$SERVICE" "$BUMP_TYPE"
    done

    # 2. Build des Agents A2A
    show_progress "agent_ops_api"
    build_and_push_agent "agent_ops_api" "$BUMP_TYPE"
    show_progress "agent_hr_api"
    build_and_push_agent "agent_hr_api" "$BUMP_TYPE"
    show_progress "agent_missions_api"
    build_and_push_agent "agent_missions_api" "$BUMP_TYPE"
    show_progress "agent_router_api"
    build_and_push_agent "agent_router_api" "$BUMP_TYPE"
    
    # 3. Build and Upload du Frontend
    show_progress "frontend"
    build_and_upload_frontend "$BUMP_TYPE"

  elif [[ " ${APP_MICROSERVICES[*]} " == *" $TARGET_SERVICE "* || "$TARGET_SERVICE" == "db_migrations" ]]; then
    show_progress "$TARGET_SERVICE"
    build_and_push_standard "$TARGET_SERVICE" "$BUMP_TYPE"
  elif [ "$TARGET_SERVICE" = "db_init" ]; then
    run_db_init_job
  elif [[ "$TARGET_SERVICE" == "agent_"* ]]; then
    show_progress "$TARGET_SERVICE"
    build_and_push_agent "$TARGET_SERVICE" "$BUMP_TYPE"
  elif [ "$TARGET_SERVICE" = "frontend" ]; then
    show_progress "frontend"
    build_and_upload_frontend "$BUMP_TYPE"
  elif [ "$TARGET_SERVICE" = "sync_prompts" ]; then
    sync_system_prompts
  else
    echo -e "${RED}Erreur : Service '${TARGET_SERVICE}' inconnu.${RESET}"
    echo "Utilisez --help pour voir la liste des services disponibles."
    exit 1
  fi
done

# Sync automatique des prompts en fin de déploiement (sauf si c'était la seule action demandée)
if [ "${TARGET_SERVICES[*]}" != "sync_prompts" ]; then
  sync_system_prompts
fi

echo -e "\n${GREEN}=== Déploiement terminé avec succès ! ===${RESET}"
