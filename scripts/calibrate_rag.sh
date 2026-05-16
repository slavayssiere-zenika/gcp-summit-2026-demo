#!/usr/bin/env bash
# scripts/calibrate_rag.sh — Calibrage initial du golden dataset RAG (R3)
#
# Usage :
#   ./scripts/calibrate_rag.sh [--env dev|uat|prd]
#
#   --env       Environnement cible (défaut: dev)
#   Flux complet : dry-run → ouverture éditeur → validation automatique

set -eo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; GREY='\033[0;37m'; BOLD='\033[1m'; RESET='\033[0m'

ENV="dev"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENV="$2"; shift 2 ;;
    *) echo "Usage: $0 [--env dev|uat|prd]"; exit 1 ;;
  esac
done

YAML_FILE="platform-engineering/envs/${ENV}.yaml"
if [ -f "$YAML_FILE" ]; then
  BASE_DOMAIN=$(grep "base_domain:" "$YAML_FILE" | cut -d'"' -f2)
  RAG_EVAL_BASE_URL="https://api.${ENV}.${BASE_DOMAIN}/api/cv"
  # URL publique pour l'auth (même pattern que mcp_cli.py) :
  #   prd → https://prd.zenika.slavayssiere.fr
  #   dev → https://dev.zenika.slavayssiere.fr
  if [ "$ENV" = "prd" ]; then
    AUTH_BASE_URL="https://prd.${BASE_DOMAIN}"
  else
    AUTH_BASE_URL="https://${ENV}.${BASE_DOMAIN}"
  fi
  # Auto-détection du project_id depuis le yaml si non défini dans le shell
  if [ -z "${PROJECT_ID:-}" ]; then
    PROJECT_ID=$(grep "^project_id:" "$YAML_FILE" | cut -d'"' -f2)
  fi
else
  RAG_EVAL_BASE_URL="${RAG_EVAL_BASE_URL:-http://localhost:8004}"
  AUTH_BASE_URL="http://localhost:8000"
fi

LOG_DIR="logs"; REPORT_FILE="${LOG_DIR}/rag_calibration_$(date +%Y%m%d_%H%M%S).md"
mkdir -p "$LOG_DIR"

echo -e "\n${BOLD}${RED}╔═════════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${RED}║     Calibrage du Golden Dataset RAG (R3)        ║${RESET}"
echo -e "${BOLD}${RED}╚═════════════════════════════════════════════════╝${RESET}\n"
echo -e "${GREY}  Env  : ${ENV} | URL : ${RAG_EVAL_BASE_URL}${RESET}"
echo -e "${GREY}  Rapport : ${REPORT_FILE}${RESET}\n"

TEST_RUNNER="uv run pytest"
if ! command -v uv >/dev/null 2>&1; then
  echo -e "${RED}❌ uv introuvable.${RESET}"
  echo -e "${YELLOW}   Installez uv : curl -LsSf https://astral.sh/uv/install.sh | sh${RESET}"
  exit 1
fi

uv run python3 -c "import httpx" 2>/dev/null || \
  { echo -e "${YELLOW}Installation httpx...${RESET}"; uv add httpx --quiet; }

# ── Token JWT ──────────────────────────────────────────────────────────────────
RAG_EVAL_TOKEN=""

if [ "$ENV" = "local" ]; then
  echo -e "${GREY}  [local] Pas d'auth JWT nécessaire${RESET}\n"
elif [ -z "${PROJECT_ID:-}" ]; then
  echo -e "${RED}❌ PROJECT_ID non défini et introuvable dans ${YAML_FILE}.${RESET}"
  echo -e "${YELLOW}   Exportez la variable avant de relancer :${RESET}"
  echo -e "${CYAN}   export PROJECT_ID=prod-ia-staffing${RESET}"
  exit 1
