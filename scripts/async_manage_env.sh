#!/bin/bash
set -e

ACTION=$1
ENV=$2
VERSION=$3

if [ -z "$ACTION" ] || [ -z "$ENV" ] || [ -z "$VERSION" ]; then
    echo "Usage: $0 <deploy|destroy|plan> <env> <container_version>"
    echo "Example: $0 deploy dev v1.0.0"
    exit 1
fi

if [ ! -d "platform-engineering" ]; then
    echo "[!] Please run this script from the root of the repository."
    exit 1
fi

PROJECT_ID="slavayssiere-sandbox-462015"
REGION="europe-west1"
AR_NAME="z-gcp-summit-services"
JOB_NAME="platform-engineering"

IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_NAME}/${JOB_NAME}"
FULL_IMAGE="${IMAGE}:${VERSION}"

# 1. Build and push Platform Engineering Container locally
echo "[*] Building Platform Engineering container version ${VERSION} locally via Docker..."
# IMPORTANT: On force l'architecture linux/amd64 requise par Cloud Run (surtout si exécuté depuis un Mac Apple Silicon)
docker build --platform linux/amd64 -t $FULL_IMAGE platform-engineering

echo "[*] Pushing image to Google Artifact Registry..."
docker push $FULL_IMAGE

# 2. Collect local versions to pass as environment variables
echo "[*] Collecting local component versions..."

COMPONENTS=("agent_api" "users_api" "items_api" "competencies_api" "cv_api" "prompts_api" "drive_api" "missions_api" "market_mcp" "db_migrations" "frontend")
ENV_VARS_ARGS=""

for COMP in "${COMPONENTS[@]}"; do
    V_FILE="${COMP}/VERSION"
    if [ -f "$V_FILE" ]; then
        COMP_VERSION=$(cat "$V_FILE" | tr -d '[:space:]')
    else
        COMP_VERSION="v0.0.1"
    fi
    VAR_NAME=$(echo "${COMP}_VERSION" | tr '[:lower:]' '[:upper:]')
    ENV_VARS_ARGS="${ENV_VARS_ARGS}${VAR_NAME}=${COMP_VERSION},"
done

# Remove trailing comma
ENV_VARS_ARGS=${ENV_VARS_ARGS%,}

echo "[*] Updating Cloud Run Job '$JOB_NAME' with new container image..."
gcloud run jobs update $JOB_NAME \
    --image=$FULL_IMAGE \
    --region=$REGION \
    --project=$PROJECT_ID

# 3. Run the job asynchronously and capture its exact Execution ID
echo "[*] Lancement de l'exécution $JOB_NAME pour l'action '$ACTION' sur l'environnement '$ENV'..."
EXEC_ID=$(gcloud run jobs execute $JOB_NAME \
    --args="$ACTION,--env,$ENV" \
    --update-env-vars="$ENV_VARS_ARGS" \
    --region=$REGION \
    --project=$PROJECT_ID \
    --format="value(metadata.name)")

echo "[+] Job démarré sous l'ID : $EXEC_ID"
echo "========================================================="
echo "[*] Attachement au flux de logs de l'exécution en temps réel..."
echo "========================================================="

# Streame exclusivement les logs de cette exécution spécifique
# Remarque : La fonctionnalité de tail s'appuie sur le composant beta
gcloud beta run executions logs tail $EXEC_ID \
    --region=$REGION \
    --project=$PROJECT_ID \
    --log-http
