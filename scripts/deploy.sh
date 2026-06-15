#!/usr/bin/env bash
set -eo pipefail

# Configuration
PROJECT_ID="slavayssiere-sandbox-462015"
REGION="europe-west1"
REGISTRY="z-gcp-summit-services-dev"
FRONTEND_BUCKET="z-gcp-summit-frontend"

# Docker registry prefix
DOCKER_REPO="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REGISTRY}"

# Python Artifact Registry (zenika-shared-schemas wheels)
PYTHON_REPO="zenika-python"
PYTHON_REPO_URL="${REGION}-python.pkg.dev/${PROJECT_ID}/${PYTHON_REPO}"

# Python Command detection (prioritize virtualenv if present)
PYTHON_CMD="./test_env/bin/python3"
if [ ! -f "$PYTHON_CMD" ]; then
  PYTHON_CMD="python3"
fi

# Colors for Zenika Branding
RED='\033[0;31m'
GREY='\033[1;30m'
RESET='\033[0m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'

show_help() {
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
  echo "  --no-deploy        Construit et pousse les images Docker uniquement, ignore le déploiement Cloud Run"
  echo "  --force-all        Force le rebuild de TOUS les services (même ceux sans changement détecté)"
  echo "  --skip-tests       Bypasse la gate de tests unitaires (HOTFIX UNIQUEMENT — apparaîtra dans le summary)"
  echo "  --skip-perf        Bypasse le test de performance/charge Locust post-déploiement"
  echo ""
  echo "Tests:"
  echo "  Par défaut, tous les tests sont lancés : unitaires + intégration Testcontainers (nécessite Docker)."
  echo "  Les tests d'intégration sont dans tests/integration/ de chaque service."
  echo "  Ils démarrent des conteneurs Docker pour PostgreSQL, Redis et l'émulateur Pub/Sub."
  echo "  Docker doit être démarré — une vérification automatique bloque le build si indisponible."
  echo "  Utilisez --skip-tests pour bypasser tous les tests (unitaires + intégration) en mode hotfix."

  echo "Note: Par défaut, seuls les services ayant changé depuis leur dernier build sont reconstruits."
  echo "Note: Quand shared/ change, zenika-shared-schemas est automatiquement buildé, versionné et pushé sur Artifact Registry Python."
  echo "Note: sync_prompts est aussi exécuté automatiquement après tout déploiement."
  echo ""
  echo "Exemples:"
  echo "  $0 all minor"
  echo "  $0 users_api cv_api minor"
  echo "  $0 db_migrations"
}

# A8 — show_help() extraite en fonction propre (appelable aussi depuis d'autres contextes)
if [[ "$1" == "-h" || "$1" == "--help" ]]; then
  show_help
  exit 0
fi

# Déclaration des tableaux de suivi
DEPLOYS_SUCCESS=()
DEPLOYS_FAILED=()
DEPLOYS_SKIPPED=()
TESTS_SKIPPED=()  # Services dont les tests ont été bypassés via --skip-tests
CURRENT_DEPLOYING_SERVICE=""
SKIP_TESTS=false
SKIP_PERF=false
SKIP_UNCHANGED=true    # Défaut : rebuild uniquement ce qui a changé (opt-out via --force-all)
FORCE_ALL=false        # Rebuild tout, même si aucun changement détecté
declare -A COVERAGE_RESULTS   # service -> "75%" | "N/A" | "SKIPPED"

# Répertoire de logs par run — conservé après exécution pour debug
LOG_DIR="$(pwd)/deploy_logs/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$LOG_DIR"
ln -sfn "$LOG_DIR/deploy.log" "$(pwd)/deploy_logs/latest_deploy.log"
exec > >(tee -a "${LOG_DIR}/deploy.log") 2>&1

