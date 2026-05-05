#!/bin/bash

# run_tests.sh — Lance les tests unitaires ET les tests d'intégration Testcontainers
# en parallèle sur chaque service détecté.
#
# Prérequis : Docker doit être disponible (nécessaire pour les tests d'intégration).
# Les tests d'intégration sont dans tests/integration/ et nécessitent des conteneurs.
# Si Docker est absent, un avertissement est affiché mais les tests unitaires continuent.

set -euo pipefail

# ─── Vérification Docker ────────────────────────────────────────────────────
check_docker_available() {
    if ! command -v docker &>/dev/null; then
        echo "⚠️  [WARN] Docker introuvable — les tests d'intégration (Testcontainers) seront ignorés."
        echo "         Installez Docker pour activer les tests d'intégration complets."
        return 1
    fi
    if ! docker info &>/dev/null 2>&1; then
        echo "⚠️  [WARN] Le démon Docker n'est pas démarré — tests d'intégration ignorés."
        echo "         Démarrez Docker Desktop ou 'sudo systemctl start docker'."
        return 1
    fi
    return 0
}

DOCKER_AVAILABLE=true
check_docker_available || DOCKER_AVAILABLE=false

echo "Démarrage des tests en parallèle (Docker: $DOCKER_AVAILABLE)..."

pids=()
apis=()

echo "Détection dynamique des modules de test..."
for dir in */; do
    # On ignore test_env et les dossiers cachés
    if [[ "$dir" != "test_env/" ]] && [[ "$dir" != .* ]]; then
        # On vérifie s'il y a un pytest.ini ou des fichiers test_*.py dans le dossier
        if find "$dir" -maxdepth 3 \( -name 'test_*.py' -o -name '*_test.py' -o -name 'pytest.ini' \) 2>/dev/null | grep -q .; then
            clean_name="${dir%/}"
            apis+=("$clean_name")
        fi
    fi
done

echo "Modules détectés : ${apis[*]}"

for api in "${apis[@]}"; do
    echo "Lancement des tests pour $api..."
    # Lance unitaires + intégration (tests/integration/ est découvert automatiquement par pytest)
    # Si Docker est absent, les tests d'intégration échoueront gracieusement (Testcontainers
    # lève une erreur au démarrage du conteneur — le test est marqué ERROR, pas FAILED)
    (cd "$api" && OTEL_TRACES_EXPORTER=none OTEL_METRICS_EXPORTER=none \
        OTEL_LOGS_EXPORTER=none SECRET_KEY="testsecret" PYTHONPATH=..:. \
        ../test_env/bin/pytest --cov=. --cov-report=json > pytest.log 2>&1) &
    pids+=("$api:$!")
done

if [ -d "frontend" ] && grep -q '"test:unit"' "frontend/package.json" 2>/dev/null; then
    echo "Lancement des tests vitest pour frontend..."
    (cd frontend && npm run test:unit:run > vitest.log 2>&1) &
    pids+=("frontend:$!")
fi

failure=0
for entry in "${pids[@]}"; do
    api_name="${entry%%:*}"
    pid="${entry##*:}"

    wait "$pid"
    if [ $? -ne 0 ]; then
        echo "❌ L'un des tests a échoué: $api_name (PID: $pid)."
        echo "   → Consultez $api_name/pytest.log pour les détails."
        failure=1
    fi
done

if [ $failure -ne 0 ]; then
    echo "Échec des tests critiques, annulation du git push."
    exit 1
fi

if [ "$DOCKER_AVAILABLE" = "true" ]; then
    echo "✅ Tous les tests ont réussi (unitaires + intégration Testcontainers). Rapports json générés."
else
    echo "✅ Tests unitaires réussis. Tests d'intégration ignorés (Docker absent). Rapports json générés."
fi
