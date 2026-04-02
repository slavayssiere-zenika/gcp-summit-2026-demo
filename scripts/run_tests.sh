#!/bin/bash
set -e

echo "Démarrage des tests en parallèle..."

pids=""

for api in agent_api competencies_api cv_api drive_api items_api prompts_api users_api; do
    echo "Lancement des tests pour $api..."
    (
        cd "$api"
        PYTHONPATH=. TESTING=1 ../test_env/bin/pytest --cov=. --cov-report=json > pytest.log 2>&1
    ) &
    pids="$pids $!"
done

failed=0
for pid in $pids; do
    wait $pid || {
        echo "❌ L'un des tests a échoué (PID: $pid)."
        failed=1
    }
done

if [ $failed -ne 0 ]; then
    echo "Échec des tests critiques, annulation du git push."
    exit 1
fi

echo "✅ Tous les tests ont réussi avec succès. Rapports json générés."
