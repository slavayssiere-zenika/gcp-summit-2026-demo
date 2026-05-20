---
description: Lance les tests de performance et de stress locaux via local_up.py (mode perf + stress + full), analyse les rapports CSV générés et propose des améliorations architecturales concrètes.
---

Ce workflow orchestre un cycle complet de tests de performance local :
test de charge standard (50 users, 3 min), ingestion dédiée de 3 000 CVs (auto-stop),
et stress test distribué (500 users, 5 min), puis analyse les rapports pour
proposer des optimisations priorisées.

> **Pré-requis** : Docker Desktop actif, `local_up.py` accessible, images AR présentes.
> Ce workflow NE déploie PAS en production. Il est 100% local.

### 🏗️ Contexte d'exécution cible : Google Cloud Run

> [!IMPORTANT]
> Les tests locaux simulent la **production sur Cloud Run** (europe-west1). Toute proposition
> d'amélioration doit être évaluée dans ce contexte, pas dans un contexte serveur classique.

| Caractéristique | Local (Docker) | Production (Cloud Run) |
|---|---|---|
| **CPU par instance** | Multi-core Mac | **1 vCPU** par défaut (configurable 2-8) |
| **Concurrence** | Unlimited | `--concurrency 80` (FastAPI async) |
| **Scaling** | Manuel | **Scale-to-zero** automatique |
| **Instances** | 1 processus | 1 instance = 1 processus Python (uvicorn) |
| **Pool DB** | Local postgres | AlloyDB (max_connections à calculer depuis prd) |
| **Workers WSGI** | N/A (uvicorn) | **Uvicorn** (pas Gunicorn) — 1 seul worker par instance |

**Implications pour l'analyse :**

- **ThreadPoolExecutor bcrypt** : avec 1 vCPU par instance Cloud Run, le `ThreadPoolExecutor`
  par défaut a `min(32, cpu_count+4) = 5` workers. Sur Cloud Run 1 vCPU, un seul thread
  bcrypt tourne réellement à la fois (CPU-bound) → **le ThreadPoolExecutor est déjà correct**,
  ne jamais proposer de réduire `max_workers` car cela degraderait la concurrence async.
- **Pas de Gunicorn/unicorn multi-workers** : Cloud Run utilise `uvicorn` en processus unique.
  Les optimisations multi-workers (ex: Gunicorn `--workers N`) ne s'appliquent pas.
- **Latences locales vs prd** : les latences Docker local sont **supérieures** à la prd
  (réseau local, même machine). En prd, AlloyDB répond en ~1-3ms vs ~10-50ms en local.
- **LOCUST_INGESTION_USERS** : contrôle le **nombre de pipelines parallèles** (concurrence),
  pas la vitesse individuelle. 30 workers = 30 connexions DB simultanées. À aligner avec
  la capacité réelle du pool DB (`DB_POOL_SIZE` calculé depuis AlloyDB prd).

### Modes disponibles

| Flag | Phases | Durée totale |
|---|---|---|
| `--perf` | Perf 50 users 3 min | ~5 min (avec seed) |
| `--stress` | Stress 500 users 5 min | ~8 min |
| `--full` | Perf → Ingestion 3 000 CVs → Stress | ~25-30 min |
| `--perf --erase` | Reseed complet + Perf | ~8 min |

### Seed intelligent — comportement automatique

`local_up.py` inclut un **skip-seed par probe API réelle** : après le démarrage des services,
il tente un **login admin** (`admin@zenika.com` / `admin`) pour obtenir un JWT, puis sonde
**10 users aléatoires** issus de `seeded_ids.json` avec ce JWT.
Si ≥ 80 % répondent HTTP 200, les données sont confirmées en base → seed ignoré.
Cela couvre les cas de reset DB, rollback Liquibase ou redémarrage sur volume vierge.

> ⚠️ La simple existence de `seeded_ids.json` **ne prouve pas** que la DB est peuplée
> (le fichier est persistant sur le filesystem). Seule la probe API est fiable.

