#!/bin/bash

# Configuration

echo "Démarrage des tests en parallèle..."

pids=()
apis=("agent_api" "competencies_api" "cv_api" "drive_api" "items_api" "prompts_api" "users_api" "market_mcp")

for api in "${apis[@]}"; do
    echo "Lancement des tests pour $api..."
    (cd "$api" && OTEL_TRACES_EXPORTER=none OTEL_METRICS_EXPORTER=none OTEL_LOGS_EXPORTER=none SECRET_KEY="testsecret" PYTHONPATH=. ../test_env/bin/pytest --cov=. --cov-report=json > pytest.log 2>&1) &
    pids+=("$api:$!")
done

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
