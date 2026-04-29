#!/bin/bash

# Configuration

echo "Démarrage des tests en parallèle..."

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
    (cd "$api" && OTEL_TRACES_EXPORTER=none OTEL_METRICS_EXPORTER=none OTEL_LOGS_EXPORTER=none SECRET_KEY="testsecret" PYTHONPATH=..:. ../test_env/bin/pytest --cov=. --cov-report=json > pytest.log 2>&1) &
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
        failure=1
    fi
done

if [ $failure -ne 0 ]; then
    echo "Échec des tests critiques, annulation du git push."
    exit 1
fi

echo "✅ Tous les tests ont réussi avec succès. Rapports json générés."