# Tableau global des fichiers temporaires — nettoyé par le trap EXIT/INT/TERM (P0/R3)
_TMPFILES=()
_cleanup_tmpfiles() { [ ${#_TMPFILES[@]} -gt 0 ] && rm -f "${_TMPFILES[@]}"; }
trap '_cleanup_tmpfiles' EXIT INT TERM

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

  if [ ${#TESTS_SKIPPED[@]} -gt 0 ]; then
    echo -e "${RED}🚨 ATTENTION — TESTS UNITAIRES BYPASSÉS (--skip-tests) :${RESET}"
    for svc in "${TESTS_SKIPPED[@]}"; do
      echo -e "   ⚠️  ${svc} (déployé SANS validation des tests)"
    done
    echo -e "${RED}   → Ces services doivent être re-déployés avec les tests dès que possible !${RESET}"
  fi

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
      if [[ "$svc" == *"Build error"* ]] || [[ "$svc" == *"Tests"* ]]; then
        build_failures+=("$svc")
      else
        deploy_failures+=("$svc")
      fi
    done

    if [ ${#build_failures[@]} -gt 0 ]; then
      echo -e "${RED}❌ ÉCHECS DE BUILD / TESTS (Docker/Local) :${RESET}"
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

  # ── Rapport de couverture des services rebuildés ──────────────────
  if [ ${#COVERAGE_RESULTS[@]} -gt 0 ]; then
    echo -e "${GREY}------------------------------------------------------------${RESET}"
    echo -e "📊 ${GREY}COUVERTURE DE TEST (services rebuildés)${RESET}"
    echo -e "${GREY}------------------------------------------------------------${RESET}"
    printf "   %-35s %s\n" "SERVICE" "COUVERTURE"
    printf "   %-35s %s\n" "-------" "----------"

    for svc in "${!COVERAGE_RESULTS[@]}"; do
      local cov="${COVERAGE_RESULTS[$svc]}"
      local cov_color="$RESET"
      local cov_icon="📊"
      local num
      num=$(echo "$cov" | tr -d '%❌ ')
      if [[ "$cov" == "SKIPPED" ]]; then
        cov_color="$YELLOW"; cov_icon="⏭️ "
      elif [[ "$cov" == "N/A" ]]; then
        cov_color="$GREY"; cov_icon="➖ "
      elif [[ "$num" =~ ^[0-9]+$ ]]; then
        if [ "$num" -ge 80 ]; then
          cov_color="$GREEN"; cov_icon="✅"
        elif [ "$num" -ge 50 ]; then
          cov_color="$YELLOW"; cov_icon="⚠️ "
        else
          cov_color="$RED"; cov_icon="❌"
        fi
      fi

      printf "   %-35s ${cov_color}%s %s${RESET}\n" "$svc" "$cov_icon" "$cov"
    done
  fi
  # ─────────────────────────────────────────────────────────────────────────────

  echo -e "${GREY}============================================================${RESET}\n"

  # ── Génération du fichier prompt Antigravity (enrichi) ──────────────────────
  local PROMPT_FILE="${LOG_DIR}/antigravity_prompt.md"
  local HAS_ERRORS=false

  # Contexte git (non bloquant)
  local GIT_BRANCH GIT_COMMIT GIT_MSG
  GIT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
  GIT_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
  GIT_MSG=$(git log -1 --pretty=format:"%s" 2>/dev/null || echo "unknown")

  # Durée totale du run
  local RUN_DURATION=$(( SECONDS ))
  local RUN_MIN=$(( RUN_DURATION / 60 ))
  local RUN_SEC=$(( RUN_DURATION % 60 ))

  {
    set +e  # Désactiver fail-fast dans le bloc rapport — les greps/diffs peuvent retourner 1
    echo "# 🚀 Rapport de déploiement Antigravity — $(date '+%Y-%m-%d %H:%M')"
    echo ""
    echo "> **Instructions pour Antigravity** : Ce rapport est généré automatiquement après \`./scripts/deploy.sh\`."
    echo "> Lis-le intégralement avant de proposer un diagnostic. Les sections sont ordonnées du plus important au moins important."
    echo ""

    # ── Section 1 : Contexte opérationnel ──────────────────────────────────────
    echo "## 📋 Contexte opérationnel"
    echo ""
    echo "| Champ | Valeur |"
    echo "|---|---|"
    echo "| **Date / heure** | $(date '+%Y-%m-%d %H:%M:%S %Z') |"
    echo "| **Durée totale** | ${RUN_MIN}m ${RUN_SEC}s |"
    echo "| **Branche git** | \`${GIT_BRANCH}\` |"
    echo "| **Commit** | \`${GIT_COMMIT}\` — ${GIT_MSG} |"
    echo "| **Répertoire logs** | \`${LOG_DIR}/\` |"
    echo "| **Tests bypassés** | ${SKIP_TESTS} |"
    echo "| **PROJECT_ID** | ${PROJECT_ID} |"
    echo "| **REGION** | ${REGION} |"
    echo ""

    if [ "$SKIP_TESTS" = true ]; then
      echo "> ⚠️ **ATTENTION — HOTFIX** : Les tests unitaires ont été bypassés via \`--skip-tests\`."
      echo "> Les services déployés n'ont PAS été validés par les tests. Vérifier manuellement avant de clore le ticket."
      echo ""
    fi

    # ── Section 2 : Résumé des services ────────────────────────────────────────
    echo "## 🗂️ Résumé des services"
    echo ""

    if [ ${#DEPLOYS_SUCCESS[@]} -gt 0 ]; then
      echo "### ✅ Déployés avec succès"
      echo ""
      echo "| Service | Version | Couverture |"
      echo "|---|---|---|"
      for svc in "${DEPLOYS_SUCCESS[@]}"; do
        local svc_key ver cov
        svc_key=$(echo "$svc" | awk '{print $1}')
        ver="N/A"
        [ -f "${svc_key}/VERSION" ] && ver=$(cat "${svc_key}/VERSION")
        cov="${COVERAGE_RESULTS[$svc_key]:-N/A}"
        echo "| \`${svc_key}\` | ${ver} | ${cov} |"
      done
      echo ""
    fi

    if [ ${#DEPLOYS_SKIPPED[@]} -gt 0 ]; then
      echo "### ⏭️ Skippés (aucun changement détecté)"
      echo ""
      echo "| Service | Version actuelle |"
      echo "|---|---|"
      for svc in "${DEPLOYS_SKIPPED[@]}"; do
        local svc_key ver
        svc_key=$(echo "$svc" | awk '{print $1}')
        ver="N/A"
        [ -f "${svc_key}/VERSION" ] && ver=$(cat "${svc_key}/VERSION")
        echo "| \`${svc_key}\` | ${ver} |"
      done
      echo ""
      echo "> ℹ️ Les services skippés utilisent leur **version précédemment déployée**."
      echo "> Ne pas diagnostiquer leurs comportements sur la base du code local si ce n'est pas la même version."
      echo ""
    fi

    if [ ${#DEPLOYS_FAILED[@]} -gt 0 ]; then
      echo "### ❌ Échecs"
      echo ""
      echo "| Service | Raison |"
      echo "|---|---|"
      for svc in "${DEPLOYS_FAILED[@]}"; do
        echo "| \`${svc}\` | Voir section détaillée ci-dessous |"
      done
      echo ""
    fi

    # ── Section 3 : Détail des erreurs de tests ─────────────────────────────────
    local found_any_test_error=false
    for f in "${LOG_DIR}"/*_tests.log; do
      [ -f "$f" ] || continue
      local svc_name
      svc_name=$(basename "$f" _tests.log)
      local errors
      errors=$(grep -E 'ERROR|FAILED|Error|Exception|NameError|ImportError|assert|XFAIL' "$f" \
        | grep -v 'DeprecationWarning\|pythonjsonlogger\|HTTP Request Failed\|exc_info\|warnings.warn\|PytestUnraisable\|ConnectionError\|opentelemetry\|ServiceUnavailable\|_InactiveRpcError\|ValueError' \
        | grep -v 'Logging error\|Failed to export\|grpc_status\|grpc_message\|StatusCode\|localhost:4317\|OTLP\|BatchExport\|Call stack' \
        | grep -v '_log(ERROR\|logger\.error\|logger\.warning\|self\._log' \
        | head -50)


      if [ -n "$errors" ]; then
        HAS_ERRORS=true
        found_any_test_error=true
        echo "## ❌ Détail échec tests : \`${svc_name}\`"
        echo ""
        echo "### Lignes d'erreur filtrées"
        echo '```text'
        echo "$errors"
        echo '```'
        echo ""
        echo "### Résumé pytest (fin du log)"
        echo '```text'
        tail -30 "$f"
        echo '```'
        echo ""
        # Stack trace complet du premier FAILED (jusqu'à 60 lignes)
        local first_failed_line
        first_failed_line=$(grep -n "^FAILED\|^_ FAILED\|AssertionError\|raise " "$f" | head -1 | cut -d: -f1)
        if [ -n "$first_failed_line" ]; then
          local ctx_start=$(( first_failed_line > 20 ? first_failed_line - 20 : 1 ))
          echo "### Stack trace (contexte autour de la première erreur)"
          echo '```text'
          sed -n "${ctx_start},$((first_failed_line + 40))p" "$f"
          echo '```'
          echo ""
        fi
        # Commandes MCP pour investiguer en production
        local cr_name="${svc_name//_/-}-dev"
        echo "### 🔍 Commandes MCP pour investiguer \`${svc_name}\`"
        echo ""
        echo "\`\`\`bash"
        echo "# Logs Cloud Run récents du service"
        echo "python3 scripts/mcp_cli.py errors --hours 2 --service ${cr_name}"
        echo ""
        echo "# Health check"
        echo "python3 scripts/mcp_cli.py health"
        echo ""
        echo "# Logs complets du run local"
        echo "cat ${LOG_DIR}/${svc_name}_tests.log | grep -A 20 'FAILED\|AssertionError'"
        echo "\`\`\`"
        echo ""
        echo "---"
        echo ""
      fi
    done

    if [ "$found_any_test_error" = false ]; then
      # Section 3 vide → indiquer succès
      echo "## ✅ Tests"
      echo ""
      echo "Tous les services rebuilds ont passé leurs tests unitaires."
      echo ""
    fi

    # ── Section 4 : Table de couverture ────────────────────────────────────────
    if [ ${#COVERAGE_RESULTS[@]} -gt 0 ]; then
      echo "## 📊 Couverture de tests"
      echo ""
      echo "| Service | Couverture | État |"
      echo "|---|---|---|"
      for svc in "${!COVERAGE_RESULTS[@]}"; do
        local cov="${COVERAGE_RESULTS[$svc]}"
        local icon="📊"
        local num
        num=$(echo "$cov" | tr -d '%❌ SKIPPED NA/A ')
        if [[ "$cov" == "SKIPPED" ]]; then icon="⏭️"
        elif [[ "$cov" == "N/A" ]]; then icon="➖"
        elif [[ "$num" =~ ^[0-9]+$ ]]; then
          [ "$num" -ge 80 ] && icon="✅" || { [ "$num" -ge 50 ] && icon="⚠️" || icon="❌"; }
        fi
        echo "| \`${svc}\` | ${cov} | ${icon} |"
      done
      echo ""
    fi

    # ── Section 5 : Prochaines étapes recommandées ──────────────────────────────
    echo "## 🎯 Prochaines étapes recommandées pour Antigravity"
    echo ""
    if [ "$HAS_ERRORS" = true ]; then
      echo "1. **Identifier la cause racine** dans les stack traces de la section 3"
      echo "2. **Chercher en mémoire** : \`mcp_antigravity-memory_search_past_errors(query=\"<service> <type d'erreur>\")\`"
      echo "3. **Investiguer Cloud Run** si l'erreur est runtime : \`python3 scripts/mcp_cli.py errors --hours 2\`"
      echo "4. **Proposer un fix** et lister les fichiers à modifier"
      echo "5. **Mémoriser la solution** après correction : \`mcp_antigravity-memory_log_error_and_solution(...)\`"
    else
      echo "1. Le déploiement est un succès — vérifier les services en production si nécessaire"
      echo "2. \`python3 scripts/mcp_cli.py health\` pour un health check global"
      echo "3. Si une régression est observée en prod, lire les logs : \`python3 scripts/mcp_cli.py errors --hours 1\`"
    fi
    echo ""
    echo "---"
    echo "*Rapport généré par \`scripts/deploy.sh\` — $(date '+%Y-%m-%dT%H:%M:%SZ')*"
  } > "$PROMPT_FILE"
  set -e  # Réactiver fail-fast après la génération du rapport

  # Affichage terminal
  if [ "$HAS_ERRORS" = true ]; then
    echo -e "${RED}\n📋 Rapport Antigravity généré (avec erreurs) :${RESET}"
    echo -e "${GREY}   Fichier : ${PROMPT_FILE}${RESET}"
    echo -e "${GREY}   Commande : cat ${PROMPT_FILE}${RESET}\n"
    [ -f "$PROMPT_FILE" ] && cat "$PROMPT_FILE"
  else
    echo -e "${GREEN}\n📝 Rapport Antigravity généré (tout OK) : ${PROMPT_FILE}${RESET}"
  fi
  # ──────────────────────────────────────────────────────────────────────────────

  # ── Génération de last_deploy.json (état courant lisible par Antigravity) ────
  local LAST_DEPLOY_FILE="./deploy_logs/last_deploy.json"
  local OVERALL_STATUS="success"
  [ ${#DEPLOYS_FAILED[@]} -gt 0 ] && OVERALL_STATUS="failure"
  [ "$HAS_ERRORS" = true ] && OVERALL_STATUS="failure"

  # Sérialise les tableaux bash en JSON array (jq-free)
  local success_json="["
  for s in "${DEPLOYS_SUCCESS[@]}"; do
    # Lire la version si disponible
    local svc_key
    svc_key=$(echo "$s" | awk '{print $1}')
    local ver=""
    [ -f "${svc_key}/VERSION" ] && ver=$(cat "${svc_key}/VERSION")
    success_json+="\"${s} ${ver}\","
  done
  success_json="${success_json%,}]"

  local failed_json="["
  for s in "${DEPLOYS_FAILED[@]}"; do failed_json+="\"${s}\","; done
  failed_json="${failed_json%,}]"

  local skipped_json="["
  for s in "${DEPLOYS_SKIPPED[@]}"; do
    local svc_key
    svc_key=$(echo "$s" | awk '{print $1}')
    local ver=""
    [ -f "${svc_key}/VERSION" ] && ver=$(cat "${svc_key}/VERSION")
    skipped_json+="\"${s} ${ver}\","; done
  skipped_json="${skipped_json%,}]"

  cat > "$LAST_DEPLOY_FILE" <<JSON
{
  "timestamp": "$(date -u '+%Y-%m-%dT%H:%M:%SZ')",
  "run_dir": "${LOG_DIR}",
  "overall_status": "${OVERALL_STATUS}",
  "skip_tests": ${SKIP_TESTS},
  "deployed": ${success_json},
  "failed": ${failed_json},
  "skipped": ${skipped_json},
  "antigravity_prompt": "${PROMPT_FILE}",
  "how_to_read": "cat deploy_logs/last_deploy.json | python3 -m json.tool"
}
JSON
  echo -e "${GREY}📊 État sauvegardé : ${LAST_DEPLOY_FILE}${RESET}"
  # ──────────────────────────────────────────────────────────────────────────────

  exit $exit_code
}

trap 'print_summary; _cleanup_tmpfiles' EXIT

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
  if [[ "$SERVICE" == "agent_"* ]]; then
    DIRS_TO_CHECK+=("./agent_commons")
  fi
  # shared/ est inclus dans le hash des services backend Python uniquement.
  # Les services non-Python (db_migrations, db_init) ne dépendent pas de shared/
  # et ne doivent pas être invalidés par des changements dans shared/.
  local SHARED_EXEMPT_SERVICES=("frontend" "db_migrations" "db_init")
  local is_exempt=false
  for exempt in "${SHARED_EXEMPT_SERVICES[@]}"; do
    if [ "$SERVICE" == "$exempt" ]; then
      is_exempt=true
      break
    fi
  done
  if [ -d "./shared" ] && [ "$is_exempt" = false ]; then
    DIRS_TO_CHECK+=("./shared")
  fi

  # Compute a SHA1 hash of all files in the relevant directories
  # Exclude VERSION and HASH files, and common ignore paths
  find "${DIRS_TO_CHECK[@]}" -type f \
    ! -name "VERSION" ! -name "HASH" ! -name "FILE_HASHES" \
    ! -name ".coverage" ! -name "coverage.json" ! -name "coverage.xml" ! -name "coverage_output.txt" ! -name "pytest.log" \
    ! -name "*.db" ! -name "*.pyc" ! -name "*.md" \
    ! -path "*/__pycache__/*" ! -path "*/.pytest_cache/*" \
    ! -path "*/.venv*/*" ! -path "*/venv*/*" ! -path "*/env*/*" ! -path "*/test_env*/*" ! -path "*/node_modules/*" \
    ! -path "*/dist/*" ! -path "*/build/*" ! -path "*/.DS_Store" ! -path "*/.hypothesis/*" \
    ! -path "*/htmlcov/*" ! -path "*/test_data/*" ! -path "*/tests/data/*" ! -path "*/tests/mock_data/*" \
    ! -path "*/coverage/*" ! -path "*/.nyc_output/*" \
    ! -path "*/*.egg-info/*" \
    -exec shasum {} + | sort > "/tmp/hash_${SERVICE}"

  shasum "/tmp/hash_${SERVICE}" | awk '{print $1}'
}

save_service_hash() {
  local SERVICE=$1
  compute_service_hash "$SERVICE" > "${SERVICE}/HASH"
  cp "/tmp/hash_${SERVICE}" "${SERVICE}/FILE_HASHES"
}

save_shared_hash() {
  # Sauvegarde le hash de shared/ uniquement une fois que tous les consumers
  # ont été buildés avec succès. Tant qu'un build échoue, shared/HASH reste
  # à l'ancienne valeur → le prochain run re-déclenchera le rebuild complet.
  if [ -d "./shared" ]; then
    find "./shared" -type f \
      ! -name "HASH" ! -name "FILE_HASHES" ! -name "VERSION" \
      ! -name ".coverage" ! -name "coverage.json" ! -name "coverage.xml" ! -name "coverage_output.txt" ! -name "pytest.log" \
      ! -name "*.db" ! -name "*.pyc" ! -name "*.md" \
      ! -path "*/__pycache__/*" ! -path "*/.pytest_cache/*" \
      ! -path "*/.venv*/*" ! -path "*/venv*/*" ! -path "*/env*/*" ! -path "*/test_env*/*" ! -path "*/node_modules/*" \
      ! -path "*/dist/*" ! -path "*/build/*" ! -path "*/.DS_Store" ! -path "*/.hypothesis/*" \
      ! -path "*/htmlcov/*" ! -path "*/test_data/*" ! -path "*/tests/data/*" ! -path "*/tests/mock_data/*" \
      ! -path "*/*.egg-info/*" \
      -exec shasum {} + | sort > "shared/FILE_HASHES"
    shasum "shared/FILE_HASHES" | awk '{print $1}' > "shared/HASH"
  fi
}

check_shared_changed() {
  # Retourne 0 (true) si shared/ a changé depuis le dernier build réussi
  local SHARED_HASH_FILE="shared/HASH"
  [ ! -d "./shared" ] && return 1           # Pas de dossier shared/ → rien à vérifier
  [ ! -f "$SHARED_HASH_FILE" ] && return 0  # Pas de HASH → nouveau → changed
  local SAVED
  SAVED=$(cat "$SHARED_HASH_FILE")
  local CURRENT
  find "./shared" -type f \
    ! -name "HASH" ! -name "FILE_HASHES" ! -name "VERSION" \
    ! -name ".coverage" ! -name "coverage.json" ! -name "coverage.xml" ! -name "coverage_output.txt" ! -name "pytest.log" \
    ! -name "*.db" ! -name "*.pyc" ! -name "*.md" \
    ! -path "*/__pycache__/*" ! -path "*/.pytest_cache/*" \
    ! -path "*/.venv*/*" ! -path "*/venv*/*" ! -path "*/env*/*" ! -path "*/test_env*/*" ! -path "*/node_modules/*" \
    ! -path "*/dist/*" ! -path "*/build/*" ! -path "*/.DS_Store" ! -path "*/.hypothesis/*" \
    ! -path "*/htmlcov/*" ! -path "*/test_data/*" ! -path "*/tests/data/*" ! -path "*/tests/mock_data/*" \
    ! -path "*/*.egg-info/*" \
    -exec shasum {} + | sort > "/tmp/current_shared_hashes"
  CURRENT=$(shasum "/tmp/current_shared_hashes" | awk '{print $1}')
  
  if [ "$SAVED" != "$CURRENT" ]; then
    return 0 # changed
  else
    return 1 # not changed
  fi
}

audit_mock_configs() {
  echo -e "\n${GREY}--- 🛡️  Audit de securite des variables de Mocking Gemini ---${RESET}"
  local audit_failed=0

  # 1. Verification des fichiers d'environnement dans platform-engineering/envs/
  if [ -d "platform-engineering/envs" ]; then
    for env_file in platform-engineering/envs/*.yaml; do
      [ ! -f "$env_file" ] && continue
      local match_gemini
      match_gemini=$(grep -E "GEMINI_API_BASE_URL" "$env_file" | grep -v '""' | grep -v "''" || true)
      local match_vertex
      match_vertex=$(grep -E "VERTEX_API_BASE_URL" "$env_file" | grep -v '""' | grep -v "''" || true)
      
      if [ -n "$match_gemini" ] || [ -n "$match_vertex" ]; then
        echo -e "${RED}❌ ERREUR AUDIT : Valeur de mock non vide detectee dans $(basename "$env_file") :${RESET}"
        [ -n "$match_gemini" ] && echo -e "   -> $match_gemini"
        [ -n "$match_vertex" ] && echo -e "   -> $match_vertex"
        audit_failed=1
      fi
    done
  fi

  # 2. Verification des fichiers Terraform (cr_*.tf)
  if [ -d "platform-engineering/terraform" ]; then
    for tf_file in platform-engineering/terraform/cr_*.tf; do
      [ ! -f "$tf_file" ] && continue
      local bad_lines
      bad_lines=$(grep -A 1 -E "GEMINI_API_BASE_URL|VERTEX_API_BASE_URL" "$tf_file" | grep "value" | grep -E "mock_gemini|localhost|127.0.0.1" || true)
      if [ -n "$bad_lines" ]; then
        echo -e "${RED}❌ ERREUR AUDIT : Configuration locale detectee dans Terraform $(basename "$tf_file") :${RESET}"
        echo -e "   -> $bad_lines"
        audit_failed=1
      fi
    done
  fi

  if [ "$audit_failed" -eq 1 ]; then
    echo -e "${RED}❌ L'audit a echoue. Le deploiement est bloque pour proteger la production.${RESET}\n"
    exit 1
  else
    echo -e "${GREEN}✅ Audit de securite reussi : aucun mock Gemini configure pour la production.${RESET}\n"
  fi
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
    if [ -f "${SERVICE}/FILE_HASHES" ]; then
      echo -e "${GREY}   Détails des changements pour $SERVICE :${RESET}"
      diff "${SERVICE}/FILE_HASHES" "/tmp/hash_${SERVICE}" | grep -E '^[<>]' | sed 's/^< /   [-] (Ancien) /; s/^> /   [+] (Nouveau) /' | awk '{print $1, $2, $4}' || true
      echo ""
    else
      echo -e "${GREY}   (Détails non disponibles ce coup-ci, initialisation du tracking...)${RESET}"
      echo ""
    fi
    return 0 # Changements détectés
  fi
}

# ==============================================================================
# Docker Availability Check (prérequis Testcontainers)
# ==============================================================================

check_docker_available() {
  # Vérifie que le démon Docker est accessible.
  # Testcontainers l'exige pour les tests d'intégration (postgres, redis).
  if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}❌ [DOCKER] Démon Docker non disponible.${RESET}"
    echo -e "${RED}   Les tests d'intégration (Testcontainers) ne peuvent pas s'exécuter.${RESET}"
    echo -e "${RED}   → Démarrez Docker Desktop avant de relancer deploy.sh.${RESET}"
    exit 1
  fi
  echo -e "${GREEN}✅ [DOCKER] Démon disponible — tests d'intégration activés.${RESET}"
}

# ==============================================================================
# Push resilient vers Artifact Registry (retry + timeout)
# ==============================================================================
#
# push_with_retry <image>
#   Tente jusqu'à PUSH_MAX_RETRIES fois (défaut 3) avec un timeout de
#   PUSH_TIMEOUT secondes (défaut 300) par tentative.
#   Entre chaque tentative : backoff exponentiel (15s → 30s) + refresh
#   du token gcloud pour ne pas échouer sur un token expiré.
#
#   Pourquoi : docker push n'a pas de timeout intégré. Un blocage réseau
#   idle (VPN, Wi-Fi instable) suspend le process indéfiniment, forçant
#   une relance complète de deploy.sh.

push_with_retry() {
  local image="$1"
  local max_attempts="${PUSH_MAX_RETRIES:-3}"
  local push_timeout="${PUSH_TIMEOUT:-300}"
  local attempt=0

  while [ $attempt -lt $max_attempts ]; do
    attempt=$((attempt + 1))
    echo -e "  → [Push] Tentative $attempt/$max_attempts : $image"

    local push_cmd=("docker" "push" "$image")
    if command -v timeout >/dev/null 2>&1; then
      push_cmd=("timeout" "$push_timeout" "${push_cmd[@]}")
    elif command -v gtimeout >/dev/null 2>&1; then
      push_cmd=("gtimeout" "$push_timeout" "${push_cmd[@]}")
    fi

    local exit_code=0
    if "${push_cmd[@]}"; then
      echo -e "  ${GREEN}✅ [Push] Succès : $image${RESET}"
      return 0
    else
      exit_code=$?
    fi
    if [ $attempt -lt $max_attempts ]; then
      local wait_time=$(( attempt * 15 ))
      if [ $exit_code -eq 124 ]; then
        echo -e "  ${YELLOW}⚠️  [Push] Timeout (${push_timeout}s dépassé) — retry dans ${wait_time}s...${RESET}"
      else
        echo -e "  ${YELLOW}⚠️  [Push] Échec (exit $exit_code) — retry dans ${wait_time}s...${RESET}"
      fi
      sleep "$wait_time"
      # Rafraîchit les credentials AR avant la prochaine tentative
      # (le token gcloud expire après 1h, un long build peut l'invalider)
      echo -e "  ${GREY}[Push] Rafraîchissement des credentials gcloud...${RESET}"
      gcloud auth configure-docker europe-west1-docker.pkg.dev --quiet 2>/dev/null || true
    fi
  done

  echo -e "  ${RED}❌ [Push] Échec après $max_attempts tentatives : $image${RESET}"
  return 1
}

# ==============================================================================
# Test Gate (fail-fast avant chaque docker build)
# ==============================================================================

run_service_tests() {
  local SERVICE=$1
  local TEST_RUNNER="./test_env/bin/pytest"

  # Bypass explicite via --skip-tests
  if [ "$SKIP_TESTS" = true ]; then
    echo -e "${YELLOW}[⚠️  TESTS SKIPPED] $SERVICE — bypass via --skip-tests (hotfix uniquement !)${RESET}"
    TESTS_SKIPPED+=("$SERVICE")
    return 0
  fi

  # Vérification de la présence de uv
  if ! command -v uv >/dev/null 2>&1; then
    echo -e "${YELLOW}[⚠️  SKIP TESTS] uv introuvable pour $SERVICE.${RESET}"
    echo -e "${YELLOW}   → Installez uv : curl -LsSf https://astral.sh/uv/install.sh | sh${RESET}"
    echo -e "${YELLOW}   → Build autorisé sans validation des tests.${RESET}"
    return 0
  fi

  # Détection des fichiers de test
  local HAS_TESTS=false
  if find "./${SERVICE}/tests" -name 'test_*.py' 2>/dev/null | grep -q .; then
    HAS_TESTS=true
  elif find "./${SERVICE}" -maxdepth 1 -name 'test_*.py' 2>/dev/null | grep -q .; then
    HAS_TESTS=true
  fi

  if [ "$HAS_TESTS" = false ]; then
    echo -e "${GREY}[ℹ️  NO TESTS] Aucun test trouvé pour $SERVICE — build autorisé.${RESET}"
    return 0
  fi

  echo -e "${RED}--- 🧪 Tests unitaires + couverture : $SERVICE ---${RESET}"

  # PYTHONPATH : racine du monorepo (pour shared/) + dossier du service
  # Les agents ajoutent aussi agent_commons
  local PYTHONPATH_VAL=".:${SERVICE}"
  if [[ "$SERVICE" == "agent_"* ]]; then
    PYTHONPATH_VAL=".:${SERVICE}:./agent_commons:./agent_commons/agent_commons"
  fi


  # Fichier temporaire pour capturer la sortie pytest (nécessaire pour parser la couverture)
  # Enregistré dans _TMPFILES pour nettoyage garanti même en cas de SIGINT/SIGTERM (P0/R3)
  local TMP_OUTPUT
  TMP_OUTPUT=$(mktemp)
  _TMPFILES+=("$TMP_OUTPUT")

  local PYTEST_EXIT=0
  echo -e "${GREY}   (Exécution des tests en cours...)${RESET}"
  OTEL_TRACES_EXPORTER=none \
  OTEL_METRICS_EXPORTER=none \
  OTEL_LOGS_EXPORTER=none \
  SECRET_KEY="testsecret" \
  PYTHONPATH="$PYTHONPATH_VAL" \
  uv run --project "./${SERVICE}" --with-requirements scripts/test_requirements.txt pytest "./${SERVICE}" -x \
    --cov="./${SERVICE}" --cov-report=term-missing:skip-covered \
    2>&1 | tee "$TMP_OUTPUT" | grep --line-buffered -E "(test_.*\.py|\[[ 0-9]+%\]|===.*===|^FAILED|^ERROR)" | awk '{print "   " $0; fflush()}' || PYTEST_EXIT=${PIPESTATUS[0]}

  # Écriture dans le log persistant (jamais cat direct — évite la verbosité terminal)
  local LOG_FILE="${LOG_DIR}/${SERVICE}_tests.log"
  cat "$TMP_OUTPUT" > "$LOG_FILE"

  # Extraire le % total depuis la ligne "TOTAL   ...   75%"
  local COV_PCT
  COV_PCT=$(grep -E '^TOTAL' "$TMP_OUTPUT" | awk '{print $NF}' | tail -1)
  # Pas de rm -f manuel : nettoyage délégué au trap global _cleanup_tmpfiles (P0/R3)

  if [ "$PYTEST_EXIT" -eq 0 ]; then
    COVERAGE_RESULTS["$SERVICE"]="${COV_PCT:-N/A}"
    echo -e "${GREEN}✅ Tests $SERVICE : OK (couverture: ${COV_PCT:-N/A}) — build autorisé${RESET}"
    return 0
  else
    COVERAGE_RESULTS["$SERVICE"]="${COV_PCT:-N/A} ❌"
    echo -e "${RED}❌ Tests $SERVICE : ÉCHEC — build bloqué (fail-fast)${RESET}"
    echo -e "${RED}   → Détails : ${LOG_FILE}${RESET}"
    DEPLOYS_FAILED+=("$SERVICE (Tests échoués)")
    return 1
  fi
}

# ==============================================================================
# ==============================================================================
# Deployment Logic
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
  local MODE=${3:-"both"}

  local IMAGE_NAME="${DOCKER_REPO}/${SERVICE}"
  local TAG

  if [[ "$MODE" == "build" || "$MODE" == "both" ]]; then
    if [ "$SKIP_UNCHANGED" = true ] && ! has_changes "$SERVICE"; then
      echo -e "${YELLOW}--- Skipped $SERVICE (no changes detected since last deployment) ---${RESET}"
      DEPLOYS_SKIPPED+=("$SERVICE")
      return 0
    fi

    # ── Vérification Docker (prérequis Testcontainers) ────────────────────────────────────
    check_docker_available

    # ── Gate de test fail-fast ──────────────────────────────────────────────────
    # CURRENT_DEPLOYING_SERVICE vidé avant return 1 pour éviter la double entrée
    # dans DEPLOYS_FAILED via le trap EXIT (P0/R4)
    run_service_tests "$SERVICE" || { CURRENT_DEPLOYING_SERVICE=""; return 1; }

    TAG=$(get_service_tag "$SERVICE" "$BUMP")
    echo "--- Building $SERVICE ($TAG) ---"

    # Build pour Cloud Run (nécessite amd64) — contexte = racine du monorepo
    # BuildKit requis pour --secret (token AR non visible dans docker history)
    # Le token est éphémère (1h) et jamais persisté dans l'image
    local AR_TOKEN
    AR_TOKEN=$(gcloud auth print-access-token)
    local AR_TOKEN_FILE
    AR_TOKEN_FILE=$(mktemp)
    _TMPFILES+=("$AR_TOKEN_FILE")
    echo -n "$AR_TOKEN" > "$AR_TOKEN_FILE"

    local SHARED_VERSION_RAW=$(cat shared/VERSION 2>/dev/null || echo "latest")
    local SHARED_VERSION="${SHARED_VERSION_RAW#v}"

    DOCKER_BUILDKIT=1 docker build --platform linux/amd64 \
      --secret id=ar_token,src="$AR_TOKEN_FILE" \
      --build-arg PYTHON_AR_REPO="${PYTHON_REPO_URL}" \
      --build-arg SHARED_VERSION="${SHARED_VERSION}" \
      -t "${IMAGE_NAME}:${TAG}" -t "${IMAGE_NAME}:latest" \
      -f "./${SERVICE}/Dockerfile" .

    # Bridging tag for Compose local name
    echo "--- Tagging for Compose: test-open-code-${SERVICE}:latest ---"
    docker tag "${IMAGE_NAME}:latest" "test-open-code-${SERVICE}:latest"
    
    echo "--- Smoke Test: Vérification du démarrage du conteneur ---"
    if [ "$SERVICE" == "db_migrations" ]; then
      echo -e "${GREEN}✅ [SMOKE TEST] Ignoré pour $SERVICE (Job d'exécution courte).${RESET}"
    else
      local PORT_EXPOSED=8080
      case "$SERVICE" in
        users_api|prompts_api) PORT_EXPOSED=8000 ;;
        items_api) PORT_EXPOSED=8001 ;;
        competencies_api) PORT_EXPOSED=8003 ;;
        cv_api) PORT_EXPOSED=8004 ;;
        drive_api) PORT_EXPOSED=8006 ;;
        missions_api) PORT_EXPOSED=8009 ;;
        *) PORT_EXPOSED=8080 ;;
      esac

      local SMOKE_CONTAINER="smoke_${SERVICE}_$RANDOM"
      
      docker run -d --name "$SMOKE_CONTAINER" \
        -p 0:"$PORT_EXPOSED" \
        -e SECRET_KEY="smoke_test_key" \
        -e GEMINI_API_KEY="dummy" \
        -e REDIS_URL="redis://localhost:6379" \
        -e DATABASE_URL="postgresql+asyncpg://dummy:dummy@localhost:5432/dummy" \
        "${IMAGE_NAME}:${TAG}" >/dev/null
        
      # Extraction du port dynamique hôte affecté par Docker
      # sleep 1 : laisse Docker enregistrer le mapping avant d'appeler docker port
      sleep 1
      local HOST_PORT
      HOST_PORT=$(docker port "$SMOKE_CONTAINER" "$PORT_EXPOSED" 2>/dev/null | awk -F: '{print $NF}' | tr -d '[:space:]')

      # Fallback : docker inspect si docker port échoue (container crashé trop vite ou mapping non encore enregistré)
      if [ -z "$HOST_PORT" ]; then
        HOST_PORT=$(docker inspect --format="{{(index (index .NetworkSettings.Ports \"${PORT_EXPOSED}/tcp\") 0).HostPort}}" "$SMOKE_CONTAINER" 2>/dev/null | tr -d '[:space:]')
      fi

      if [ -z "$HOST_PORT" ] || [ "$HOST_PORT" = "<no value>" ]; then
        echo -e "${RED}❌ [SMOKE TEST] Impossible de récupérer le port dynamique affecté par Docker !${RESET}"
        docker logs "$SMOKE_CONTAINER" 2>&1 | tee -a "${LOG_DIR}/${SERVICE}_tests.log"
        docker rm -f "$SMOKE_CONTAINER" >/dev/null
        DEPLOYS_FAILED+=("$SERVICE (Smoke Test dynamic port mapping failed)")
        CURRENT_DEPLOYING_SERVICE=""
        return 1
      fi


      # Active HTTP probe loop (max 30s)
      local SUCCESS=false
      local ELAPSED=0
      
      local SERVICE_ROOT_PATH=""
      case "$SERVICE" in
        drive_api) SERVICE_ROOT_PATH="/drive-api" ;;
        missions_api) SERVICE_ROOT_PATH="/missions-api" ;;
        users_api) SERVICE_ROOT_PATH="/users-api" ;;
        items_api) SERVICE_ROOT_PATH="/items-api" ;;
        competencies_api) SERVICE_ROOT_PATH="/competencies-api" ;;
        cv_api) SERVICE_ROOT_PATH="/cv-api" ;;
        prompts_api) SERVICE_ROOT_PATH="/prompts-api" ;;
        analytics_mcp) SERVICE_ROOT_PATH="/analytics-mcp" ;;
        monitoring_mcp) SERVICE_ROOT_PATH="/monitoring-mcp" ;;
      esac

      echo -e "${GREY}[*] Port dynamique mappé : ${HOST_PORT}. Lancement de la boucle de sondes actives (max 30s)...${RESET}"
      while [ $ELAPSED -lt 30 ]; do
        if ! docker ps -q -f name="^${SMOKE_CONTAINER}$" | grep -q .; then
          echo -e "${RED}❌ [SMOKE TEST] Le conteneur a crashé au démarrage pendant le probing !${RESET}"
          break
        fi
        
        local HTTP_STATUS="000"
        
        # 1. Probe /health
        HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 1 "http://localhost:${HOST_PORT}/health" || echo "000")
        
        # 2. Probe /${ROOT_PATH}/health
        if [[ "$HTTP_STATUS" == "000" || "$HTTP_STATUS" == "404" ]]; then
          if [ -n "$SERVICE_ROOT_PATH" ]; then
            local CLEAN_ROOT
            CLEAN_ROOT=$(echo "$SERVICE_ROOT_PATH" | sed 's/^\///')
            HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 1 "http://localhost:${HOST_PORT}/${CLEAN_ROOT}/health" || echo "000")
          fi
        fi
        
        # 3. Probe root /
        if [[ "$HTTP_STATUS" == "000" || "$HTTP_STATUS" == "404" ]]; then
          HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 1 "http://localhost:${HOST_PORT}/" || echo "000")
        fi
        
        if [[ "$HTTP_STATUS" != "000" ]]; then
          SUCCESS=true
          break
        fi
        
        sleep 1
        ELAPSED=$((ELAPSED + 1))
      done

      if [ "$SUCCESS" = false ]; then
        echo -e "${RED}❌ [SMOKE TEST] L'image Docker n'a pas répondu aux sondes HTTP dans les 30s ou a crashé !${RESET}"
        echo -e "${RED}   Logs du conteneur :${RESET}"
        docker logs "$SMOKE_CONTAINER" 2>&1 | tee -a "${LOG_DIR}/${SERVICE}_tests.log"
        docker rm -f "$SMOKE_CONTAINER" >/dev/null
        DEPLOYS_FAILED+=("$SERVICE (Smoke Test failed)")
        CURRENT_DEPLOYING_SERVICE=""
        return 1
      fi
      
      echo -e "${GREEN}✅ [SMOKE TEST] Démarrage et boucle de sondes validés avec succès (statut HTTP: ${HTTP_STATUS}).${RESET}"
      docker rm -f "$SMOKE_CONTAINER" >/dev/null
    fi
  fi

  if [[ "$MODE" == "deploy" || "$MODE" == "both" ]]; then
    if [[ " ${DEPLOYS_SKIPPED[*]} " == *" $SERVICE "* ]]; then
      return 0
    fi

    TAG=$(get_service_tag "$SERVICE" "none")
    echo "--- Pushing $SERVICE ($TAG) ---"
    push_with_retry "${IMAGE_NAME}:${TAG}"
    push_with_retry "${IMAGE_NAME}:latest"
    
    if [ "$SKIP_CLOUDRUN" = true ]; then
      echo "--- Skipping update_cloudrun/jobs for $SERVICE ---"
      DEPLOYS_SUCCESS+=("$SERVICE (Docker only)")
    else
      if [ "$SERVICE" != "db_migrations" ]; then
        if update_cloudrun "$SERVICE" "$TAG"; then
          DEPLOYS_SUCCESS+=("$SERVICE")
          save_service_hash "$SERVICE"  # P1/R6 — indentation corrigée

          # ── R3 — Évaluation RAG post-déploiement (optionnelle) ──────────────
          if [ "$SERVICE" = "cv_api" ] && [ "${RAG_EVAL_ENABLED:-false}" = "true" ] && [ "$SKIP_TESTS" = false ]; then
            echo -e "\n${GREY}--- 🔍 [R3] Évaluation qualité RAG post-déploiement (30s) ---${RESET}"
            RAG_EVAL_EXIT=0
            RAG_EVAL_DRY_RUN="${RAG_EVAL_DRY_RUN:-false}" \
            PROJECT_ID="$PROJECT_ID" \
            bash scripts/run_rag_eval.sh --env dev || RAG_EVAL_EXIT=$?
            if [ "$RAG_EVAL_EXIT" -ne 0 ]; then
              echo -e "${RED}⚠️  [R3] Régression RAG détectée — vérifiez GEMINI_EMBEDDING_MODEL ou VECTOR_DISTANCE_THRESHOLD${RESET}"
              echo -e "${GREY}   → Requalifier les cas golden : RAG_EVAL_DRY_RUN=true ./scripts/run_rag_eval.sh${RESET}"
            else
              echo -e "${GREEN}✅ [R3] Qualité RAG validée post-déploiement${RESET}"
            fi
          fi
          # ────────────────────────────────────────────────────────────────────

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
            save_service_hash "$SERVICE"  # P1/R6 — indentation corrigée
          else
            DEPLOYS_FAILED+=("$SERVICE (Job execution failed)")
          fi
        else
          echo "--- Cloud Run Job $JOB_NAME n'existe pas encore. Seul le push de l'image a été effectué ---"
          DEPLOYS_SUCCESS+=("$SERVICE (Docker only)")
          save_service_hash "$SERVICE"
        fi
      fi
    fi
  fi
}

# P1/R5 — build_and_push_agent fusionnée dans build_and_push_standard
# Les agents utilisent le même pattern Docker (contexte racine, shared/)
# Le seul comportement différencié (PYTHONPATH agent_commons) est géré dans run_service_tests.

build_and_upload_frontend() {
  local BUMP=${1:-"patch"}
  local MODE=${2:-"both"}

  if [[ "$MODE" == "build" || "$MODE" == "both" ]]; then
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
    # P1/R8 — pushd/popd garantit le retour au répertoire racine même si npm échoue (set -eo pipefail)
    pushd frontend > /dev/null
    echo "--- NPM ci && Tests && Build ---"
    npm ci   # A2 — npm ci (reproductible, ne modifie pas package-lock.json, ~2-3x plus rapide en CI)
    
    if [ "$SKIP_TESTS" = false ]; then
      echo "--- Run Frontend Tests ---"
      npm run test:unit:run
    else
      echo -e "${YELLOW}[⚠️  TESTS SKIPPED] frontend — bypass via --skip-tests${RESET}"
      TESTS_SKIPPED+=("frontend")
    fi

    npm run build
    popd > /dev/null

    echo "--- Création de l'archive tar.gz ---"
    local TIMESTAMP=$(date +%Y%m%d%H%M%S)
    local ARCHIVE_NAME="frontend-${TIMESTAMP}-${TAG}.tar.gz"
    # A3 — L'archive locale est enregistrée dans _TMPFILES pour nettoyage automatique après upload
    _TMPFILES+=("$ARCHIVE_NAME")

    tar -czvf "$ARCHIVE_NAME" frontend/dist/
    FRONTEND_ARCHIVE_NAME="$ARCHIVE_NAME"
  fi

  if [[ "$MODE" == "deploy" || "$MODE" == "both" ]]; then
    if [[ " ${DEPLOYS_SKIPPED[*]} " == *" frontend "* ]]; then
      return 0
    fi

    local TAG=$(get_service_tag "frontend" "none")
    local ARCHIVE_NAME
    if [ -n "$FRONTEND_ARCHIVE_NAME" ]; then
      ARCHIVE_NAME="$FRONTEND_ARCHIVE_NAME"
    else
      ARCHIVE_NAME=$(ls frontend-*-${TAG}.tar.gz 2>/dev/null | tail -n 1)
    fi

    if [ -z "$ARCHIVE_NAME" ] || [ ! -f "$ARCHIVE_NAME" ]; then
      echo -e "${RED}❌ Archive frontend introuvable pour la version $TAG !${RESET}"
      DEPLOYS_FAILED+=("frontend (Missing archive)")
      return 1
    fi

    echo "--- Upload vers Google Cloud Storage ($FRONTEND_BUCKET) ---"
    gcloud storage cp "$ARCHIVE_NAME" "gs://${FRONTEND_BUCKET}/"

    if [ "$SKIP_CLOUDRUN" = true ]; then
      echo "--- Skipping deployment to environment bucket for frontend ---"
      DEPLOYS_SUCCESS+=("frontend (Archive only)")
      save_service_hash "frontend"
      return 0
    fi

    echo "--- Déploiement vers le bucket de l'environnement DEV et gestion du cache ---"
    local DEV_BUCKET
    DEV_BUCKET=$(cd platform-engineering/terraform && terraform workspace select dev >/dev/null 2>&1 && terraform output -raw frontend_bucket_name 2>/dev/null || echo "")

    if [[ -n "$DEV_BUCKET" && ! "$DEV_BUCKET" =~ "Warning:" ]]; then
      # IMPORTANT : local_up.py (Phase 2 / Locust) peut avoir extrait une ancienne archive
      # dans frontend/dist/, écrasant le build Phase 1. On extrait donc l'archive fraîche
      # dans un répertoire temporaire pour garantir que c'est bien la bonne version qui part sur GCS.
      local FRONTEND_TEMP_DIR
      FRONTEND_TEMP_DIR=$(mktemp -d)
      echo "-> Extraction de l'archive ${ARCHIVE_NAME} dans un répertoire temporaire (isolation Phase 2)..."
      tar -xzf "$ARCHIVE_NAME" -C "$FRONTEND_TEMP_DIR"
      local DIST_SRC="${FRONTEND_TEMP_DIR}/frontend/dist"

      echo "-> Synchronisation des fichiers vers gs://${DEV_BUCKET}..."
      gcloud storage rsync "${DIST_SRC}/" "gs://${DEV_BUCKET}/" --recursive --delete-unmatched-destination-objects

      rm -rf "$FRONTEND_TEMP_DIR"

      echo "-> Configuration des entêtes Cache-Control..."
      # Désactiver le cache pour index.html
      gcloud storage objects update "gs://${DEV_BUCKET}/index.html" --cache-control="no-store, no-cache, must-revalidate, max-age=0"
      # Mettre en cache les assets statiques (js, css, etc.) pour 1 an
      gcloud storage objects update "gs://${DEV_BUCKET}/assets/**" --cache-control="public, max-age=31536000, immutable" 2>/dev/null || true

      echo "-> Invalidation du cache CDN (Google Cloud CDN)..."
      gcloud compute url-maps invalidate-cdn-cache "lb-${TF_WORKSPACE}" --path "/*" --async --project "$PROJECT_ID" || echo "/!\ Attention: impossible d'invalider le cache CDN"
      DEPLOYS_SUCCESS+=("frontend")
      save_service_hash "frontend"
    else
      echo "-> /!\ Impossible de récupérer le nom du bucket dev depuis Terraform (ou output vide). Déploiement ignoré."
      DEPLOYS_SUCCESS+=("frontend (Build & Archive only)")
      save_service_hash "frontend"
    fi
  fi
}

# ==============================================================================
# Shared Library Build & Push (zenika-shared-schemas)
# ==============================================================================

build_and_push_shared_wheel() {
  local BUMP=${1:-"patch"}

  echo -e "\n${RED}=== Build & Push zenika-shared-schemas ===${RESET}"

  # ── 1. Bump de version dans shared/VERSION ─────────────────────────────────
  local VERSION_FILE="shared/VERSION"
  if [ ! -f "$VERSION_FILE" ]; then
    echo "v1.0.0" > "$VERSION_FILE"
  fi
  local CURRENT_VERSION
  CURRENT_VERSION=$(cat "$VERSION_FILE" | tr -d '[:space:]')
  # Strip leading 'v' for PEP 440
  local SEMVER
  SEMVER=$(echo "$CURRENT_VERSION" | sed 's/^v//')

  if [[ $SEMVER =~ ^([0-9]+)\.([0-9]+)\.([0-9]+)$ ]]; then
    local MAJOR="${BASH_REMATCH[1]}"
    local MINOR="${BASH_REMATCH[2]}"
    local PATCH="${BASH_REMATCH[3]}"
  else
    local MAJOR=1; local MINOR=0; local PATCH=0
  fi

  case $BUMP in
    major) MAJOR=$((MAJOR + 1)); MINOR=0; PATCH=0 ;;
    minor) MINOR=$((MINOR + 1)); PATCH=0 ;;
    patch) PATCH=$((PATCH + 1)) ;;
  esac
  local NEW_SEMVER="${MAJOR}.${MINOR}.${PATCH}"
  echo "v${NEW_SEMVER}" > "$VERSION_FILE"
  echo -e "${GREY}   Version: ${CURRENT_VERSION} → v${NEW_SEMVER}${RESET}"

  # ── 2. Mettre à jour la version dans pyproject.toml ────────────────────────
  local PYPROJECT="shared/pyproject.toml"
  if [ ! -f "$PYPROJECT" ]; then
    echo -e "${RED}❌ shared/pyproject.toml introuvable — annulation.${RESET}"
    return 1
  fi
  # Remplacer la ligne version = "x.y.z" par la nouvelle version
  sed -i.bak "s/^version = \".*\"/version = \"${NEW_SEMVER}\"/" "$PYPROJECT"
  rm -f "${PYPROJECT}.bak"
  echo -e "${GREY}   shared/pyproject.toml mis à jour (version = \"${NEW_SEMVER}\")${RESET}"

  # ── 3. Build du wheel ──────────────────────────────────────────────────────
  local WHEEL_DIST="shared/dist"
  rm -rf "$WHEEL_DIST"
  echo "--- Building wheel zenika-shared-schemas==${NEW_SEMVER} ---"
  # Utilisation de uv pour le build
  uv build --wheel --out-dir "$WHEEL_DIST" ./shared/ 2>&1 | tail -5
  local WHEEL_FILE
  WHEEL_FILE=$(ls "${WHEEL_DIST}"/*.whl 2>/dev/null | head -1)
  if [ -z "$WHEEL_FILE" ]; then
    echo -e "${RED}❌ Build wheel échoué — aucun .whl trouvé dans ${WHEEL_DIST}${RESET}"
    return 1
  fi
  echo -e "${GREEN}✅ Wheel buildé : ${WHEEL_FILE}${RESET}"

  # ── 4. Push vers Artifact Registry Python ─────────────────────────────────
  echo "--- Pushing wheel vers Artifact Registry (${PYTHON_REPO_URL}) ---"
  if uvx twine upload \
    --repository-url "https://${PYTHON_REPO_URL}/" \
    --username "oauth2accesstoken" \
    --password "$(gcloud auth print-access-token)" \
    --non-interactive \
    "$WHEEL_FILE" 2>&1; then

    echo -e "${GREEN}✅ zenika-shared-schemas==${NEW_SEMVER} publié sur Artifact Registry${RESET}"
  else
    echo -e "${YELLOW}⚠️  Push Artifact Registry échoué (non bloquant — wheel local disponible pour les Dockerfiles)${RESET}"
  fi

  DEPLOYS_SUCCESS+=("shared (zenika-shared-schemas==${NEW_SEMVER})")
}

sync_system_prompts() {
  echo -e "
${RED}=== Synchronisation des System Prompts (Grounding) ===${RESET}"

  # P1/R7 — Récupération du mot de passe via Secret Manager (jamais via terraform output)
  # terraform output est visible dans 'ps aux' et les logs shell ; Secret Manager est sûr.
  echo "[*] Récupération du mot de passe admin depuis Secret Manager..."
  local ADMIN_PWD
  ADMIN_PWD=$(gcloud secrets versions access latest \
    --secret=admin-password-dev \
    --project="$PROJECT_ID" 2>/dev/null || echo "")

  if [ -z "$ADMIN_PWD" ]; then
    echo -e "${YELLOW}[!] Impossible de récupérer le mot de passe admin depuis Secret Manager (admin-password-dev). Skip sync.${RESET}"
    return 0
  fi

  # Détermination de l'URL (via dev.yaml ou convention)
  local BASE_DOMAIN="zenika.slavayssiere.fr"
  if [ -f "platform-engineering/envs/dev.yaml" ]; then
    BASE_DOMAIN=$(grep "base_domain:" platform-engineering/envs/dev.yaml | cut -d'"' -f2)
  fi
  local API_URL="https://api.dev.${BASE_DOMAIN}/api/prompts"

  # Exécution du script Python
  if "$PYTHON_CMD" scripts/sync_prompts.py --url "$API_URL" --password "$ADMIN_PWD"; then
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
  elif [[ "$arg" == "--force-all" ]]; then
    FORCE_ALL=true
    SKIP_UNCHANGED=false
    echo -e "${YELLOW}[--force-all] Rebuild forcé de tous les services, ignorant le cache de hash.${RESET}"
  elif [[ "$arg" == "--skip-unchanged" ]]; then
    # Alias conservé pour compatibilité — même comportement que le défaut
    SKIP_UNCHANGED=true
  elif [[ "$arg" == "--skip-tests" ]]; then
    SKIP_TESTS=true
    echo -e "${RED}🚨 [--skip-tests] Gate de tests DÉSACTIVÉE — réservé aux hotfixes urgents uniquement !${RESET}"
  elif [[ "$arg" == "--skip-perf" ]]; then
    SKIP_PERF=true
    echo -e "${YELLOW}[--skip-perf] Gate de performance/charge Locust post-déploiement DÉSACTIVÉE.${RESET}"
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
    NEW_TARGETS+=("${APP_MICROSERVICES[@]}" "agent_router_api" "agent_hr_api" "agent_ops_api" "agent_missions_api" "frontend" "db_init")
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

# ── Gate d'audit de securite des configurations de Mocking (fail-fast) ───────────
audit_mock_configs

# ── Gate de test E2E & Evaluation globale (fail-fast) ───────────────────────────
if [ "$SKIP_TESTS" = false ]; then
  echo -e "\n${RED}--- 🧪 Gates de validation Stateless & Prompts ---${RESET}"
  echo -e "${GREY}   (Validation E2E in-memory + Évaluation de régression des Prompts IA...)${RESET}"

  E2E_EXIT=0
  PYTEST_CMD="./test_env/bin/pytest"
  if [ ! -f "$PYTEST_CMD" ]; then
    PYTEST_CMD="pytest"
  fi

  OTEL_TRACES_EXPORTER=none \
  OTEL_METRICS_EXPORTER=none \
  OTEL_LOGS_EXPORTER=none \
  SECRET_KEY="testsecret" \
  PYTHONPATH=. \
  $PYTEST_CMD tests/test_e2e_stateless.py shared/tests/test_prompt_evaluation.py -vv 2>&1 || E2E_EXIT=$?

  if [ "$E2E_EXIT" -eq 0 ]; then
    echo -e "${GREEN}✅ Gates de validation Stateless & Prompts : SUCCÈS${RESET}\n"
  else
    echo -e "${RED}❌ Gates de validation Stateless & Prompts : ÉCHEC (${E2E_EXIT})${RESET}"
    echo -e "${RED}   → Le déploiement est bloqué (fail-fast) pour cause d'intégration ou prompt corrompus.${RESET}"
    exit 1
  fi
fi

# ── Filet de sécurité : si shared/ a changé, forcer le rebuild de TOUS les consumers ──
# Même si l'utilisateur a spécifié un seul service, shared/ impacte tout le monde
SHARED_CONSUMERS=("competencies_api" "cv_api" "missions_api" "users_api" \
  "items_api" "drive_api" "prompts_api" "analytics_mcp" "monitoring_mcp" \
  "agent_hr_api" "agent_ops_api" "agent_missions_api" "agent_router_api" "frontend")

if check_shared_changed; then
  echo -e "${YELLOW}⚠️  shared/ a changé depuis le dernier build — expansion automatique vers tous les consumers${RESET}"

  if [ -f "shared/FILE_HASHES" ] && [ -f "/tmp/current_shared_hashes" ]; then
    echo -e "${GREY}   Détails des changements dans shared/ :${RESET}"
    diff "shared/FILE_HASHES" "/tmp/current_shared_hashes" | grep -E '^[<>]' | sed 's/^< /   [-] (Ancien) /; s/^> /   [+] (Nouveau) /' | awk '{print $1, $2, $4}' || true

    # Vérification stricte du contrat d'interface (shared/schemas/)
    if diff "shared/FILE_HASHES" "/tmp/current_shared_hashes" | grep -E '^[<>]' | grep -q 'shared/schemas/'; then
      echo -e "${YELLOW}🚨 Modification détectée dans shared/schemas/ (contrat d'interface) !${RESET}"
      if [ "$BUMP_TYPE" == "patch" ] || [ "$BUMP_TYPE" == "none" ]; then
        echo -e "${YELLOW}   → Upgrade automatique du bump de '${BUMP_TYPE}' à 'minor'.${RESET}"
        BUMP_TYPE="minor"
      fi
    fi
    echo ""
  else
    echo -e "${GREY}   (Détails non disponibles ce coup-ci, initialisation du tracking...)${RESET}"
    echo ""
  fi

  # ── Build & Push du wheel zenika-shared-schemas (version bumped) ──────────
  # Doit se faire AVANT les Docker builds des consumers pour que le wheel
  # local dans shared/dist/ soit disponible lors du COPY dans les Dockerfiles.
  CURRENT_DEPLOYING_SERVICE="shared"
  build_and_push_shared_wheel "$BUMP_TYPE"
  save_shared_hash
  CURRENT_DEPLOYING_SERVICE=""

  EXPANDED=false
  for consumer in "${SHARED_CONSUMERS[@]}"; do
    if [[ ! " ${ALL_TASKS[*]} " =~ " ${consumer} " ]]; then
      ALL_TASKS+=("$consumer")
      echo -e "${YELLOW}   + ${consumer} ajouté automatiquement (contrat impacté)${RESET}"
      EXPANDED=true
    fi
  done
  if [ "$EXPANDED" = false ]; then
    echo -e "${YELLOW}   Tous les consumers sont déjà dans la liste.${RESET}"
  fi
fi

# ==============================================================================
# Phase 1: Build Local & Smoke Tests
# ==============================================================================
echo -e "\n${RED}============================================================${RESET}"
echo -e "${RED}=== PHASE 1: Build Local & Smoke Tests                      ===${RESET}"
echo -e "${RED}============================================================${RESET}"

echo -e "${GREY}[*] Arrêt complet de la stack Docker (libère la RAM avant testcontainers en Phase 1)${RESET}"
docker-compose down --remove-orphans 2>/dev/null || true
docker-compose --profile perf --profile perf-stress down --remove-orphans 2>/dev/null || true
docker container prune -f 2>/dev/null || true
docker network rm monitoring_net 2>/dev/null || true

for TARGET_SERVICE in "${ALL_TASKS[@]}"; do
  CURRENT_DEPLOYING_SERVICE="$TARGET_SERVICE"
  if [[ " ${APP_MICROSERVICES[*]} " == *" $TARGET_SERVICE "* || "$TARGET_SERVICE" == "db_migrations" ]]; then
    show_progress "$TARGET_SERVICE"
    build_and_push_standard "$TARGET_SERVICE" "$BUMP_TYPE" "build"
  elif [ "$TARGET_SERVICE" = "db_init" ]; then
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

    # Bridging tag for Compose
    echo "--- Tagging for Compose: test-open-code-db_init:latest ---"
    docker tag "${DOCKER_REPO}/db_init:latest" "test-open-code-db_init:latest"

  elif [[ "$TARGET_SERVICE" == "agent_"* ]]; then
    show_progress "$TARGET_SERVICE"
    build_and_push_standard "$TARGET_SERVICE" "$BUMP_TYPE" "build"
  elif [ "$TARGET_SERVICE" = "frontend" ]; then
    show_progress "frontend"
    build_and_upload_frontend "$BUMP_TYPE" "build"
  elif [ "$TARGET_SERVICE" = "sync_prompts" ]; then
    echo -e "${GREY}[*] sync_prompts: Pas d'étape de build local requise.${RESET}"
  else
    echo -e "${RED}Erreur : Service '${TARGET_SERVICE}' inconnu.${RESET}"
    exit 1
  fi
  CURRENT_DEPLOYING_SERVICE=""
done

# Interrompre immédiatement la pipeline si un build ou smoke test local a échoué (fail-fast)
if [ ${#DEPLOYS_FAILED[@]} -gt 0 ]; then
  echo -e "${RED}❌ Échecs détectés lors de la Phase 1 (Build Local). Annulation du déploiement.${RESET}"
  exit 1
fi

# ==============================================================================
# Phase 1.5: Gate de Validation de Contrat d'Interface OpenAPI
# ==============================================================================
echo -e "\n${RED}============================================================${RESET}"
echo -e "${RED}=== PHASE 1.5: Gate de Validation des Contrats OpenAPI      ===${RESET}"
echo -e "${RED}============================================================${RESET}"

if [ "$SKIP_TESTS" = true ]; then
  echo -e "${YELLOW}[!] Gate de validation OpenAPI bypassée via --skip-tests.${RESET}"
else
  CURRENT_DEPLOYING_SERVICE="openapi_contract_gate"
  echo -e "${GREY}[*] Validation de la rétrocompatibilité des spécifications OpenAPI...${RESET}"
  
  # Exécution du script de validation
  if ! "$PYTHON_CMD" scripts/validate_openapi.py; then
    echo -e "${RED}❌ Échec de la validation de contrat OpenAPI (breaking changes détectés) !${RESET}"
    DEPLOYS_FAILED+=("openapi_contract_gate (Rupture de contrat OpenAPI)")
    exit 1
  else
    echo -e "${GREEN}✅ Tous les contrats d'interface OpenAPI ont été validés avec succès !${RESET}"
    DEPLOYS_SUCCESS+=("openapi_contract_gate")
  fi
  CURRENT_DEPLOYING_SERVICE=""
fi

# ==============================================================================
# Phase 2: Gate de Performance & Charge Locale (Locust)
# ==============================================================================
echo -e "\n${RED}============================================================${RESET}"
echo -e "${RED}=== PHASE 2: Gate de Performance & Charge Locale (Locust)   ===${RESET}"

echo -e "${RED}============================================================${RESET}"

if [ "$SKIP_PERF" = true ]; then
  echo -e "${YELLOW}[!] Gate de performance locale bypassée via --skip-perf.${RESET}"
elif [ "$SKIP_TESTS" = true ]; then
  echo -e "${YELLOW}[!] Gate de performance locale bypassée via --skip-tests.${RESET}"
elif [ ${#ALL_TASKS[@]} -eq 0 ]; then
  echo -e "${YELLOW}[!] Aucun service ciblé : skip de la gate Locust locale.${RESET}"
else
  # Vérifier si au moins un microservice ou agent BACKEND est ciblé
  # (frontend exclu : Locust ne teste pas le frontend)
  has_api_or_agent=false
  for task in "${ALL_TASKS[@]}"; do
    if [[ " ${APP_MICROSERVICES[*]} agent_router_api agent_hr_api agent_ops_api agent_missions_api " == *" $task "* ]]; then
      has_api_or_agent=true
      break
    fi
  done

  if [ "$has_api_or_agent" = false ]; then
    echo -e "${YELLOW}[!] Aucun microservice ni agent backend ciblé (uniquement frontend/tâches admin) : skip de la gate Locust locale.${RESET}"
  else
    # Vérifier si au moins un microservice/agent BACKEND ciblé a réellement changé (non skippé)
    # (frontend exclu : pas de test Locust dessus)
    any_api_changed=false
    for task in "${ALL_TASKS[@]}"; do
      if [[ " ${APP_MICROSERVICES[*]} agent_router_api agent_hr_api agent_ops_api agent_missions_api " == *" $task "* ]]; then
        if [[ " ${DEPLOYS_SKIPPED[*]} " != *" $task "* ]]; then
          any_api_changed=true
          break
        fi
      fi
    done

    if [ "$any_api_changed" = false ]; then
      echo -e "${YELLOW}[!] Aucune API ni agent n'a changé (tous skippés — hash identique) : gate Locust locale ignorée.${RESET}"
      DEPLOYS_SKIPPED+=("locust_local_gate (no code change)")
    else
      CURRENT_DEPLOYING_SERVICE="locust_local_gate"
      echo -e "${GREY}[*] Teardown complet (postgres inclus) pour éviter les états corrompus (postmaster.pid orphelin)${RESET}"
      docker-compose down -v --remove-orphans 2>/dev/null || true
      echo -e "${GREY}[*] Teardown des conteneurs perf existants (pubsub_emulator, mock_gemini...)${RESET}"
      docker-compose --profile perf --profile perf-stress down --remove-orphans 2>/dev/null || true
      echo -e "${GREY}[*] Suppression du réseau monitoring_net pour recréation en mode isolé (internal: true)${RESET}"
      docker network rm monitoring_net 2>/dev/null || true

      # Pré-flight : s'assurer que les images locales non gérées par deploy.sh sont buildées.
      # Ces images sont supprimées par docker system prune et ne se re-buildent pas automatiquement (--no-build).
      # - loki_mcp     : build depuis GitHub (grafana/loki-mcp)
      # - mock_gemini  : build depuis contexte local (./mock_gemini/)
      declare -A LOCAL_ONLY_IMAGES=(
        ["loki_mcp"]="test-open-code-loki_mcp:latest"
        ["mock_gemini"]="test-open-code-mock_gemini:latest"
      )
      for svc in "${!LOCAL_ONLY_IMAGES[@]}"; do
        img="${LOCAL_ONLY_IMAGES[$svc]}"
        if ! docker image inspect "$img" > /dev/null 2>&1; then
          echo -e "${GREY}[*] Image $img absente — build du service '$svc'...${RESET}"
          docker-compose build "$svc"
          if [ $? -ne 0 ]; then
            echo -e "${RED}❌ Build $svc échoué — gate Locust impossible.${RESET}"
            DEPLOYS_FAILED+=("locust_local_gate ($svc build failure)")
            exit 1
          fi
          echo -e "${GREEN}✅ $img buildée avec succès.${RESET}"
        else
          echo -e "${GREY}[*] Image $img présente localement — skip build.${RESET}"
        fi
      done

      # Note : les images de services (cv_api, users_api, etc.) sont déjà correctes —
      # Phase 3 du run précédent les a buildées et taguées :latest localement.
      # L'image Locust est buildée par _build_locust_image() dans local_up.py.
      # La variable GEMINI_API_BASE_URL est passée au conteneur cv_api via docker-compose.perf-override.yml.

      GEMINI_API_BASE_URL=http://mock_gemini:8099 \
      COMPOSE_FILE=docker-compose.yml:docker-compose.perf-override.yml \
      LOCUST_USERS=50 LOCUST_SPAWN_RATE=10 LOCUST_DURATION="2m" "$PYTHON_CMD" scripts/local_up.py --no-pull --perf --erase
      LOCUST_EXIT=$?

      if [ "$LOCUST_EXIT" -ne 0 ]; then
        echo -e "${RED}❌ La gate de performance locale (Locust) a échoué ! (Code de retour: $LOCUST_EXIT)${RESET}"
        DEPLOYS_FAILED+=("locust_local_gate (Failure in local performance gate)")
        exit 1
      else
        echo -e "${GREEN}✅ Gate de performance locale validée avec succès !${RESET}"
        DEPLOYS_SUCCESS+=("locust_local_gate")
      fi
      CURRENT_DEPLOYING_SERVICE=""
    fi
  fi

fi

# ==============================================================================
# Phase 3: Déploiement vers GCP (Artifact Registry / Cloud Run)
# ==============================================================================
echo -e "\n${RED}============================================================${RESET}"
echo -e "${RED}=== PHASE 3: Déploiement vers GCP (Artifact Registry / Cloud Run) ===${RESET}"
echo -e "${RED}============================================================${RESET}"

for TARGET_SERVICE in "${ALL_TASKS[@]}"; do
  CURRENT_DEPLOYING_SERVICE="$TARGET_SERVICE"
  if [[ " ${APP_MICROSERVICES[*]} " == *" $TARGET_SERVICE "* || "$TARGET_SERVICE" == "db_migrations" ]]; then
    show_progress "$TARGET_SERVICE"
    build_and_push_standard "$TARGET_SERVICE" "$BUMP_TYPE" "deploy"
  elif [ "$TARGET_SERVICE" = "db_init" ]; then
    if [[ " ${DEPLOYS_SKIPPED[*]} " == *" db_init "* ]]; then
      CURRENT_DEPLOYING_SERVICE=""
      continue
    fi

    show_progress "db_init"
    local_tag=$(get_service_tag "db_init" "none")
    db_init_image="${DOCKER_REPO}/db_init:${local_tag}"
    echo "--- Pushing db_init ---"
    push_with_retry "${DOCKER_REPO}/db_init:${local_tag}"
    push_with_retry "${DOCKER_REPO}/db_init:latest"

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
    build_and_push_standard "$TARGET_SERVICE" "$BUMP_TYPE" "deploy"
  elif [ "$TARGET_SERVICE" = "frontend" ]; then
    show_progress "frontend"
    build_and_upload_frontend "$BUMP_TYPE" "deploy"
  elif [ "$TARGET_SERVICE" = "sync_prompts" ]; then
    if sync_system_prompts; then DEPLOYS_SUCCESS+=("sync_prompts"); else DEPLOYS_FAILED+=("sync_prompts"); fi
  else
    echo -e "${RED}Erreur : Service '${TARGET_SERVICE}' inconnu.${RESET}"
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