| Situation | Commande | Seed |
|---|---|---|
| Premier run (DB vide) | `--perf` | ✅ Seed complet |
| Runs suivants (données OK) | `--perf` | ⏭️ Skip automatique (probe admin login + JWT) |
| Forcer le reseed | `--perf --erase` | 🔄 Probe ignorée + reseed complet |
| Standalone sans docker-compose | `--seed-perf` | ✅ Seed perf uniquement |

### Scénarios Locust

| `LOCUST_SCENARIO` | Classes actives | Usage |
|---|---|---|
| `full` (défaut) | ZenikaPerfUser (75%) + CVIngestionPipelineUser (25%) | `--perf` |
| `navigation` | ZenikaPerfUser uniquement | `--stress` |
| `ingestion` | CVIngestionPipelineUser uniquement, auto-stop à `CV_TARGET` | Phase 2 de `--full` |

### Paramètres mock Gemini par mode

| Mode | `MOCK_LLM_LATENCY_MAX_S` | `MOCK_LLM_EMBED_LATENCY_MAX_S` | `LOCUST_CV_TARGET` |
|---|---|---|---|
| `--perf` | **1s** (feedback rapide) | 0s | 120 |
| `--stress` | **3s** (simulation prod) | 0s | 3000 |
| Phase ingestion (`--full`) | **1s** | 0s | **3000** (auto-stop) |

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
# Vérifier que les prérequis perf sont présents et flake8 propre
ls -la mock_gemini/main.py locust/locustfile.py locust/data/mock_cv_pool.json 2>&1
python3 -m flake8 scripts/local_up.py locust/locustfile.py \
  --max-line-length=120 --extend-ignore=W503,E501 2>&1 | head -10 || echo "⚠️ Violations flake8 détectées"
# Afficher l'état du fichier de référentiel (son existence ne prouve pas que la DB est peuplée)
python3 -c "
import os, time
p = 'locust/data/seeded_ids.json'
if os.path.exists(p):
    age_h = (time.time() - os.path.getmtime(p)) / 3600
    print(f'  seeded_ids.json présent ({age_h:.1f}h) — probe API requise pour confirmer la DB')
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

### Étape 2 : Test de performance standard (50 users — 3 min)

Lancement du pipeline complet : pull des dernières images AR + seed intelligent + Locust 50 users 3 min.
Le seed est automatiquement skippé si la probe API confirme les données en base
(login admin → JWT → spot-check 10 users → ≥ 80% HTTP 200).

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
> Le seed est auto-skippé via probe API si les données sont déjà en base.

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

### Étape 4bis (optionnelle) : Cycle complet 3 phases (--full, ~25-30 min)

Lance les 3 phases en séquence : perf → ingestion → stress.
L'ingestion s'arrête automatiquement quand 3 000 CVs sont ingérés (`runner.quit()` dans locustfile).

// turbo
```bash
python3 scripts/local_up.py --full 2>&1 | tee /tmp/full_run.log
```

