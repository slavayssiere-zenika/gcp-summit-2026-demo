---
description: Lance les tests de performance et de stress locaux via local_up.py (mode perf + stress), analyse les rapports CSV générés et propose des améliorations architecturales concrètes.
---

Ce workflow orchestre un cycle complet de tests de performance local :
pipeline d'ingestion CV (mock_gemini), test de charge standard (50 users, 1 min)
et stress test distribué (500 users, 5 min), puis analyse les rapports pour
proposer des optimisations priorisées.

> **Pré-requis** : Docker Desktop actif, `local_up.py` accessible, images AR présentes.
> Ce workflow NE déploie PAS en production. Il est 100% local.

### Seed intelligent — comportement automatique

`local_up.py` inclut un **skip-seed par détection** : après le démarrage des services,
il obtient un JWT admin et sonde **10 users + 5 items aléatoires** issus de `seeded_ids.json`.
Si ≥ 80% répondent HTTP 200, les données sont confirmées en base → seed ignoré.
Cela couvre les cas de reset DB, rollback Liquibase ou redémarrage sur volume vierge.

| Situation | Commande | Seed |
|---|---|---|
| Premier run (DB vide) | `--perf` | ✅ Seed complet |
| Runs suivants (données OK) | `--perf` | ⏭️ Skip automatique (probe API) |
| Forcer le skip (sans probe) | `--perf --skip-seed` | ⏭️ Skip forcé |
| Repartir de zéro | `--perf --erase` | 🔄 Erase + reseed |

### Comparaison automatique

À la fin de chaque run, `local_up.py` affiche automatiquement le diff avec les
3 derniers runs (via `scripts/compare_runs.py`). Pour consulter l'historique manuellement :

```bash
python3 scripts/compare_runs.py          # diff 2 derniers runs
python3 scripts/compare_runs.py --runs 5 # diff 5 derniers
python3 scripts/compare_runs.py --list   # liste les runs disponibles
```

---

### Étape 0 : Vérifications préalables

// turbo
```bash
# Vérifier que Docker est actif et que les ports clés sont libres
docker info --format '{{.ServerVersion}}' 2>&1 | head -1
lsof -i :8000 -i :8001 -i :8004 -i :8089 2>/dev/null | grep LISTEN | awk '{print $9, $1, $2}' | head -10 || echo "✅ Ports libres"
```

// turbo
```bash
# Vérifier que le mock_gemini et les prérequis perf sont présents
ls -la mock_gemini/main.py locust/locustfile.py locust/data/mock_cv_pool.json 2>&1
python3 -m flake8 scripts/local_up.py --max-line-length=120 --extend-ignore=W503,E501 2>&1 | head -5 || echo "⚠️ Violations flake8 détectées"
# Afficher l'état du seed (âge de seeded_ids.json)
python3 -c "
import os, time
p = 'locust/data/seeded_ids.json'
if os.path.exists(p):
    age_h = (time.time() - os.path.getmtime(p)) / 3600
    print(f'  seeded_ids.json : {age_h:.1f}h (skip auto si < 24h)')
else:
    print('  seeded_ids.json absent → seed complet au prochain run')
" 2>&1
```

---

### Étape 1 : Tests unitaires du pipeline perf (sans Docker)

// turbo
```bash
# Valider les tests unitaires du pipeline perf avant de lancer la charge
cd cv_api && python3 -m pytest tests/test_perf_pipeline.py tests/test_mock_gemini_config.py \
  -v --tb=short 2>&1 | tail -20
```

**Si des tests échouent ici** → stopper et corriger avant de lancer la charge complète.

---

### Étape 2 : Test de performance standard (50 users — ~3 min ou ~30s si seed skippé)

Lancement du pipeline complet : pull des dernières images AR + seed intelligent + Locust 50 users 1 min.
Le seed est automatiquement skippé si les données sont détectées en base (probe API).

// turbo
```bash
python3 scripts/local_up.py --perf 2>&1 | tee /tmp/perf_run.log
```

> La comparaison automatique avec les runs précédents s'affiche en fin de run.

---

### Étape 3 : Lecture des résultats de performance standard

// turbo
```bash
# Lire le rapport CSV généré
ls -la locust/results/ 2>&1
echo "=== STATS ===" && cat locust/results/perf_stats_stats.csv 2>/dev/null || echo "Fichier non trouvé"
echo "=== FAILURES ===" && cat locust/results/perf_stats_failures.csv 2>/dev/null || echo "Aucune erreur"
echo "=== LOG RÉSUMÉ ===" && cat /tmp/perf_run.log | tail -80
```

