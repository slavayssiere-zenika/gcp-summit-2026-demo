#!/usr/bin/env bash
# =============================================================================
# force_requeue_processing.sh
# Reset immédiat de tous les CVs bloqués en PROCESSING/QUEUED → PENDING → Pub/Sub
# Usage : ./scripts/force_requeue_processing.sh [BASE_URL]
# =============================================================================
set -euo pipefail

BASE_URL="${1:-https://dev.zenika.slavayssiere.fr}"
PLATFORM_DIR="$(dirname "$0")/../platform-engineering"

echo "🔍 Récupération des credentials depuis Terraform..."
ADMIN_PASSWORD=$(cd "$PLATFORM_DIR" && terraform output -raw admin_password 2>/dev/null || echo "")

if [ -z "$ADMIN_PASSWORD" ]; then
  echo "⚠️  Impossible de récupérer le mot de passe via Terraform."
  echo "   Entrez le mot de passe admin manuellement :"
  read -s -r ADMIN_PASSWORD
fi

echo "🔑 Obtention du token JWT..."
TOKEN=$(curl -s -X POST "${BASE_URL}/api/users/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"username\": \"admin\", \"password\": \"${ADMIN_PASSWORD}\"}" \
  | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))")

if [ -z "$TOKEN" ]; then
  echo "❌ Échec de l'authentification. Vérifiez l'URL et le mot de passe."
  exit 1
fi

echo "✅ Token obtenu."

echo ""
echo "1️⃣  Force reset de TOUS les PROCESSING/QUEUED → PENDING..."
RESET_RESULT=$(curl -s -X POST "${BASE_URL}/api/drive/retry-errors?force=true" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json")
echo "   Résultat : ${RESET_RESULT}"

echo ""
echo "2️⃣  Déclenche le sync pour republier en Pub/Sub..."
SYNC_RESULT=$(curl -s -X POST "${BASE_URL}/api/drive/sync" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json")
echo "   Résultat : ${SYNC_RESULT}"

echo ""
echo "3️⃣  Statut actuel du pipeline :"
curl -s "${BASE_URL}/api/drive/status" \
  -H "Authorization: Bearer ${TOKEN}" \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'   PENDING    : {d.get(\"pending\", 0)}')
print(f'   QUEUED     : {d.get(\"queued\", 0)}')
print(f'   PROCESSING : {d.get(\"processing\", 0)}')
print(f'   IMPORTED   : {d.get(\"imported\", 0)}')
print(f'   ERRORS     : {d.get(\"errors\", 0)}')
"

echo ""
echo "✅ Terminé. Les CVs devraient apparaître en QUEUED puis PROCESSING dans l'UI."
