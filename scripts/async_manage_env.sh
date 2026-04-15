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

# 1. Build and push Platform Engineering Container
echo "[*] Building Platform Engineering container version ${VERSION} via GCP Cloud Build..."
# Note: This is fully native and independent of local architecture (arm vs amd64)
gcloud builds submit platform-engineering --tag $FULL_IMAGE --project $PROJECT_ID

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

# 3. Run the job asynchronously
echo "[*] Execution Async of $JOB_NAME for action '$ACTION' over env '$ENV'..."
gcloud run jobs execute $JOB_NAME \
    --args="$ACTION,--env,$ENV" \
    --update-env-vars="$ENV_VARS_ARGS" \
    --region=$REGION \
    --project=$PROJECT_ID

echo "[+] Job execution triggered asynchronously!"
echo "========================================================="
echo "You can check progression live using:"
echo "gcloud run jobs logs tail $JOB_NAME --region=$REGION --project=$PROJECT_ID"
echo "========================================================="