else
  # L'email admin et le nom du secret peuvent être surchargés via env
  ADMIN_EMAIL="${ZENIKA_ADMIN_EMAIL:-admin@zenika.com}"
  SECRET_NAME="${ZENIKA_SECRET_NAME:-admin-password-${ENV}}"

  echo -e "${GREY}[*] JWT via Secret Manager (secret: ${SECRET_NAME}, projet: ${PROJECT_ID}) ...${RESET}"
  ADMIN_PWD=$(gcloud secrets versions access latest \
    --secret="$SECRET_NAME" --project="$PROJECT_ID" 2>/dev/null || echo "")
  if [ -z "$ADMIN_PWD" ]; then
    echo -e "${RED}❌ Impossible de lire ${SECRET_NAME} dans Secret Manager.${RESET}"
    echo -e "${YELLOW}   Vérifiez vos droits gcloud : gcloud auth application-default login${RESET}"
    exit 1
  fi
  echo -e "${GREY}   Mot de passe récupéré (${#ADMIN_PWD} caractères)${RESET}"

  AUTH_URL="${AUTH_BASE_URL}/auth/login"
  echo -e "${GREY}   POST ${AUTH_URL} (email: ${ADMIN_EMAIL})${RESET}"
  AUTH_RESP=$(curl -s -X POST "$AUTH_URL" -H "Content-Type: application/json" \
    -d "{\"email\":\"${ADMIN_EMAIL}\",\"password\":\"${ADMIN_PWD}\"}" 2>/dev/null || echo "")
  RAG_EVAL_TOKEN=$(echo "$AUTH_RESP" | \
    python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || echo "")
  if [ -z "$RAG_EVAL_TOKEN" ]; then
    echo -e "${RED}❌ Échec de l'authentification sur ${AUTH_URL}.${RESET}"
    echo -e "${GREY}   Réponse HTTP : ${AUTH_RESP:0:300}${RESET}"
    echo -e "${YELLOW}   → Surcharger l'email : ZENIKA_ADMIN_EMAIL=votre@email.com ./scripts/calibrate_rag.sh${RESET}"
    exit 1
  fi
  echo -e "${GREEN}  ✅ JWT récupéré (projet: ${PROJECT_ID}, email: ${ADMIN_EMAIL})${RESET}\n"
fi

# ── ÉTAPE 1 : Dry-run ─────────────────────────────────────────────────────────
echo -e "${CYAN}═══ ÉTAPE 1/3 — Dry-run : collecte des top-10 résultats réels ════${RESET}\n"
DRY_RUN_LOG="${LOG_DIR}/rag_dryrun_raw.txt"

RAG_EVAL_BASE_URL="$RAG_EVAL_BASE_URL" \
RAG_EVAL_TOKEN="$RAG_EVAL_TOKEN" \
RAG_EVAL_DRY_RUN="true" \
RAG_EVAL_TOP_K="10" \
"$TEST_RUNNER" cv_api/eval/test_rag_quality.py::test_rag_recall_at_k \
  -v --tb=short --no-header -s -W "ignore::DeprecationWarning:pythonjsonlogger" 2>&1 | tee "$DRY_RUN_LOG" || true

# ── ÉTAPE 2 : Rapport de calibrage ────────────────────────────────────────────
echo -e "\n${CYAN}═══ ÉTAPE 2/3 — Génération du rapport de calibrage ════════════${RESET}\n"

{
  echo "# Rapport de Calibrage RAG — $(date '+%Y-%m-%d %H:%M')"
  echo ""
  echo "**Env** : \`${ENV}\` | **URL** : \`${RAG_EVAL_BASE_URL}\`"
  echo ""
  echo "## Instructions"
  echo ""
  echo "1. Consultez les **Top-10 IDs** ci-dessous pour chaque cas golden"
  echo "2. Ouvrez \`cv_api/eval/golden_queries.json\`"
  echo "3. Pour chaque cas, copiez les IDs **pertinents** dans \`expected_user_ids\`"
  echo "   - Vérifiez via \`source_url\` (URL Drive) que le profil correspond"
  echo "4. Relancez : \`./scripts/calibrate_rag.sh --env ${ENV} --validate\`"
  echo ""
  echo "## Résultats bruts"
  echo '```'
  grep -E "Top-10|Source URLs|Scores|^\[" "$DRY_RUN_LOG" 2>/dev/null || \
    echo "Consultez ${DRY_RUN_LOG}"
  echo '```'
  echo ""
  echo "## Variables de configuration"
  echo "| Variable | Défaut | Description |"
  echo "|---|---|---|"
  echo "| \`VECTOR_DISTANCE_THRESHOLD\` | \`0.55\` | Seuil de distance cosine (R2) |"
  echo "| \`MAX_VECTOR_CANDIDATES\` | \`500\` | Pool max de candidats explorés (fix 2.12) |"
  echo "| \`GEMINI_EMBEDDING_MODEL\` | *(env Cloud Run)* | Modèle d'embedding (R1) |"
} > "$REPORT_FILE"

echo -e "${GREEN}✅ Rapport généré : ${REPORT_FILE}${RESET}\n"
echo -e "${BOLD}📋 Top-10 IDs à copier dans golden_queries.json :${RESET}\n"
grep -E "^\[|Top-10" "$DRY_RUN_LOG" 2>/dev/null || \
  echo -e "${GREY}  (voir ${DRY_RUN_LOG})${RESET}"

