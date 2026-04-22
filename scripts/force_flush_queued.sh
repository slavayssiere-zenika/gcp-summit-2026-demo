#!/bin/bash
# ============================================================
# DÉBLOCAGE IMMÉDIAT des fichiers bloqués en QUEUED (force flush)
# Utilise force=true pour bypasser le seuil zombie de 30 min
# Usage : ./scripts/force_flush_queued.sh <BASE_URL>
# Ex:    ./scripts/force_flush_queued.sh https://drive-api-xxx.run.app
# ============================================================
set -e

BASE_URL="${1:-}"
if [ -z "$BASE_URL" ]; then
  echo "❌ Usage: $0 <DRIVE_API_BASE_URL>"
  echo "   Ex: $0 https://drive-api-xxx-ew.a.run.app"
  exit 1
fi

echo "🔓 Force flush des fichiers QUEUED sur $BASE_URL..."

# Appel OIDC Cloud Run : le scheduler peut appeler /scheduled/retry-errors sans JWT
OIDC_TOKEN=$(curl -sf \
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience=${BASE_URL}" \
  -H "Metadata-Flavor: Google" 2>/dev/null || echo "")

if [ -n "$OIDC_TOKEN" ]; then
  # Sur Cloud Run / Cloud Shell avec metadata server
  RESPONSE=$(curl -sf -X POST \
    "${BASE_URL}/scheduled/retry-errors?force=true" \
    -H "Authorization: Bearer $OIDC_TOKEN" \
    -H "Content-Type: application/json")
else
  # En local ou sans metadata server — appel sans auth (IAM protège en prod)
  echo "⚠️  Metadata server non disponible — tentative sans token (doit être appelé depuis Cloud)"
  RESPONSE=$(curl -sf -X POST \
    "${BASE_URL}/scheduled/retry-errors?force=true" \
    -H "Content-Type: application/json" || true)
fi

echo "✅ Réponse drive_api:"
echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"

echo ""
echo "🔄 Lancement immédiat de /sync pour republier les PENDING dans Pub/Sub..."
SYNC_RESPONSE=$(curl -sf -X POST \
  "${BASE_URL}/sync" \
  -H "Authorization: Bearer ${OIDC_TOKEN:-dummy}" \
  -H "Content-Type: application/json" || true)

echo "✅ Réponse /sync:"
echo "$SYNC_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$SYNC_RESPONSE"