// turbo
```bash
echo "=== LOG COMPLET ===" && cat /tmp/full_run.log | tail -120
python3 scripts/compare_runs.py --runs 5 2>&1
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
4. **Bottlenecks identifiés** (DB pool, LLM mock, réseau Docker)
5. **Propositions d'amélioration priorisées** (P1/P2/P3) avec fichier et ligne impactés
6. **Comparaison perf ↔ ingestion ↔ stress** (fournie automatiquement en fin de run)

> ⚠️ **Avant de proposer une action corrective, vérifier si elle n'est pas déjà implémentée** :
> - Index HNSW sur `cv_profiles(embedding)` → déjà présent (`db_migrations/changelogs/cv/changelog.yaml`)
> - bcrypt async via `ThreadPoolExecutor` → déjà présent (`users_api/src/auth.py`)
> - **Réduire `max_workers` du ThreadPoolExecutor bcrypt** → **INTERDIT sur Cloud Run** :
>   1 vCPU = 1 thread CPU à la fois, le default est déjà optimal. Réduire dégraderait la concurrence async.
> - **Proposer Gunicorn multi-workers** → **NON PERTINENT** : Cloud Run utilise uvicorn (1 processus).
> - `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` → **NE JAMAIS proposer de valeur arbitraire.**
>   Ces paramètres sont calculés depuis la configuration AlloyDB de production (voir bloc ci-dessous).
>   Toute recommendation se limite à signaler une anomalie et renvoyer vers le calcul prd.

> [!CAUTION]
> **Règle DB Pool — INTERDICTION de hardcoder des valeurs**
> `DB_POOL_SIZE` et `DB_MAX_OVERFLOW` ne doivent jamais être modifiés sans d'abord consulter
> la capacité AlloyDB réelle en production. La formule est :
> `DB_POOL_SIZE = floor(alloydb_max_connections / nb_instances_cloud_run / nb_services_partageant_la_db)`
> Récupérer les paramètres AlloyDB prd avec :
> ```bash
> GCLOUD_BIN=/Users/sebastien.lavayssiere/Apps/google-cloud-sdk/bin/gcloud
> $GCLOUD_BIN alloydb instances describe primary \
>   --cluster=zenika-cluster --region=europe-west1 \
>   --project=prod-ia-staffing \
>   --format="yaml(databaseFlags,machineConfig)"
> ```
> Si le `max_connections` AlloyDB est inconnu, **ne pas toucher** `DB_POOL_SIZE` et le noter
> dans le rapport sous "Investigations requises".

> [!CAUTION]
> **Règle Cache Redis — INTERDICTION de proposer du cache comme correctif de performance**
> Ajouter du cache Redis pour améliorer un P95 élevé détecté pendant un tir de perf/stress est
> **formellement interdit comme action corrective**. Raisons :
> 1. Le cache se "réchauffe" pendant le tir → les métriques s'améliorent artificiellement au fil du temps,
>    masquant la latence réelle de la requête froide.
> 2. Le cache cache le problème (requête SQL lente, N+1, index manquant) au lieu de le corriger.
> 3. Un cache mal invalidé introduit des incohérences de données en production.
>
> **Ce qui est autorisé à la place :**
> - Identifier et corriger la requête SQL lente (EXPLAIN ANALYZE, index manquant)
> - Corriger un pattern N+1 (jointure ou `selectinload` SQLAlchemy)
> - Ajouter un index PostgreSQL via une migration Liquibase
> - Réduire la complexité algorithmique (ex: groupby Python O(n) → GROUP BY SQL)
>
> **Exception** : si un cache Redis **existe déjà** sur l'endpoint et que la latence observée
> correspond à un cache miss structurel (cold start), signaler sous "Investigations requises".
> Ne jamais ajouter un nouveau cache pour compenser une latence SQL.


**Format du rapport attendu :**

```markdown
## Rapport Performance — <date>

### Vue d'ensemble
| Métrique | Perf (50u/3min) | Ingestion (30u) | Stress (500u/5min) |
|---|---|---|---|
| Req/s | X | X | X |
| Erreurs % | X% | X% | X% |
| P95 médian | Xms | Xms | Xms |
| CVs ingérés | ~X | X/3000 | N/A |

### Endpoints critiques
- **[CRIT] GET /cv/search** : P95 = Xms → cause : cold cache pgvector

### Propositions P1 (bloquant)
1. ...

### Propositions P2 (performance)
1. ...

### Propositions P3 (long terme)
1. ...
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
  Mode perf      : XX req/s, P95=XXms, Erreurs=X%, CV_TARGET=120 (1s latence)
  Mode ingestion : XX CVs/min, X/3000 CVs ingérés, auto-stop atteint : oui/non
  Mode stress    : XX req/s, P95=XXms, Erreurs=X%, (navigation pure)
Seed : skippé (probe admin OK, 10/10 users HTTP 200) | complet (login échoué ou DB vide)
Endpoints CRIT : <liste avec root cause>
Endpoints WARN : <liste>
P1 appliqués   : <liste des corrections avec fichiers>
Prochaine action : relancer --full ou corriger P2
```