echo ""
# ── ÉTAPE 2b : Injection automatique des IDs dans golden_queries.json ─────────
echo -e "${CYAN}═══ ÉTAPE 2/3 — Injection automatique dans golden_queries.json ══${RESET}\n"

./test_env/bin/python3 - <<'PYEOF'
import json
import re
import sys
from pathlib import Path

log_path   = Path("logs/rag_dryrun_raw.txt")
golden_path = Path("cv_api/eval/golden_queries.json")

if not log_path.exists():
    print(f"❌ Log dry-run introuvable : {log_path}", file=sys.stderr)
    sys.exit(1)

log_text = log_path.read_text(encoding="utf-8")

# Parse les blocs "Top-10 IDs" depuis la sortie pytest (-s)
# Format : "  Top-10 IDs : [710, 478, ...]"  précédé de "[CASE_ID] ..."
pattern = re.compile(
    r"\[(?P<case_id>[A-Z0-9_]+)\].*?\n"   # ligne avec l'ID du cas
    r"(?:.*?\n)*?"                          # lignes intermédiaires (non-greedy)
    r"\s+Top-10 IDs\s*:\s*(?P<ids>\[[\d,\s]+\])",
    re.MULTILINE,
)

extracted: dict[str, list[int]] = {}
for m in pattern.finditer(log_text):
    case_id = m.group("case_id")
    ids = json.loads(m.group("ids"))
    extracted[case_id] = ids

if not extracted:
    print("⚠️  Aucun Top-10 ID parsé depuis le log. Vérifiez logs/rag_dryrun_raw.txt", file=sys.stderr)
    sys.exit(1)

data = json.loads(golden_path.read_text(encoding="utf-8"))
updated = 0
for case in data["cases"]:
    cid = case["id"]
    if cid in extracted:
        case["expected_user_ids"] = extracted[cid]
        print(f"  ✅ {cid} → {extracted[cid]}")
        updated += 1
    else:
        print(f"  ⚠️  {cid} → non trouvé dans le log (conservé tel quel)")

golden_path.write_text(
    json.dumps(data, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
print(f"\n✅ {updated}/{len(data['cases'])} cas mis à jour dans {golden_path}")
PYEOF

PATCH_EXIT=$?
if [ "$PATCH_EXIT" -ne 0 ]; then
  echo -e "${RED}❌ Échec du patch automatique — vérifiez logs/rag_dryrun_raw.txt${RESET}"
  exit 1
fi

echo ""

# ── ÉTAPE 3 : Validation automatique ─────────────────────────────────────────
echo -e "${CYAN}═══ ÉTAPE 3/3 — Validation finale (Recall@5) ═══════════════════${RESET}\n"

VALIDATE_EXIT=0
RAG_EVAL_BASE_URL="$RAG_EVAL_BASE_URL" \
RAG_EVAL_TOKEN="$RAG_EVAL_TOKEN" \
RAG_EVAL_DRY_RUN="false" \
RAG_EVAL_TOP_K="5" \
"$TEST_RUNNER" cv_api/eval/test_rag_quality.py -v --tb=short --no-header -W "ignore::DeprecationWarning:pythonjsonlogger" 2>&1 || VALIDATE_EXIT=$?

echo ""
if [ "$VALIDATE_EXIT" -eq 0 ]; then
  echo -e "${GREEN}✅ Calibrage validé — tous les cas passent !${RESET}"
  echo -e "${GREEN}   Activez l'éval post-déploiement :${RESET}"
  echo -e "${GREEN}   Pour relancer l'éval RAG seule (sans redéployer) :${RESET}"
  echo -e "${CYAN}   RAG_EVAL_BASE_URL=https://api.${ENV}.${BASE_DOMAIN}/api/cv \\"
  echo -e "   RAG_EVAL_TOKEN=\$TOKEN bash scripts/run_rag_eval.sh --env ${ENV}${RESET}"
  echo -e "${GREY}   (RAG_EVAL_ENABLED=true ./scripts/deploy.sh cv_api active l'éval automatique en CI/CD${RESET}"
  echo -e "${GREY}    mais nécessite un déploiement GCP complet — non adapté à une validation locale)${RESET}"
else
  echo -e "${YELLOW}⚠️  Certains cas échouent — Recall@5 < seuil${RESET}"
  echo -e "${GREY}   Les IDs injectés sont les top-10 bruts — tous pertinents ? Affinez min_recall_at_k.${RESET}"
  echo -e "${GREY}   Relancez : ./scripts/calibrate_rag.sh --env ${ENV}${RESET}"
fi

echo -e "\n${GREY}Rapport complet : ${REPORT_FILE}${RESET}\n"
