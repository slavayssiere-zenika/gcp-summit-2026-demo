#!/usr/bin/env bash
set -eo pipefail

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
  echo "  --mutation-tests   Active les tests de mutation mutmut (opt-in, lent ~5-15 min/service)"
  echo "  --mutation-strict  --mutation-tests + bloque le build si score < seuil (défaut: 60%)"
  echo ""
  echo "Tests:"
  echo "  Par défaut, tous les tests sont lancés : unitaires + intégration Testcontainers (nécessite Docker)."
  echo "  Les tests d'intégration sont dans tests/integration/ de chaque service."
  echo "  Ils démarrent des conteneurs Docker pour PostgreSQL, Redis et l'émulateur Pub/Sub."
  echo "  Docker doit être démarré — une vérification automatique bloque le build si indisponible."
  echo "  Utilisez --skip-tests pour bypasser tous les tests (unitaires + intégration) en mode hotfix."

  echo "Note: Par défaut, seuls les services ayant changé depuis leur dernier build sont reconstruits."
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
SKIP_UNCHANGED=true    # Défaut : rebuild uniquement ce qui a changé (opt-out via --force-all)
FORCE_ALL=false        # Rebuild tout, même si aucun changement détecté
RUN_MUTATION_TESTS=false   # Opt-in : --mutation-tests
MUTATION_STRICT=false      # Opt-in : --mutation-strict (bloque le build si score < seuil)
MUTATION_SCORE_THRESHOLD=60  # Seuil minimum de mutants tués (%) pour passer la gate
declare -A COVERAGE_RESULTS   # service -> "75%" | "N/A" | "SKIPPED"
declare -A MUTATION_RESULTS   # service -> "75% (50/67)" | "N/A" | "SKIPPED"

