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
  echo -e "  db_init        Build + exécute le Cloud Run Job d'initialisation AlloyDB"
  echo -e "  sync_prompts   Synchronise uniquement les system prompts vers prompts_api"
  echo ""
  echo "Bump Types (SemVer):"
  echo "  patch (défaut), minor, major, none"
  echo ""
  echo "Options:"
  echo "  --no-deploy    Construit et pousse les images Docker uniquement, ignore le déploiement Cloud Run"
  echo "  --skip-unchanged Ignore le build/deploy des services qui n'ont pas changé depuis leur dernier tag"
  echo "Note: sync_prompts est aussi exécuté automatiquement après tout déploiement."
  echo ""
  echo "Exemples:"

  echo "  $0 all minor"
  echo "  $0 users_api cv_api minor"
  echo "  $0 db_migrations"
  exit 0
fi

# Déclaration des tableaux de suivi
DEPLOYS_SUCCESS=()
DEPLOYS_FAILED=()
DEPLOYS_SKIPPED=()
CURRENT_DEPLOYING_SERVICE=""

get_display_version() {
  local raw_name=$1
  local svc_name=$(echo "$raw_name" | awk '{print $1}')
  
  if [ -f "${svc_name}/VERSION" ]; then
    echo " ($(cat "${svc_name}/VERSION"))"
  else
    echo ""
  fi
}

