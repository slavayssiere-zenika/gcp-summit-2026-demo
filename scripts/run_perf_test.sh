#!/bin/bash
set -e

echo "🚀 Etape 1: Génération du grand volume de données pour les tests de perf (400 users, 2000 items)..."
python3 seed_data.py --perf

echo "🚀 Etape 2: Lancement des tests Locust en mode headless (sans interface)..."
# On s'assure que le dossier de résultats existe
mkdir -p locust/results

# Variables de configuration de charge
USERS=50
SPAWN_RATE=10
DURATION=1m

echo "Simulating $USERS concurrent users (spawn rate: $SPAWN_RATE/s) for $DURATION..."
docker-compose --profile perf run --rm locust \
    -f /locust/locustfile.py \
    --headless \
    -u $USERS \
    -r $SPAWN_RATE \
    -t $DURATION \
    --csv=/locust/results/perf_stats \
    --host=http://localhost  # placeholder requis par Locust CLI \u2014 les vraies URLs sont dans locustfile.py

echo "✅ Tests de perf terminés !"
echo "📊 Les résultats sont disponibles dans le dossier 'locust/results/' :"
echo "- locust/results/perf_stats_stats.csv : Statistiques par API (temps de réponse, RPS, etc.)"
echo "- locust/results/perf_stats_failures.csv : Liste des erreurs HTTP rencontrées"
echo ""
echo "💡 Comment utiliser ces résultats pour améliorer les APIs ?"
echo "1. Analyser les colonnes 'Median Response Time' et '95% Line' du fichier perf_stats_stats.csv."
echo "2. Identifier les endpoints les plus lents (ex: requêtes qui dépassent 500ms au 95e percentile)."
echo "3. Optimiser le code de ces endpoints : ajout d'index en base de données, utilisation de requêtes JOIN au lieu de requêtes N+1, ou ajout d'un système de cache (Redis)."
echo "4. Vérifier le fichier perf_stats_failures.csv pour détecter les '429 Too Many Requests' (si rate limiting), les timeouts (504), ou erreurs 500 liées à des blocages de connexions DB."
echo "5. Relancer ce script après chaque optimisation pour valider l'amélioration !"