# Répertoire de logs par run — conservé après exécution pour debug
LOG_DIR="./deploy_logs/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$LOG_DIR"

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

  # ── Rapport de couverture + mutation des services rebuildés ──────────────────
  if [ ${#COVERAGE_RESULTS[@]} -gt 0 ]; then
    local HAS_MUTATION=false
    [ ${#MUTATION_RESULTS[@]} -gt 0 ] && HAS_MUTATION=true

    echo -e "${GREY}------------------------------------------------------------${RESET}"
    if [ "$HAS_MUTATION" = true ]; then
      echo -e "📊 ${GREY}QUALITÉ DE TEST (services rebuildés)${RESET}"
      echo -e "${GREY}------------------------------------------------------------${RESET}"
      printf "   %-30s %-18s %s\n" "SERVICE" "COUVERTURE" "MUTATION SCORE"
      printf "   %-30s %-18s %s\n" "-------" "----------" "--------------"
    else
      echo -e "📊 ${GREY}COUVERTURE DE TEST (services rebuildés)${RESET}"
      echo -e "${GREY}------------------------------------------------------------${RESET}"
      printf "   %-35s %s\n" "SERVICE" "COUVERTURE"
      printf "   %-35s %s\n" "-------" "----------"
    fi

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

      if [ "$HAS_MUTATION" = true ]; then
        local mut="${MUTATION_RESULTS[$svc]:-—}"
        local mut_color="$RESET"
        local mut_icon="🧬"
        local mut_num
        mut_num=$(echo "$mut" | grep -oE '^[0-9]+' || echo "")
        if [[ "$mut" == "SKIPPED" || "$mut" == "—" ]]; then
          mut_color="$GREY"; mut_icon="➖ "
        elif [[ "$mut" == *"❌"* ]]; then
          mut_color="$RED"; mut_icon="❌"
        elif [[ "$mut_num" =~ ^[0-9]+$ ]]; then
          if [ "$mut_num" -ge 80 ]; then
            mut_color="$GREEN"; mut_icon="✅"
          elif [ "$mut_num" -ge "$MUTATION_SCORE_THRESHOLD" ]; then
            mut_color="$YELLOW"; mut_icon="⚠️ "
          else
            mut_color="$YELLOW"; mut_icon="⚠️ "
          fi
        fi
        printf "   %-30s ${cov_color}%-18s${RESET} ${mut_color}%s %s${RESET}\n" \
          "$svc" "${cov_icon} ${cov}" "${mut_icon}" "$mut"
      else
        printf "   %-35s ${cov_color}%s %s${RESET}\n" "$svc" "$cov_icon" "$cov"
      fi
    done

    if [ "$HAS_MUTATION" = true ]; then
      echo -e "   ${GREY}(seuil mutation: ≥${MUTATION_SCORE_THRESHOLD}% mutants tués)${RESET}"
    fi
  fi
  # ─────────────────────────────────────────────────────────────────────────────

  echo -e "${GREY}============================================================${RESET}\n"

  # ── Génération du fichier prompt Antigravity ─────────────────────────────────────────
  local PROMPT_FILE="${LOG_DIR}/antigravity_prompt.md"
  local HAS_ERRORS=false
  {
    echo "# Rapport de déploiement — $(date '+%Y-%m-%d %H:%M')"
    echo ""
    echo "**Contexte** : résultat de \`./scripts/deploy.sh\` sur le mono-repo Zenika."
    echo "Voici les erreurs et warnings à analyser :"
    echo ""

    # 1. Logs de tests en échec
    for f in "${LOG_DIR}"/*_tests.log; do
      [ -f "$f" ] || continue
      local svc_name
      svc_name=$(basename "$f" _tests.log)
      # Extraire uniquement les lignes importantes (ERRORS, FAILED, ERROR, NameError...)
      local errors
      errors=$(grep -E 'ERROR|FAILED|Error|Exception|NameError|ImportError|assert' "$f" \
        | grep -v 'DeprecationWarning\|pythonjsonlogger\|HTTP Request Failed\|exc_info' \
        | head -30)
      if [ -n "$errors" ]; then
        HAS_ERRORS=true
        echo "## ❌ Tests : ${svc_name}"
        echo '```'
        echo "$errors"
        echo '```'
        # Lignes de contexte : les 20 dernières lignes du log (résumé pytest)
        echo "**Résumé (fin du log)** :"
        echo '```'
        tail -20 "$f"
        echo '```'
        echo ""
      fi
    done

    # 2. Logs mutmut si échec strict
    for f in "${LOG_DIR}"/*_mutation.log; do
      [ -f "$f" ] || continue
      local svc_name
      svc_name=$(basename "$f" _mutation.log)
      local mut_errors
      mut_errors=$(grep -E 'BadTestExecution|Traceback|Error|FAILED' "$f" | head -10)
      if [ -n "$mut_errors" ]; then
        HAS_ERRORS=true
        echo "## ⚠️  Mutation : ${svc_name}"
        echo '```'
        echo "$mut_errors"
        echo '```'
        echo ""
      fi
    done

    if [ "$HAS_ERRORS" = false ]; then
      echo "> ✅ Aucune erreur — tous les services ont passé les tests."
    else
      echo "---"
      echo "> Logs complets disponibles dans : \`${LOG_DIR}/\`"
    fi
  } > "$PROMPT_FILE"

  # Affichage du chemin (et contenu si erreurs)
  if [ "$HAS_ERRORS" = true ]; then
    echo -e "${RED}\n📋 Rapport d'erreurs généré — copiez-collez dans Antigravity :${RESET}"
    echo -e "${GREY}   Fichier : ${PROMPT_FILE}${RESET}"
    echo -e "${GREY}   Commande : cat ${PROMPT_FILE}${RESET}\n"
    cat "$PROMPT_FILE"
  else
    echo -e "${GREEN}\n📝 Rapport généré (tout OK) : ${PROMPT_FILE}${RESET}"
  fi
  # ──────────────────────────────────────────────────────────────────────────────

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
  if [[ "$SERVICE" == "agent_"* ]]; then
    DIRS_TO_CHECK+=("./agent_commons")
  fi
  # shared/ est toujours inclus dans le hash de tous les services
  # → tout changement dans shared/ invalide le hash de TOUS les consumers
  if [ -d "./shared" ]; then
    DIRS_TO_CHECK+=("./shared")
  fi

  # Compute a SHA1 hash of all files in the relevant directories
  # Exclude VERSION and HASH files, and common ignore paths
  find "${DIRS_TO_CHECK[@]}" -type f \
    ! -name "VERSION" ! -name "HASH" ! -name "FILE_HASHES" \
    ! -name ".coverage" ! -name "coverage.json" ! -name "pytest.log" \
    ! -name "*.db" ! -name "*.pyc" ! -name ".mutmut-cache" \
    ! -path "*/__pycache__/*" ! -path "*/.pytest_cache/*" ! -path "*/mutants/*" \
    ! -path "*/.venv/*" ! -path "*/test_env/*" ! -path "*/node_modules/*" \
    ! -path "*/dist/*" ! -path "*/.DS_Store" \
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
      ! -name "HASH" ! -name "FILE_HASHES" \
      ! -name ".coverage" ! -name "coverage.json" ! -name "pytest.log" \
      ! -name "*.db" ! -name "*.pyc" ! -name ".mutmut-cache" \
      ! -path "*/__pycache__/*" ! -path "*/.pytest_cache/*" ! -path "*/mutants/*" \
      ! -path "*/.venv/*" ! -path "*/test_env/*" ! -path "*/node_modules/*" \
      ! -path "*/dist/*" ! -path "*/.DS_Store" \
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
    ! -name "HASH" ! -name "FILE_HASHES" \
    ! -name ".coverage" ! -name "coverage.json" ! -name "pytest.log" \
    ! -name "*.db" ! -name "*.pyc" ! -name ".mutmut-cache" \
    ! -path "*/__pycache__/*" ! -path "*/.pytest_cache/*" ! -path "*/mutants/*" \
    ! -path "*/.venv/*" ! -path "*/test_env/*" ! -path "*/node_modules/*" \
    ! -path "*/dist/*" ! -path "*/.DS_Store" \
    -exec shasum {} + | sort > "/tmp/current_shared_hashes"
  CURRENT=$(shasum "/tmp/current_shared_hashes" | awk '{print $1}')
  
  if [ "$SAVED" != "$CURRENT" ]; then
    return 0 # changed
  else
    return 1 # not changed
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

  # Vérification de la présence du virtualenv de test
  if [ ! -f "$TEST_RUNNER" ]; then
    echo -e "${YELLOW}[⚠️  SKIP TESTS] test_env/bin/pytest introuvable pour $SERVICE.${RESET}"
    echo -e "${YELLOW}   → Créez le venv : python3 -m venv test_env && test_env/bin/pip install -r scripts/requirements.txt${RESET}"
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

  # Nettoyage du sandbox mutmut résiduel
  # Problème : mutmut crée mutants/ avec des copies des tests. pytest compile des .pyc
  # dans tests/__pycache__/ avec __file__ pointant vers mutants/tests/*.py.
  # Au run pytest suivant, le module importé (mutants/) ne correspond pas au fichier
  # collecté (tests/) → "import file mismatch".
  # Fix : supprimer mutants/ ENTIÈREMENT + tests/__pycache__/ pour effacer les .pyc périmés.
  if [ -d "./${SERVICE}/mutants" ]; then
    rm -rf "./${SERVICE}/mutants"
    find "./${SERVICE}" -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
    echo -e "${GREY}[ℹ️] Sandbox mutmut nettoyé (mutants/ + __pycache__ supprimés).${RESET}"
  fi

  # PYTHONPATH : racine du monorepo (pour shared/) + dossier du service
  # Les agents ajoutent aussi agent_commons
  local PYTHONPATH_VAL=".:${SERVICE}"
  if [[ "$SERVICE" == "agent_"* ]]; then
    PYTHONPATH_VAL=".:${SERVICE}:./agent_commons"
  fi

  # Fichier temporaire pour capturer la sortie pytest (nécessaire pour parser la couverture)
  # Enregistré dans _TMPFILES pour nettoyage garanti même en cas de SIGINT/SIGTERM (P0/R3)
  local TMP_OUTPUT
  TMP_OUTPUT=$(mktemp)
  _TMPFILES+=("$TMP_OUTPUT")

  local PYTEST_EXIT=0
  OTEL_TRACES_EXPORTER=none \
  OTEL_METRICS_EXPORTER=none \
  OTEL_LOGS_EXPORTER=none \
  SECRET_KEY="testsecret" \
  PYTHONPATH="$PYTHONPATH_VAL" \
  "$TEST_RUNNER" "./${SERVICE}" -x \
    --ignore=test_env \
    --cov="./${SERVICE}" --cov-report=term-missing:skip-covered \
    2>&1 > "$TMP_OUTPUT" || PYTEST_EXIT=$?

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
# Mutation Test Gate (opt-in via --mutation-tests / --mutation-strict)
# ==============================================================================

run_mutation_tests() {
  local SERVICE=$1
  local MUTMUT_BIN="./test_env/bin/mutmut"

  # Désactivé par défaut — uniquement si --mutation-tests ou --mutation-strict
  if [ "$RUN_MUTATION_TESTS" = false ]; then
    return 0
  fi

  # Vérification de la présence de mutmut
  if [ ! -f "$MUTMUT_BIN" ]; then
    echo -e "${YELLOW}[⚠️  MUTATION SKIP] mutmut introuvable dans test_env.${RESET}"
    echo -e "${YELLOW}   → test_env/bin/pip install mutmut${RESET}"
    MUTATION_RESULTS["$SERVICE"]="SKIPPED"
    return 0
  fi

  # Vérification de la présence du setup.cfg mutmut
  if [ ! -f "./${SERVICE}/setup.cfg" ]; then
    echo -e "${GREY}[ℹ️  MUTATION SKIP] Pas de setup.cfg mutmut pour $SERVICE — skipped.${RESET}"
    MUTATION_RESULTS["$SERVICE"]="SKIPPED"
    return 0
  fi

  echo -e "${YELLOW}--- 🧬 Tests de mutation : $SERVICE ---${RESET}"

  # PYTHONPATH : idem run_service_tests
  local PYTHONPATH_VAL=".:${SERVICE}"
  if [[ "$SERVICE" == "agent_"* ]]; then
    PYTHONPATH_VAL=".:${SERVICE}:./agent_commons"
  fi

  # mutmut log persistant — stdout silencé (trop verbeux pour le terminal)
  local MUT_LOG="${LOG_DIR}/${SERVICE}_mutation.log"

  pushd "./${SERVICE}" > /dev/null
  OTEL_TRACES_EXPORTER=none \
  OTEL_METRICS_EXPORTER=none \
  OTEL_LOGS_EXPORTER=none \
  SECRET_KEY="testsecret" \
  PYTHONPATH="../${PYTHONPATH_VAL//.\//../}" \
  "$OLDPWD/$MUTMUT_BIN" run \
    2>&1 > "$OLDPWD/$MUT_LOG"

  # Collecter les résultats (que le run ait réussi ou non)
  local MUT_RESULTS_RAW
  MUT_RESULTS_RAW=$("$OLDPWD/$MUTMUT_BIN" results --all true 2>/dev/null || echo "")
  popd > /dev/null

  # Extraire les compteurs depuis la sortie brute de mutmut results
  # Format mutmut 3.x : chaque ligne = "  module.func__mutmut_N: killed|survived|not checked"
  # Note: on utilise grep + wc -l plutôt que grep -c pour éviter le "0\n0" quand
  # grep -c ne trouve aucun match (exit 1) et que || echo "0" s'exécute (valeur multi-ligne)
  local KILLED SURVIVED TOTAL SCORE
  KILLED=$(echo "$MUT_RESULTS_RAW" | grep ': killed' | wc -l | tr -d ' ')
  SURVIVED=$(echo "$MUT_RESULTS_RAW" | grep ': survived' | wc -l | tr -d ' ')
  TOTAL=$(( KILLED + SURVIVED ))

  # Vérifier si mutmut n'a pas pu s'exécuter (phase stats échouée)
  local UNCHECKED
  UNCHECKED=$(echo "$MUT_RESULTS_RAW" | grep ': not checked' | wc -l | tr -d ' ')

  if [ "$TOTAL" -eq 0 ] && [ "$UNCHECKED" -gt 0 ]; then
    echo -e "${YELLOW}⚠️  Mutation $SERVICE : ${UNCHECKED} mutants non testés (sandbox stats) — voir ${MUT_LOG}${RESET}"
    MUTATION_RESULTS["$SERVICE"]="⚠️ ${UNCHECKED} mutants (non testés)"
    return 0
  fi

  if [ "$TOTAL" -eq 0 ]; then
    echo -e "${GREY}[ℹ️  MUTATION] Aucun mutant généré pour $SERVICE.${RESET}"
    MUTATION_RESULTS["$SERVICE"]="N/A"
    return 0
  fi

  # Score = (Killed / Total) * 100
  SCORE=$(( KILLED * 100 / TOTAL ))
  local SCORE_STR="${SCORE}% (${KILLED}/${TOTAL} tués)"

  if [ "$SCORE" -ge "$MUTATION_SCORE_THRESHOLD" ]; then
    echo -e "${GREEN}✅ Mutation $SERVICE : ${SCORE_STR} ≥ seuil ${MUTATION_SCORE_THRESHOLD}% — OK${RESET}"
    MUTATION_RESULTS["$SERVICE"]="$SCORE_STR"
    return 0
  else
    MUTATION_RESULTS["$SERVICE"]="${SCORE_STR} ⚠️"
    echo -e "${YELLOW}⚠️  Mutation $SERVICE : ${SCORE_STR} < seuil ${MUTATION_SCORE_THRESHOLD}%${RESET}"
    if [ "$MUTATION_STRICT" = true ]; then
      echo -e "${RED}❌ [--mutation-strict] Build bloqué — score de mutation insuffisant.${RESET}"
      echo -e "${RED}   → Renforcez les assertions dans les tests pour tuer plus de mutants.${RESET}"
      DEPLOYS_FAILED+=("$SERVICE (Mutation score: ${SCORE}% < ${MUTATION_SCORE_THRESHOLD}%)")
      return 1
    else
      echo -e "${YELLOW}   → Score sous le seuil — non bloquant (utilisez --mutation-strict pour bloquer).${RESET}"
      return 0
    fi
  fi
}


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

  if [ "$SKIP_UNCHANGED" = true ] && [ "$SERVICE" != "db_init" ] && ! has_changes "$SERVICE"; then
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
  # ── Gate de mutation (opt-in via --mutation-tests / --mutation-strict) ───────
  run_mutation_tests "$SERVICE" || { CURRENT_DEPLOYING_SERVICE=""; return 1; }
  # ────────────────────────────────────────────────────────────────────────────

  local TAG=$(get_service_tag "$SERVICE" "$BUMP")
  echo "--- Building $SERVICE ($TAG) ---"
  local IMAGE_NAME="${DOCKER_REPO}/${SERVICE}"

  # Build pour Cloud Run (nécessite amd64) — contexte = racine du monorepo
  # (même pattern que les agents) pour inclure shared/ dans le contexte
  docker build --platform linux/amd64 \
    -t "${IMAGE_NAME}:${TAG}" -t "${IMAGE_NAME}:latest" \
    -f "./${SERVICE}/Dockerfile" .
  
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
        save_service_hash "$SERVICE"  # P1/R6 — indentation corrigée
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
      fi
    fi
  fi
}

# P1/R5 — build_and_push_agent fusionnée dans build_and_push_standard
# Les agents utilisent le même pattern Docker (contexte racine, shared/)
# Le seul comportement différencié (PYTHONPATH agent_commons) est géré dans run_service_tests.

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
  # P1/R8 — pushd/popd garantit le retour au répertoire racine même si npm échoue (set -eo pipefail)
  pushd frontend > /dev/null
  echo "--- NPM ci && Build ---"
  npm ci   # A2 — npm ci (reproductible, ne modifie pas package-lock.json, ~2-3x plus rapide en CI)
  npm run build
  popd > /dev/null

  echo "--- Création de l'archive tar.gz ---"
  local TIMESTAMP=$(date +%Y%m%d%H%M%S)
  local ARCHIVE_NAME="frontend-${TIMESTAMP}-${TAG}.tar.gz"
  # A3 — L'archive locale est enregistrée dans _TMPFILES pour nettoyage automatique après upload
  _TMPFILES+=("$ARCHIVE_NAME")

  tar -czvf "$ARCHIVE_NAME" frontend/dist/

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
    echo "-> /!\ Impossible de récupérer le nom du bucket dev depuis Terraform (ou output vide). Déploiement ignoré."
    DEPLOYS_SUCCESS+=("frontend (Build & Archive only)")
    save_service_hash "frontend"
  fi
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
  elif [[ "$arg" == "--mutation-tests" ]]; then
    RUN_MUTATION_TESTS=true
    echo -e "${YELLOW}[🧬 --mutation-tests] Tests de mutation activés (lent — prévoir ~5-15 min par service).${RESET}"
  elif [[ "$arg" == "--mutation-strict" ]]; then
    RUN_MUTATION_TESTS=true
    MUTATION_STRICT=true
    echo -e "${YELLOW}[🧬 --mutation-strict] Tests de mutation activés en mode STRICT (bloque si score < ${MUTATION_SCORE_THRESHOLD}%).${RESET}"
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
    build_and_push_standard "$TARGET_SERVICE" "$BUMP_TYPE"  # P1/R5 — fusionné avec build_and_push_standard
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

# ── Sauvegarde du hash de shared/ si tous les consumers ont été buildés sans échec ──
if [ ${#DEPLOYS_FAILED[@]} -eq 0 ] && [ -d "./shared" ]; then
  save_shared_hash
  echo -e "${GREY}[shared/HASH] Hash mis à jour après build réussi.${RESET}"
fi

# Le summary de fin est géré par le trap EXIT.