print_summary() {
  local exit_code=$?
  # Si le script plante inopinément pendant un service (ex: docker build failed)
  if [ -n "$CURRENT_DEPLOYING_SERVICE" ]; then
    DEPLOYS_FAILED+=("${CURRENT_DEPLOYING_SERVICE} (Fatal/Build error)")
  fi

  echo -e "\n${GREY}============================================================${RESET}"
  if [ $exit_code -eq 0 ] && [ ${#DEPLOYS_FAILED[@]} -eq 0 ]; then
    echo -e "              ${GREEN}✅ DÉPLOIEMENTS TERMINÉS AVEC SUCCÈS${RESET}"
  else
    echo -e "              ${RED}⚠️ DÉPLOIEMENTS TERMINÉS AVEC ERREURS${RESET}"
  fi
  echo -e "${GREY}============================================================${RESET}"
  
  if [ ${#DEPLOYS_SUCCESS[@]} -gt 0 ]; then
    echo -e "${GREEN}✅ RÉUSSIS :${RESET}"
    for svc in "${DEPLOYS_SUCCESS[@]}"; do
      local ver=$(get_display_version "$svc")
      echo -e "   - ${svc}${ver}"
    done
  fi

  if [ ${#DEPLOYS_SKIPPED[@]} -gt 0 ]; then
    echo -e "${YELLOW}⏭️ SKIPPÉS (Aucun changement) :${RESET}"
    for svc in "${DEPLOYS_SKIPPED[@]}"; do
      local ver=$(get_display_version "$svc")
      echo -e "   - ${svc}${ver}"
    done
  fi
  
  if [ ${#DEPLOYS_FAILED[@]} -gt 0 ]; then
    local build_failures=()
    local deploy_failures=()
    
    for svc in "${DEPLOYS_FAILED[@]}"; do
      if [[ "$svc" == *"Build error"* ]]; then
        build_failures+=("$svc")
      else
        deploy_failures+=("$svc")
      fi
    done
    
    if [ ${#build_failures[@]} -gt 0 ]; then
      echo -e "${RED}❌ ÉCHECS DE BUILD (Docker/Local) :${RESET}"
      for svc in "${build_failures[@]}"; do
        local ver=$(get_display_version "$svc")
        echo -e "   - ${svc}${ver}"
      done
    fi
    
    if [ ${#deploy_failures[@]} -gt 0 ]; then
      echo -e "${RED}❌ ÉCHECS DE DÉPLOIEMENT (Cloud Run/GCP) :${RESET}"
      for svc in "${deploy_failures[@]}"; do
        local ver=$(get_display_version "$svc")
        echo -e "   - ${svc}${ver}"
      done
    fi
  fi
  echo -e "${GREY}============================================================${RESET}\n"
  
  exit $exit_code
}

trap print_summary EXIT

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
  
  echo "$NEW_TAG"
}

# ==============================================================================
# Git Diff Helper
# ==============================================================================

compute_service_hash() {
  local SERVICE=$1
  local DIRS_TO_CHECK=("./${SERVICE}")
  if [[ "$SERVICE" == "agent_hr_api" || "$SERVICE" == "agent_ops_api" || "$SERVICE" == "agent_missions_api" ]]; then
    DIRS_TO_CHECK+=("./agent_commons")
  fi

  # Compute a SHA1 hash of all files in the relevant directories
  # Exclude VERSION and HASH files, and common ignore paths
  find "${DIRS_TO_CHECK[@]}" -type f ! -name "VERSION" ! -name "HASH" ! -path "*/__pycache__/*" ! -path "*/.venv/*" ! -path "*/node_modules/*" ! -path "*/dist/*" ! -path "*/.DS_Store" -exec shasum {} + | sort | shasum | awk '{print $1}'
}

save_service_hash() {
  local SERVICE=$1
  compute_service_hash "$SERVICE" > "${SERVICE}/HASH"
}

has_changes() {
  local SERVICE=$1
  
  if [ ! -f "${SERVICE}/HASH" ]; then
    return 0 # Pas de fichier HASH -> on build
  fi
  
  local SAVED_HASH=$(cat "${SERVICE}/HASH")
  local CURRENT_HASH=$(compute_service_hash "$SERVICE")
  
  if [ "$SAVED_HASH" == "$CURRENT_HASH" ]; then
    return 1 # Pas de changement
  else
    return 0 # Changements détectés
  fi
}

# ==============================================================================
# Helper Functions
# ==============================================================================

update_cloudrun() {
  local SERVICE=$1
  local TAG=$2
  
  local CLEAN_NAME="${SERVICE//_/-}"
  local SVC_NAME="${CLEAN_NAME}-dev"
  
  if ! gcloud run services describe "$SVC_NAME" --region "$REGION" --project "$PROJECT_ID" >/dev/null 2>&1; then
    echo -e "${YELLOW}--- Skipped Cloud Run update for $SERVICE (Service $SVC_NAME introuvable, config Terraform requise d'abord) ---${RESET}"
    return 0
  fi
  
  echo "--- Déploiement de $SERVICE sur Cloud Run (dev) ---"
  local IMAGE_URL="${DOCKER_REPO}/${SERVICE}:${TAG}"
  
  local CMD_ARGS=(
    "gcloud" "run" "services" "update" "$SVC_NAME"
    "--region" "$REGION"
    "--project" "$PROJECT_ID"
    "--container" "api" "--image" "$IMAGE_URL"
    "--update-env-vars" "APP_VERSION=$TAG"
  )
  
  if [[ "$SERVICE" == "users_api" || "$SERVICE" == "items_api" || "$SERVICE" == "competencies_api" || "$SERVICE" == "cv_api" || "$SERVICE" == "drive_api" || "$SERVICE" == "missions_api" ]]; then
    CMD_ARGS+=( "--container" "mcp" "--image" "$IMAGE_URL" "--update-env-vars" "APP_VERSION=$TAG" )
  fi
  
  if "${CMD_ARGS[@]}"; then
    return 0
  else
    echo -e "${RED}/!\ Échec partiel du déploiement Cloud Run pour $SERVICE${RESET}"
    return 1
  fi
}

run_db_init_job() {
  local JOB_NAME="db-init-job-dev"

  # AlloyDB n'est accessible que depuis le VPC GCP (IP privée).
  # Le job doit obligatoirement être exécuté via Cloud Run (accès VPC direct).
  if gcloud run jobs describe "$JOB_NAME" --region "$REGION" --project "$PROJECT_ID" >/dev/null 2>&1; then
    echo "--- Lancement du Cloud Run Job: $JOB_NAME ---"
    if gcloud run jobs execute "$JOB_NAME" \
      --region "$REGION" \
      --project "$PROJECT_ID" \
      --wait; then
      return 0
    else
      return 1
    fi
  else
    echo -e "${RED}--- Cloud Run Job $JOB_NAME introuvable. Exécutez d'abord: ./scripts/deploy.sh db_init ---${RESET}"
    return 1
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
  
  echo -e "
${GREY}------------------------------------------------------------${RESET}"
  echo -e "${RED}🚀 BUILDING: ${CURRENT}${RESET}"
  
  if [ ${#DONE_TASKS[@]} -gt 0 ]; then
    echo -e "${GREEN}✅ COMPLETED: ${DONE_TASKS[*]}${RESET}"
  fi
  
  if [ ${#TODO_TASKS[@]} -gt 0 ]; then
    echo -e "${GREY}⏳ REMAINING: ${TODO_TASKS[*]}${RESET}"
  fi
  echo -e "${GREY}------------------------------------------------------------${RESET}
"
}

build_and_push_standard() {
  local SERVICE=$1
  local BUMP=${2:-"patch"}
  
  if [ "$SKIP_UNCHANGED" = true ] && [ "$SERVICE" != "db_migrations" ] && [ "$SERVICE" != "db_init" ] && ! has_changes "$SERVICE"; then
    echo -e "${YELLOW}--- Skipped $SERVICE (no changes detected since last deployment) ---${RESET}"
    DEPLOYS_SKIPPED+=("$SERVICE")
    return 0
  fi

  local TAG=$(get_service_tag "$SERVICE" "$BUMP")
  echo "--- Building $SERVICE ($TAG) ---"
  local IMAGE_NAME="${DOCKER_REPO}/${SERVICE}"
  
  # Build pour Cloud Run (nécessite amd64)
  docker build --platform linux/amd64 -t "${IMAGE_NAME}:${TAG}" -t "${IMAGE_NAME}:latest" "./${SERVICE}"
  
  # Push
  echo "--- Pushing $SERVICE ---"
  docker push "${IMAGE_NAME}:${TAG}"
  docker push "${IMAGE_NAME}:latest"
  
  if [ "$SKIP_CLOUDRUN" = true ]; then
    echo "--- Skipping update_cloudrun/jobs for $SERVICE ---"
    DEPLOYS_SUCCESS+=("$SERVICE (Docker only)")
  else
    if [ "$SERVICE" != "db_migrations" ]; then
      if update_cloudrun "$SERVICE" "$TAG"; then
        DEPLOYS_SUCCESS+=("$SERVICE")
    save_service_hash "$SERVICE"
      else
        DEPLOYS_FAILED+=("$SERVICE (Cloud Run)")
      fi
    else
      # Chaine automatiquement avec le init_job
      run_db_init_job || true

      local CLEAN_NAME="${SERVICE//_/-}"
      local JOB_NAME="${CLEAN_NAME}-job-dev"
      
      if gcloud run jobs describe "$JOB_NAME" --region "$REGION" --project "$PROJECT_ID" >/dev/null 2>&1; then
        echo "--- Mise à jour de l'image du Cloud Run Job: $JOB_NAME ---"
        gcloud run jobs update "$JOB_NAME" \
          --region "$REGION" \
          --project "$PROJECT_ID" \
          --image "${IMAGE_NAME}:${TAG}"
        
        echo "--- Lancement du Cloud Run Job: $JOB_NAME ---"
        if gcloud run jobs execute "$JOB_NAME" \
          --region "$REGION" \
          --project "$PROJECT_ID" \
          --wait; then
          DEPLOYS_SUCCESS+=("$SERVICE")
    save_service_hash "$SERVICE"
        else
          DEPLOYS_FAILED+=("$SERVICE (Job execution failed)")
        fi
      else
        echo "--- Cloud Run Job $JOB_NAME n'existe pas encore. Seul le push de l'image a été effectué ---"
        DEPLOYS_SUCCESS+=("$SERVICE (Docker only)")
      fi
    fi
  fi
}

build_and_push_agent() {
  local SERVICE=$1
  local BUMP=${2:-"patch"}
  
  if [ "$SKIP_UNCHANGED" = true ] && ! has_changes "$SERVICE"; then
    echo -e "${YELLOW}--- Skipped $SERVICE (no changes detected since last deployment) ---${RESET}"
    DEPLOYS_SKIPPED+=("$SERVICE")
    return 0
  fi

  local TAG=$(get_service_tag "$SERVICE" "$BUMP")
  
  # Build context doit être la racine pour inclure agent_commons
  echo "--- Building $SERVICE ($TAG) ---"
  local AGENT_IMAGE_NAME="${DOCKER_REPO}/${SERVICE}"
  docker build --platform linux/amd64 -t "${AGENT_IMAGE_NAME}:${TAG}" -t "${AGENT_IMAGE_NAME}:latest" -f "./${SERVICE}/Dockerfile" .
  echo "--- Pushing $SERVICE ---"
  docker push "${AGENT_IMAGE_NAME}:${TAG}"
  docker push "${AGENT_IMAGE_NAME}:latest"
  
  if [ "$SKIP_CLOUDRUN" = true ]; then
    echo "--- Skipping update_cloudrun for $SERVICE ---"
    DEPLOYS_SUCCESS+=("$SERVICE (Docker only)")
  else
    if update_cloudrun "$SERVICE" "$TAG"; then
      DEPLOYS_SUCCESS+=("$SERVICE")
    save_service_hash "$SERVICE"
    else
      DEPLOYS_FAILED+=("$SERVICE (Cloud Run)")
    fi
  fi
}

build_and_upload_frontend() {
  local BUMP=${1:-"patch"}

  if [ "$SKIP_UNCHANGED" = true ] && ! has_changes "frontend"; then
    echo -e "${YELLOW}--- Skipped frontend (no changes detected since last deployment) ---${RESET}"
    DEPLOYS_SKIPPED+=("frontend")
    return 0
  fi

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
    DEPLOYS_SUCCESS+=("frontend")
    save_service_hash "frontend"
  else
    echo "-> /!\ Impossible de récupérer le nom du bucket dev depuis Terraform."
    DEPLOYS_FAILED+=("frontend (Bucket introuvable)")
  fi
}

sync_system_prompts() {
  echo -e "
${RED}=== Synchronisation des System Prompts (Grounding) ===${RESET}"
  
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
  if python3 scripts/sync_prompts.py --url "$API_URL" --password "$ADMIN_PWD"; then
    return 0
  else
    return 1
  fi
}

# ==============================================================================
# Main logic
# ==============================================================================
# Liste des services applicatifs (déployés par 'all')
APP_MICROSERVICES=("users_api" "items_api" "competencies_api" "cv_api" "prompts_api" "drive_api" "missions_api" "analytics_mcp" "monitoring_mcp")
# Liste de tous les services possibles pour la validation
VALID_SERVICES=("db_migrations" "db_init" "sync_prompts" "agent_router_api" "agent_hr_api" "agent_ops_api" "agent_missions_api" "frontend" "${APP_MICROSERVICES[@]}")

BUMP_TYPE="patch"
TARGET_SERVICES=()
SKIP_CLOUDRUN=false

for arg in "$@"; do
  if [[ "$arg" == "patch" || "$arg" == "minor" || "$arg" == "major" || "$arg" == "none" ]]; then
    BUMP_TYPE="$arg"
  elif [[ "$arg" == "--no-deploy" ]]; then
    SKIP_CLOUDRUN=true
  elif [[ "$arg" == "--skip-unchanged" ]]; then
    SKIP_UNCHANGED=true
  else
    # Normalize input (e.g. agent-api -> agent_api)
    TARGET_SERVICES+=("${arg//-/_}")
  fi
done

if [ ${#TARGET_SERVICES[@]} -eq 0 ]; then
  TARGET_SERVICES=("all")
fi

# Expansion de 'all' par la liste complète des services et ajout des services explicites
NEW_TARGETS=()
for svc in "${TARGET_SERVICES[@]}"; do
  if [ "$svc" == "all" ]; then
    NEW_TARGETS+=("${APP_MICROSERVICES[@]}" "agent_router_api" "agent_hr_api" "agent_ops_api" "agent_missions_api" "frontend")
  else
    NEW_TARGETS+=("$svc")
  fi
done

# Déduplication tout en conservant l'ordre (au cas où "all users_api" est lancé)
ALL_TASKS=()
for svc in "${NEW_TARGETS[@]}"; do
  if [[ ! " ${ALL_TASKS[*]} " =~ " ${svc} " ]]; then
    ALL_TASKS+=("$svc")
  fi
done

for TARGET_SERVICE in "${ALL_TASKS[@]}"; do
  CURRENT_DEPLOYING_SERVICE="$TARGET_SERVICE"
  if [[ " ${APP_MICROSERVICES[*]} " == *" $TARGET_SERVICE "* || "$TARGET_SERVICE" == "db_migrations" ]]; then
    show_progress "$TARGET_SERVICE"
    build_and_push_standard "$TARGET_SERVICE" "$BUMP_TYPE"
  elif [ "$TARGET_SERVICE" = "db_init" ]; then
    # ── DB Init : build image dédiée + mise à jour du Cloud Run Job + exécution ──
    # AlloyDB n'est accessible qu'en VPC GCP (IP privée) : pas d'exécution locale possible.
    if [ "$SKIP_UNCHANGED" = true ] && ! has_changes "db_init"; then
      echo -e "${YELLOW}--- Skipped db_init (no changes detected since last deployment) ---${RESET}"
      DEPLOYS_SKIPPED+=("db_init")
      CURRENT_DEPLOYING_SERVICE=""
      continue
    fi
    show_progress "db_init"
    local_tag=$(get_service_tag "db_init" "$BUMP_TYPE")
    db_init_image="${DOCKER_REPO}/db_init:${local_tag}"
    echo "--- Building db_init ($local_tag) ---"
    docker build --platform linux/amd64 \
      -t "${DOCKER_REPO}/db_init:${local_tag}" \
      -t "${DOCKER_REPO}/db_init:latest" \
      ./db_init
    echo "--- Pushing db_init ---"
    docker push "${DOCKER_REPO}/db_init:${local_tag}"
    docker push "${DOCKER_REPO}/db_init:latest"

    if [ "$SKIP_CLOUDRUN" = true ]; then
      echo "--- Skipping update_cloudrun/jobs for db_init ---"
      DEPLOYS_SUCCESS+=("db_init (Docker only)")
      save_service_hash "db_init"
    else
      JOB_NAME="db-init-job-dev"
      if gcloud run jobs describe "$JOB_NAME" --region "$REGION" --project "$PROJECT_ID" >/dev/null 2>&1; then
        echo "--- Mise à jour de l'image du Cloud Run Job $JOB_NAME ---"
        gcloud run jobs update "$JOB_NAME" \
          --region "$REGION" \
          --project "$PROJECT_ID" \
          --image "$db_init_image"
        
        if run_db_init_job; then
          DEPLOYS_SUCCESS+=("db_init")
          save_service_hash "db_init"
        else
          DEPLOYS_FAILED+=("db_init (Job failed)")
        fi
      else
        echo "--- Cloud Run Job $JOB_NAME n'existe pas encore. Seul le push de l'image a été effectué ---"
        DEPLOYS_SUCCESS+=("db_init (Docker only)")
      save_service_hash "db_init"
      fi
    fi
  elif [[ "$TARGET_SERVICE" == "agent_"* ]]; then
    show_progress "$TARGET_SERVICE"
    build_and_push_agent "$TARGET_SERVICE" "$BUMP_TYPE"
  elif [ "$TARGET_SERVICE" = "frontend" ]; then
    show_progress "frontend"
    build_and_upload_frontend "$BUMP_TYPE"
  elif [ "$TARGET_SERVICE" = "sync_prompts" ]; then
    if sync_system_prompts; then DEPLOYS_SUCCESS+=("sync_prompts"); else DEPLOYS_FAILED+=("sync_prompts"); fi
  else
    echo -e "${RED}Erreur : Service '${TARGET_SERVICE}' inconnu.${RESET}"
    echo "Utilisez --help pour voir la liste des services disponibles."
    exit 1
  fi
  CURRENT_DEPLOYING_SERVICE=""
done

# Sync automatique des prompts en fin de déploiement si l'un des services impactés est concerné
PROMPT_SERVICES=("prompts_api" "agent_router_api" "agent_hr_api" "agent_ops_api" "agent_missions_api" "cv_api" "missions_api")
SHOULD_SYNC=false

for svc in "${PROMPT_SERVICES[@]}"; do
  if [[ " ${ALL_TASKS[*]} " == *" $svc "* ]]; then
    SHOULD_SYNC=true
    break
  fi
done

if [ "$SHOULD_SYNC" = true ]; then
  # On s'assure que si prompts_api était dans la liste, son déploiement n'a pas échoué
  if [[ " ${ALL_TASKS[*]} " == *" prompts_api "* ]] && [[ ! " ${DEPLOYS_SUCCESS[*]} " == *" prompts_api "* && ! " ${DEPLOYS_SKIPPED[*]} " == *" prompts_api "* ]]; then
    echo -e "${YELLOW}--- Synchronisation des prompts ignorée car le déploiement de prompts_api a échoué ---${RESET}"
  else
    CURRENT_DEPLOYING_SERVICE="sync_prompts"
    if sync_system_prompts; then 
      DEPLOYS_SUCCESS+=("sync_prompts")
    else 
      DEPLOYS_FAILED+=("sync_prompts")
    fi
    CURRENT_DEPLOYING_SERVICE=""
  fi
fi

# Le summary de fin est géré par le trap EXIT.
