#!/usr/bin/env bash
# scripts/run_rag_eval.sh — Évaluation de la qualité RAG (R3)
#
# Usage :
#   ./scripts/run_rag_eval.sh [--env dev|uat|prd] [--fail-fast] [--dry-run] [--tag <tag>]
#
# Options :
#   --env       Environnement cible (défaut: dev). Détermine l'URL de base.
#   --fail-fast Échoue au premier cas raté (défaut: non, continue et rapporte tout).
#   --dry-run   Exécute les requêtes mais ne bloque pas sur les métriques.
#   --tag       Filtre les cas golden par tag (ex: --tag cloud).
#
# Intégration deploy.sh :
#   Appelé automatiquement après le déploiement de cv_api si RAG_EVAL_ENABLED=true.
#   En cas d'échec : avertissement dans le summary, mais pas de rollback.
#   En mode hotfix (--skip-tests) : évaluation ignorée.
#
# Variables d'environnement :
#   RAG_EVAL_ENABLED        Active l'évaluation post-déploiement (défaut: false)
#   RAG_EVAL_RECALL_THRESHOLD Seuil Recall@K global (défaut: 0.5)
#   RAG_EVAL_TOP_K          Top-K pour les métriques (défaut: 5)
#   PROJECT_ID              Projet GCP pour Secret Manager (récupération du token)

set -eo pipefail

# ── Couleurs ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
GREY='\033[0;37m'
RESET='\033[0m'

# ── Defaults ───────────────────────────────────────────────────────────────────
ENV="dev"
FAIL_FAST=false
DRY_RUN=false
TAG_FILTER=""
PROJECT_ID="${PROJECT_ID:-}"

# ── Parsing des arguments ──────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)       ENV="$2";        shift 2 ;;
    --fail-fast) FAIL_FAST=true;  shift   ;;
    --dry-run)   DRY_RUN=true;    shift   ;;
    --tag)       TAG_FILTER="$2"; shift 2 ;;
    *) echo "Usage: $0 [--env dev|uat|prd] [--fail-fast] [--dry-run] [--tag <tag>]"; exit 1 ;;
  esac
done

# ── Résolution de l'URL de base ────────────────────────────────────────────────
YAML_FILE="platform-engineering/envs/${ENV}.yaml"
if [ -f "$YAML_FILE" ]; then
  BASE_DOMAIN=$(grep "base_domain:" "$YAML_FILE" | cut -d'"' -f2)
  # prd  → https://prd.zenika.slavayssiere.fr/api/cv
  # dev  → https://dev.zenika.slavayssiere.fr/api/cv
  # uat  → https://uat.zenika.slavayssiere.fr/api/cv
  if [ "$ENV" = "prd" ]; then
    RAG_EVAL_BASE_URL="https://prd.${BASE_DOMAIN}/api/cv"
  else
    RAG_EVAL_BASE_URL="https://${ENV}.${BASE_DOMAIN}/api/cv"
  fi
  # Auto-résolution de PROJECT_ID si non fourni en env
  if [ -z "${PROJECT_ID:-}" ]; then
    PROJECT_ID=$(grep "^project_id:" "$YAML_FILE" | cut -d'"' -f2)
  fi
else
  RAG_EVAL_BASE_URL="${RAG_EVAL_BASE_URL:-http://localhost:8004}"
fi

echo -e "\n${RED}=== Évaluation RAG (R3) — Environnement: ${ENV} ===${RESET}"
echo -e "${GREY}   URL: ${RAG_EVAL_BASE_URL}${RESET}"
echo -e "${GREY}   DRY_RUN: ${DRY_RUN} | FAIL_FAST: ${FAIL_FAST} | TAG: ${TAG_FILTER:-all}${RESET}\n"

# -- Recuperation du token JWT ----------------------------------------------------
# Priorite : RAG_EVAL_TOKEN fourni en env (ex: depuis manage_env.py ou deploy.sh)
# Sinon : auto-auth via Secret Manager (meme pattern que calibrate_rag.sh)
if [ -n "${RAG_EVAL_TOKEN:-}" ]; then
  echo "[*] Token JWT fourni via RAG_EVAL_TOKEN"