// turbo
```bash
# Comparaison manuelle enrichie (N derniers runs)
python3 scripts/compare_runs.py --runs 5 2>&1
```

---

### Étape 4 : Test de stress distribué (500 users — ~8 min)

> ⚠️ Ce test est plus long. Lancer uniquement après validation du test standard (étape 2).
> Le seed est auto-skippé si les données sont déjà en base (probe API).

// turbo
```bash
python3 scripts/local_up.py --stress 2>&1 | tee /tmp/stress_run.log
```

// turbo
```bash
# Résultats stress + comparaison automatique perf vs stress
echo "=== STATS STRESS ===" && cat locust/results/perf_stats_stats.csv 2>/dev/null
echo "=== FAILURES STRESS ===" && cat locust/results/perf_stats_failures.csv 2>/dev/null
echo "=== COMPARAISON ===" && python3 scripts/compare_runs.py --runs 3 2>&1
```

---

### Étape 5 : Analyse complète et propositions d'améliorations

L'agent doit lire tous les fichiers de résultats et produire **un rapport d'analyse structuré** :

// turbo
```bash
# Lire le rapport JSON enrichi si disponible
cat locust/results/perf_report.json 2>/dev/null | python3 -m json.tool | head -100 || echo "Pas de rapport JSON"

# Vérifier les logs de services pour identifier les erreurs côté serveur
docker-compose logs --tail=50 cv_api 2>/dev/null | grep -E "ERROR|WARNING|500|Exception" | tail -20
docker-compose logs --tail=50 missions_api 2>/dev/null | grep -E "ERROR|WARNING|500|Exception|QueuePool|TimeoutError" | tail -20
docker-compose logs --tail=50 users_api 2>/dev/null | grep -E "ERROR|WARNING|500|Exception" | tail -20
```

**L'agent doit produire une analyse couvrant :**

1. **Taux d'erreur global** (objectif : < 5%) avec identification des endpoints en échec
2. **Latences P95 par endpoint** avec seuils :
   - ✅ OK : P95 < 1 000 ms
   - ⚠️ WARN : P95 entre 1 000 ms et 5 000 ms
   - ❌ CRIT : P95 > 5 000 ms
3. **Throughput global** (Requests/s) et capacité théorique
4. **Bottlenecks identifiés** (DB pool, LLM mock, réseau Docker, bcrypt)
5. **Propositions d'amélioration priorisées** (P1/P2/P3) avec fichier et ligne impactés
6. **Comparaison perf ↔ stress** (fournie automatiquement en fin de run)

**Format du rapport attendu :**

```markdown
## Rapport Performance — <date>

### Vue d'ensemble
| Métrique | Perf (50u) | Stress (500u) | Δ |
|---|---|---|---|
| Req/s | X | X | +X% |
| Erreurs % | X% | X% | +X% |
| P95 median | Xms | Xms | ×X |

### Endpoints critiques
- **[CRIT] GET /missions** : P95 = Xms → cause : QueuePool exhaustion
- **[WARN] GET /users/me** : P95 = Xms → cause : bcrypt sync

### Propositions P1 (bloquant)
1. **missions_api** : DB_POOL_SIZE manquant → ajouter dans docker-compose + cr_missions.tf

### Propositions P2 (performance)
1. **items_api** : index manquant sur user_id

### Propositions P3 (long terme)
1. Cache Redis pour /missions/
```

---

### Étape 6 : Application des corrections P1

L'agent applique les corrections P1 identifiées à l'étape 5, puis relance uniquement
le test standard (étape 2) pour valider l'amélioration.

// turbo
```bash
# Relancer avec pull des dernières images — seed auto-skippé si données OK en base
python3 scripts/local_up.py --perf 2>&1 | tee /tmp/perf_rerun.log
# La comparaison automatique s'affiche en fin de run
```

// turbo
```bash
# Comparaison explicite avant/après (3 derniers runs)
python3 scripts/compare_runs.py --runs 3 2>&1
```

---

### Résumé attendu en fin de workflow

```
📊 Performance — <date>
  Mode perf     : XX req/s, P95=XXms, Erreurs=X%
  Mode stress   : XX req/s, P95=XXms, Erreurs=X%
Endpoints CRIT : <liste avec root cause>
Endpoints WARN : <liste>
P1 appliqués  : <liste des corrections avec fichiers>
Seed : skippé (données < 24h) | complet (Nh depuis le dernier)
Prochaine action : relancer stress ou corriger P2
```