elif [ -n "$PROJECT_ID" ] && [ "$ENV" != "local" ]; then
  echo "[*] RAG_EVAL_TOKEN absent -- recuperation via Secret Manager..."
  GCLOUD_BIN="${GCLOUD_BIN:-gcloud}"
  ADMIN_EMAIL="${ZENIKA_ADMIN_EMAIL:-admin@zenika.com}"
  SECRET_NAME="${ZENIKA_SECRET_NAME:-admin-password-${ENV}}"

  if [ "$ENV" = "prd" ]; then
    AUTH_BASE_URL="https://prd.${BASE_DOMAIN}"
  else
    AUTH_BASE_URL="https://${ENV}.${BASE_DOMAIN}"
  fi

  ADMIN_PWD=$(${GCLOUD_BIN} secrets versions access latest \
    --secret="$SECRET_NAME" --project="$PROJECT_ID" 2>/dev/null || echo "")

  if [ -n "$ADMIN_PWD" ]; then
    AUTH_RESP=$(curl -s -X POST "${AUTH_BASE_URL}/auth/login" \
      -H "Content-Type: application/json" \
      -d "{\"email\":\"${ADMIN_EMAIL}\",\"password\":\"${ADMIN_PWD}\"}" 2>/dev/null || echo "")
    RAG_EVAL_TOKEN=$(echo "$AUTH_RESP" | \
      python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || echo "")
  fi

  if [ -n "$RAG_EVAL_TOKEN" ]; then
    echo -e "${GREEN}[+] Token JWT recupere (email: ${ADMIN_EMAIL})${RESET}"
  else
    echo -e "${YELLOW}[!] Impossible de recuperer le JWT -- les requetes seront non authentifiees${RESET}"
    echo -e "${GREY}    -> Exportez PROJECT_ID et relancez, ou passez RAG_EVAL_TOKEN=\$token${RESET}"
  fi
else
  RAG_EVAL_TOKEN=""
fi

# ── Vérification du virtualenv de test ────────────────────────────────────────
TEST_RUNNER="./test_env/bin/pytest"
if [ ! -f "$TEST_RUNNER" ]; then
  echo -e "${RED}❌ test_env/bin/pytest introuvable.${RESET}"
  echo -e "${YELLOW}   → Créez le venv : python3 -m venv test_env && test_env/bin/pip install -r scripts/requirements.txt${RESET}"
  echo -e "${YELLOW}   → Puis installez httpx : test_env/bin/pip install httpx${RESET}"
  exit 1
fi

# ── Construction des arguments pytest ─────────────────────────────────────────
PYTEST_ARGS=("cv_api/eval/test_rag_quality.py" "-v" "--tb=short" "--no-header" "-W" "ignore::DeprecationWarning:pythonjsonlogger")
[ "$FAIL_FAST" = true ] && PYTEST_ARGS+=("-x")
[ -n "$TAG_FILTER" ] && PYTEST_ARGS+=("-k" "$TAG_FILTER")

# ── Exécution ──────────────────────────────────────────────────────────────────
EVAL_EXIT=0
RAG_EVAL_BASE_URL="$RAG_EVAL_BASE_URL" \
RAG_EVAL_TOKEN="$RAG_EVAL_TOKEN" \
RAG_EVAL_DRY_RUN="$DRY_RUN" \
RAG_EVAL_RECALL_THRESHOLD="${RAG_EVAL_RECALL_THRESHOLD:-0.5}" \
RAG_EVAL_TOP_K="${RAG_EVAL_TOP_K:-5}" \
"$TEST_RUNNER" "${PYTEST_ARGS[@]}" || EVAL_EXIT=$?

# ── Rapport final ──────────────────────────────────────────────────────────────
echo ""
if [ "$EVAL_EXIT" -eq 0 ]; then
  echo -e "${GREEN}✅ [RAG EVAL] Tous les cas golden passent — qualité RAG validée.${RESET}"
elif [ "$DRY_RUN" = true ]; then
  echo -e "${YELLOW}⚠️  [RAG EVAL DRY-RUN] Résultats collectés pour calibrage — aucun blocage.${RESET}"
  EVAL_EXIT=0
else
  echo -e "${RED}❌ [RAG EVAL] Régression RAG détectée — vérifiez GEMINI_EMBEDDING_MODEL ou VECTOR_DISTANCE_THRESHOLD.${RESET}"
  echo -e "${GREY}   → Logs : consultez la sortie pytest ci-dessus${RESET}"
  echo -e "${GREY}   → Pour calibrer : RAG_EVAL_DRY_RUN=true ./scripts/run_rag_eval.sh --env ${ENV}${RESET}"
fi

exit $EVAL_EXIT
