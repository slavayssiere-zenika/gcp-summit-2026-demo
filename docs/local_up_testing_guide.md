# Guide de Tests de Performance — `local_up.py`

> **Audience** : Développeurs et SREs souhaitant reproduire, analyser ou étendre le cycle de tests de charge en local.
> **Référence code** : [`scripts/local_up.py`](../scripts/local_up.py) · [`locust/locustfile.py`](../locust/locustfile.py) · [`scripts/compare_runs.py`](../scripts/compare_runs.py) · [`scripts/init_pubsub_emulator.py`](../scripts/init_pubsub_emulator.py)

> [!NOTE]
> Ce guide décrit le comportement **implémenté** du script (état mai 2026). Toutes les fonctionnalités décrites — archivage CSV, session log, healthcheck dynamique, `compare_runs.py` automatique et émulateur Pub/Sub — sont présentes dans le code.

---

## Table des matières

1. [Vue d'ensemble du cycle complet](#1-vue-densemble-du-cycle-complet)
2. [Prérequis](#2-prérequis)
3. [Étape 1 — Pull des dernières images](#3-étape-1--pull-des-dernières-images)
4. [Étape 2 — Seed conditionnel des données](#4-étape-2--seed-conditionnel-des-données)
5. [Étape 3 — Démarrage de l'environnement local](#5-étape-3--démarrage-de-lenvironnement-local)
6. [Étape 4 — Test de perf standard (50 users / 5 min)](#6-étape-4--test-de-perf-standard-50-users--5-min)
7. [Étape 5 — Test d'ingestion de 3 000 CVs](#7-étape-5--test-dingestion-de-3-000-cvs)
8. [Étape 6 — Test de stress (500 users)](#8-étape-6--test-de-stress-500-users)
9. [Étape 7 — Analyse des traces (Grafana / Tempo)](#9-étape-7--analyse-des-traces-grafana--tempo)
10. [Étape 8 — Comparaison avec les runs précédents](#10-étape-8--comparaison-avec-les-runs-précédents)
11. [Étape 9 — Génération du rapport](#11-étape-9--génération-du-rapport)
12. [Commandes de référence rapide](#12-commandes-de-référence-rapide)
13. [Émulateur Pub/Sub GCP — tests de contrat](#13-émulateur-pubsub-gcp--tests-de-contrat)

---

## 1. Vue d'ensemble du cycle complet

Le mode `--full` de `local_up.py` enchaîne **trois phases** de test dans l'ordre :

```
┌───────────────────────────────────────────────────────────────────────┐
│  local_up.py --full                                                    │
│                                                                        │
│  ① Pull images AR + frontend GCS    (smart pull — skip si à jour)     │
│  ② docker-compose up -d             (recréation avec --remove-orphans) │
│  ③ Healthcheck dynamique            (wait_for_services, max 90s)      │
│  ④ Seed conditionnel                (skip si DB ≥ 80% peuplée)        │
│                                                                        │
│  PHASE 1 ─ Perf standard                                              │
│    50 users | spawn 10/s | 3 min | scénario "full"                    │
│    mock LLM latency = 1s                                              │
│    → archive CSV + compare_runs.py                                    │
│                                                                        │
│  PHASE 2 ─ Ingestion dédiée                                           │
│    30 workers | auto-stop à 3 000 CVs | timeout 20 min               │
│    mock LLM latency = 1s                                              │
│                                                                        │
│  PHASE 3 ─ Stress distribué                                           │
│    500 users (1 master + 3 workers) | spawn 5/s | 5 min              │
│    navigation pure (ZenikaPerfUser) | mock LLM latency = 3s          │
│    → archive CSV + compare_runs.py                                    │
│                                                                        │
│  ⑤ Log de session : locust/results/session_YYYYMMDD_HHMMSS.log       │
└───────────────────────────────────────────────────────────────────────┘
```

**Fichiers produits** :
| Fichier | Description |
|---|---|
| `locust/results/perf_stats_stats.csv` | Statistiques par endpoint (P50, P95, P99, RPS, erreurs) |
| `locust/results/perf_stats_failures.csv` | Détail des erreurs HTTP rencontrées |
| `locust/results/perf_report.html` | Rapport Locust interactif (graphiques temps réel) |
| `locust/results/history/YYYYMMDD_HHMM_*.csv` | Historique pour comparaison |
| `locust/results/session_*.log` | Logs bruts de chaque session |

---

## 2. Prérequis

### Dépendances locales

```bash
# Docker Desktop (ou Docker Engine) avec docker-compose v2+
docker --version        # >= 24.x
docker-compose version  # >= 2.x

# gcloud SDK (pour pull depuis Artifact Registry)
gcloud --version        # >= 495.x
export GCLOUD_BIN=/Users/sebastien.lavayssiere/Apps/google-cloud-sdk/bin/gcloud

# Python 3.11+ (pour local_up.py et seed_data.py)
python3 --version
```

### Accès GCP

```bash
# Authentification préalable (ADC)
gcloud auth application-default login
gcloud auth configure-docker europe-west1-docker.pkg.dev
```

### Ressources recommandées

| Ressource | Recommandé (--full) | Minimum (--perf) |
|---|---|---|
| CPU | 8 cœurs | 4 cœurs |
| RAM | 16 GB | 8 GB |
| Disque | 20 GB libres | 10 GB libres |
| Réseau | 100 Mbps | 20 Mbps |

---

## 3. Étape 1 — Pull des dernières images

### Comportement automatique

`local_up.py` implémente un **smart pull** : il ne tire depuis Artifact Registry que les images localement absentes.

```python
# Logique dans ensure_images()
if force_pull:           # --no-pull absent = force_pull=True par défaut
    authenticate_docker()
    pull_and_tag(services)
else:
    missing = all_images_present(services)
    if missing:
        pull_and_tag(missing)  # pull partiel
    # sinon skip
```

### Images récupérées

| Image | Source AR | Usage |
|---|---|---|
| `agent_hr_api` | `europe-west1-docker.pkg.dev/…` | Sous-agent RH |
| `agent_missions_api` | idem | Sous-agent missions |
| `agent_ops_api` | idem | Sous-agent ops |
| `agent_router_api` | idem | Routeur IA |
| `analytics_mcp` | idem | Tracking FinOps |
| `competencies_api` | idem | Compétences |
| `cv_api` | idem | Import et profils CV |
| `db_migrations` | idem | Liquibase changelogs |
| `drive_api` | idem | Synchro Google Drive |
| `items_api` | idem | Items et catégories |
| `missions_api` | idem | Missions clients |
| `monitoring_mcp` | idem | SRE & Observabilité |
| `prompts_api` | idem | System prompts agents |
| `users_api` | idem | Auth & utilisateurs |

Les **sidecars MCP** partagent l'image de leur API parente et sont re-tagés automatiquement (`competencies_mcp → competencies_api`, etc.).

### Frontend

Le frontend est récupéré depuis **GCS** (bucket `z-gcp-summit-frontend`) :

```
latest_name = dernière archive .tar.gz (tri lexico)
si local .local_version == latest_name → skip
sinon → gcloud storage cp + tar -xzf → frontend/dist/
```

### Commandes

```bash
# Pull complet (par défaut)
python3 scripts/local_up.py

# Skip le pull (utiliser les images locales existantes)
python3 scripts/local_up.py --no-pull

# Pull partiel pour un seul service
python3 scripts/local_up.py --service users_api cv_api
```

---

## 4. Étape 2 — Seed conditionnel des données

### Philosophie : fail-safe à 2 niveaux

Le seed n'est exécuté que si la base est **réellement vide ou incomplète**, évitant d'écraser les données existantes.

```
Niveau 1 — Login admin (avec retry)
  ├─ Erreur réseau (timeout, refused) → service pas prêt → retry (max 3, délai 10s)
  ├─ HTTP 4xx → admin absent → DB vide → seed requis
  └─ HTTP 200 → token obtenu → passer au niveau 2

Niveau 2 — Spot-check 10 user IDs depuis seeded_ids.json
  ├─ ≥ 80% OK → DB confirmée → seed ignoré ✅
  └─ < 80% OK → DB incomplète → seed requis
```

### Contenu du seed perf

| Ressource | Volume (--perf) | Volume (standard) |
|---|---|---|
| Utilisateurs | 400 | 12 |
| Catégories | ~10 | ~10 |
| Items | 2 000 | 50 |
| Compétences | Arbre Zenika complet | idem |
| Profils CV synthétiques | 400 (insert direct DB) | 12 |
| Prompts agents | Tous | Tous |
| Dossier Drive (Niort) | 1 | 1 |

### Sortie produite

`locust/data/seeded_ids.json` — référentiel partagé avec `locustfile.py` :
```json
{
  "user_ids": [1, 2, ..., 400],
  "cv_profile_user_ids": [1, 2, ..., 400],
  "category_ids": [1, 2, ..., 10],
  "item_ids": [1, 2, ..., 2000],
  "mission_ids": []
}
```

### Forcer le reseed

```bash
# Reseed même si DB peuplée (utile après un changement de schéma)
python3 scripts/local_up.py --perf --erase

# Seed uniquement, sans relancer docker-compose
python3 scripts/local_up.py --seed-perf
```

---

## 5. Étape 3 — Démarrage de l'environnement local

### Commande générée

```bash
docker-compose up -d --no-build --remove-orphans
```

- `--no-build` : **aucun rebuild local** — les images doivent déjà être présentes (pullées à l'étape 1).
- `--remove-orphans` : force la recréation des containers si la config `docker-compose.yml` a changé (nouvelles variables d'environnement, ports, etc.).
- Le **frontend** est servi par Nginx depuis `frontend/dist/` (volume monté).

### Healthcheck dynamique (remplace le sleep fixe)

Après `compose_up()`, `wait_for_services(max_wait_s=90)` poll les endpoints `/health` de trois services critiques jusqu'à ce qu'ils soient tous à 200, ou timeout :

| Service | URL healthcheck | Critique |
|---|---|---|
| `users_api` | `http://localhost:8000/health` | ✅ |
| `cv_api` | `http://localhost:8004/health` | ✅ |
| `items_api` | `http://localhost:8001/health` | ✅ |

Retry toutes les **3 secondes**, timeout à **90 secondes**. Si un service reste indisponible, l'exécution continue avec un avertissement (pas de fail-fast — le seed gérera l'échec).

---

## 6. Étape 4 — Test de perf standard (50 users / 5 min)

> **Note** : La configuration actuelle est 3 min. L'objectif documenté est 5 min. Pour passer à 5 min, modifier `LOCUST_DURATION = "5m"` dans `local_up.py`.

### Paramètres

| Paramètre | Valeur | Description |
|---|---|---|
| `LOCUST_USERS` | 50 | Utilisateurs virtuels concurrents |
| `LOCUST_SPAWN_RATE` | 10/s | Montée en charge (50 users en 5s) |
| `LOCUST_DURATION` | 3 min | Durée (configurable → 5 min) |
| `LOCUST_SCENARIO` | `full` | ZenikaPerfUser (75%) + CVIngestionPipelineUser (25%) |
| `MOCK_LLM_LATENCY_MAX_S` | 1s | Latence mock LLM (feedback rapide) |
| `LOCUST_CV_TARGET` | 120 | CVs ingérés attendus en 3 min |

### Scénario `full`

**ZenikaPerfUser (weight=3, 75%)** — Navigation utilisateur :
- `GET /users/` (pagination, contrat Pydantic)
- `GET /items/` (pagination)
- `GET /competencies/`
- `GET /cv/user/{id}` (profil CV + missions)
- `GET /missions/`
- `GET /cv/bulk-reanalyse/data-quality` (endpoint lourd, cache Redis)
- `GET /cv/analytics/skills-coverage` (agrégation lourde)
- `GET /items/search/query` (recherche + validation sémantique)
- + 10 autres endpoints READ

**CVIngestionPipelineUser (weight=1, 25%)** — Pipeline ingestion :
1. `POST /users/` → création du candidat
2. `POST /cv/import` → upload CV (mock_gemini)
3. `POST /competencies/user/{id}/assign/bulk` → 30 compétences
4. `POST /missions` × 45 → fiches de mission
5. `POST /items/bulk` × 5 → items liés
6. `GET /cv/user/{id}` → validation
7. `GET /competencies/stats/coverage` → analytics (1/10)

### Lancement

```bash
# Phase 1 uniquement
python3 scripts/local_up.py --perf

# Ou via le mode full
python3 scripts/local_up.py --full
```

**Interface web** : http://localhost:8089 (disponible en temps réel pendant le test)

### Résultats attendus (seuils OK)

| Métrique | WARN | CRIT |
|---|---|---|
| P95 latence | > 1 000 ms | > 5 000 ms |
| Taux d'erreur global | > 5% | > 15% |

---

## 7. Étape 5 — Test d'ingestion de 3 000 CVs

### Paramètres

| Paramètre | Valeur | Description |
|---|---|---|
| `LOCUST_INGESTION_USERS` | 30 | Workers d'ingestion parallèles |
| `LOCUST_INGESTION_SPAWN` | 5/s | Montée progressive |
| `LOCUST_INGESTION_TIMEOUT` | 20 min | Timeout de sécurité |
| `LOCUST_CV_TARGET_INGESTION` | 3 000 | Auto-stop quand atteint |
| `MOCK_LLM_LATENCY_MAX_S` | 1s | Latence réduite pour maximiser le débit |

### Architecture de l'auto-stop

Le runner s'arrête automatiquement quand `CV_TARGET` est atteint :

```python
# Dans locustfile.py — CVIngestionPipelineUser.ingest_cv_pipeline()
CVIngestionPipelineUser._cv_count += 1
if _SCENARIO == "ingestion" and cv_num >= self.CV_TARGET:
    self.environment.runner.quit()
```

Capacité théorique avec latence 1s :
```
30 workers × 20 min / ~3s par pipeline = ~1 200 CVs
→ Avec 3 workers/CPU et latence 1s : ~3 000 CVs en ~10-15 min
```

### Ce qui est stressé

- Semaphore `BULK_ENDPOINT_SEMAPHORE` de `items_api` (slots limités → 429 attendus)
- Pool de connexions DB sur `users`, `competencies`, `missions`, `cv`
- Background tasks `mock_gemini` (pipeline LLM simulé)
- Cache Redis sur les endpoints de lecture analytics

### Lancement dédié

```bash
# Phase 2 uniquement (sans relancer la stack)
python3 scripts/local_up.py --no-pull
# puis dans un second terminal :
cd /path/to/project
LOCUST_SCENARIO=ingestion docker-compose --profile perf run --rm \
  -e LOCUST_SCENARIO=ingestion \
  -e LOCUST_CV_TARGET=3000 \
  -e MOCK_LLM_LATENCY_MAX_S=1 \
  locust \
  -f /locust/locustfile.py --autostart --autoquit 5 \
  -u 30 -r 5 -t 20m \
  --csv /locust/results/perf_stats --host http://localhost
```

---

## 8. Étape 6 — Test de stress (500 users)

### Paramètres

| Paramètre | Valeur | Description |
|---|---|---|
| `LOCUST_STRESS_USERS` | 500 | Utilisateurs virtuels |
| `LOCUST_STRESS_SPAWN_RATE` | 5/s | Montée progressive (~100s) |
| `LOCUST_STRESS_DURATION` | 5 min | Durée |
| `LOCUST_STRESS_WORKERS` | 3 | Workers distribués |
| `MOCK_LLM_LATENCY_MAX_S` | 3s | Latence réaliste (simule la prod) |
| `LOCUST_SCENARIO` | `navigation` | ZenikaPerfUser uniquement (READ) |

### Architecture distribuée

```
locust-master (docker-compose) ←──── Web UI :8089
       ├── locust-worker-1 (docker-compose --scale 3)
       ├── locust-worker-2
       └── locust-worker-3
       
Réseau : monitoring_net (DNS resolution locust-master)
```

- **Master** : coordinateur, génère le rapport HTML, attend les workers.
- **Workers** : exécutent les requêtes HTTP en parallèle, connectés au master par TCP.
- **`docker wait locust-master`** : le script attend la fin du master de façon bloquante.
- Les résultats sont copiés via `docker cp locust-master:/locust/results/. …` avant suppression.

### Règle de dimensionnement workers

```
500 users / 170 users/worker ≈ 3 workers
Machine : 12 CPUs, services ~6 CPUs → 3 workers sans contention
```

### Lancement

```bash
# Stress test uniquement
python3 scripts/local_up.py --stress

# Dans le mode full (phase 3 automatique)
python3 scripts/local_up.py --full
```

---

## 9. Étape 7 — Analyse des traces (Grafana / Tempo)

### Accès aux outils d'observabilité

| Service | URL locale | Credentials |
|---|---|---|
| Grafana | http://localhost:3000 | admin / admin |
| Tempo (traces) | via Grafana → Explore → Tempo | — |
| Prometheus | http://localhost:9090 | — |
| Promtail / Loki | via Grafana → Explore → Loki | — |

### Workflow d'analyse des traces

1. **Pendant un test** : accéder à Grafana → Explore → Tempo
2. **Recherche par service** : filtrer sur `service.name=cv_api` ou `agent_router_api`
3. **Identifier les spans lents** : trier par durée décroissante
4. **Waterfall view** : visualiser les appels inter-services (cv_api → mock_gemini, cv_api → missions_api, etc.)

### Métriques clés à surveiller

```
# Prometheus queries utiles pendant les tests
rate(http_requests_total[1m])          # RPS par service
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))  # P95
rate(http_requests_total{status=~"5.."}[1m])  # Taux d'erreur 5xx
pg_pool_size                            # Pool DB (via prometheus-client)
```

### Corrélation traces → logs

Dans Grafana, activer la **corrélation Tempo → Loki** :
- Cliquer sur un span → "View Logs" → les logs du même `trace_id` s'affichent

### Points d'attention spécifiques

| Symptôme | Probable cause | Investigation |
|---|---|---|
| Span `cv_api` très long | mock_gemini saturé | Augmenter `MOCK_LLM_LATENCY_MAX_S=0` |
| 429 sur `/items/bulk` | Semaphore saturé | `BULK_ENDPOINT_SEMAPHORE` trop petit |
| P95 login > 2s | bcrypt CPU-bound | Cache Redis de session ou pre-login |
| Connection pool exhausted | `DB_POOL_SIZE` trop petit | Variable d'env dans docker-compose |

---

## 10. Étape 8 — Comparaison avec les runs précédents

### Archivage automatique (fonction `archive_results()`)

Après chaque run Locust réussi, `archive_results()` copie automatiquement les fichiers suivants dans `locust/results/history/` avec un préfixe horodaté `YYYYMMDD_HHMM_` :

| Fichier source | Description |
|---|---|
| `perf_stats_stats.csv` | Statistiques par endpoint |
| `perf_stats_failures.csv` | Erreurs HTTP |
| `perf_stats_exceptions.csv` | Exceptions Locust |
| `perf_report.json` | Rapport JSON exporté |

```
locust/results/history/
  20260518_1341_perf_stats_stats.csv
  20260518_1341_perf_stats_failures.csv
  20260519_2000_perf_stats_stats.csv
  20260519_2000_perf_stats_failures.csv
  ...
```

### Appel automatique

`run_compare()` est appelée automatiquement dans `main()` après chaque `display_results()` + `archive_results()`. Elle lance `compare_runs.py` avec `stdout` passthrough — le diff s'affiche dans le terminal et dans le log de session.

### Utilisation manuelle de `compare_runs.py`

```bash
# Comparer les 2 derniers runs (par défaut)
python3 scripts/compare_runs.py

# Comparer les 5 derniers runs
python3 scripts/compare_runs.py --runs 5

# Lister les runs disponibles
python3 scripts/compare_runs.py --list

# Sortie Markdown brute (pour copier dans un rapport)
python3 scripts/compare_runs.py --md
```

### Format de sortie

```markdown
### Vue d'ensemble (Aggregated)

| Métrique | Run 20260519_2000 | Run 20260518_1341 | Δ (dernier vs précédent) |
|---|---|---|---|
| **Req/s**     | 45.2 | 38.1 | +18.6% ✅ |
| **P50 (ms)**  | 120ms | 145ms | -17.2% ✅ |
| **P95 (ms)**  | 890ms | 1200ms | -25.8% ✅ |
| **Erreurs %** | 0.2% | 3.1% | -93.5% ✅ |

### Endpoints — évolution détaillée
| Endpoint | P95 | ΔP95 |
|---|---|---|
| ✅ [CV] GET /user/{id} | 450ms | -30% 📉 |
| ⚠️ [Items] GET /items/ | 1200ms | +8% |
```

**Icônes de tendance** :
- `📉` = amélioration ≥ 10%
- `📈` = régression ≥ 10%
- `✅` P95 < 1s / `⚠️` entre 1s et 5s / `❌` > 5s

---

## 11. Étape 9 — Génération du rapport

### Log de session (automatique)

Chaque exécution de `local_up.py` crée un fichier `locust/results/session_YYYYMMDD_HHMMSS.log` qui capture **tous les messages horodatés** de la session :

```
# local_up.py session — 2026-05-19 21:04:58
# PID=92512  CMD=--perf

[21:04:58] Mode : perf
[21:06:13] docker-compose up terminé.
[21:06:17] Données en base confirmées — seed ignoré.
[21:07:25] Résultats archivés dans history/ (préfixe 20260519_2104)
[21:07:25] ✨ local_up.py terminé.
```

### Rapport inline (display_results)

Affiché automatiquement en console après chaque phase :

```
================================================================================
RESULTATS DE PERFORMANCE
================================================================================
Endpoint                               Req/s   Fail%  Median(ms) 95%(ms)  99%(ms)  Max(ms) Errors
[CV] GET /bulk-reanalyse/data-quality  2.1     0.0    890        1240     1890     3200    0
[Items] GET /items/search/query        8.3     0.0    120        450      890      1200    0
...
================================================================================

## Rapport Locust -- 2026-05-19 20:00

### Vue d'ensemble

| Metrique          | Valeur |
|---|---|
| Requetes totales  | 12450 |
| Requetes/s        | 41.5 |
| Echecs            | 25 (0.2%) [OK] |

### Actions prioritaires

1. Aucun point bloquant detecte.
```

### Rapport HTML interactif

Accessible sur http://localhost:8089 pendant le test, exporté en `perf_report.html` après.

### Export Markdown pour CR

```bash
# Générer la comparaison en Markdown copiable
python3 scripts/compare_runs.py --md > /tmp/perf_report_$(date +%Y%m%d).md
```

---

## 12. Commandes de référence rapide

```bash
# ─── MODES PRINCIPAUX ──────────────────────────────────────────────────────────

# Démarrage complet (pull + up)
python3 scripts/local_up.py

# Démarrage sans re-pull
python3 scripts/local_up.py --no-pull

# Perf standard (50 users, 3 min)
python3 scripts/local_up.py --perf

# Stress (500 users, 5 min)
python3 scripts/local_up.py --stress

# Cycle complet (3 phases)
python3 scripts/local_up.py --full

# Cycle complet avec reseed forcé
python3 scripts/local_up.py --full --erase

# ─── SEED STANDALONE ───────────────────────────────────────────────────────────

# Seed standard (12 users)
python3 scripts/local_up.py --seed

# Seed perf (400 users, 2000 items)
python3 scripts/local_up.py --seed-perf

# ─── COMPARAISON ───────────────────────────────────────────────────────────────

# 2 derniers runs
python3 scripts/compare_runs.py

# 5 derniers runs
python3 scripts/compare_runs.py --runs 5

# Lister l'historique
python3 scripts/compare_runs.py --list
```

---

## 13. Émulateur Pub/Sub GCP — tests de contrat

### Pourquoi un émulateur plutôt qu'un mock Python

En mode perf normal, `drive_api` bypasse Pub/Sub (`PUBSUB_CV_IMPORT_TOPIC` vide → fallback `PENDING`) et Locust appelle `POST /cv/import` directement. L'émulateur GCP permet de tester le **flux complet réel** :

```
drive_api.IngestionService.ingest_batch()
  └─► pubsub_v1.PublisherClient().publish(topic, payload_json)
      └─► Émulateur (localhost:8085) → push HTTP
          └─► cv_api POST /pubsub/import-cv
              └─► PubsubService._run_cv_pipeline_bg()
                  └─► PATCH drive_api /files/{id} (IMPORTED_CV | ERROR)
```

### Composants implémentés

#### Service `pubsub-emulator` dans [`docker-compose.yml`](../docker-compose.yml)

```yaml
pubsub-emulator:
  image: gcr.io/google.com/cloudsdktool/cloud-sdk:emulators
  container_name: pubsub_emulator
  hostname: pubsub_emulator
  command: gcloud beta emulators pubsub start --host-port=0.0.0.0:8085 --project=test-project
  ports:
    - "8085:8085"
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8085/v1/projects"]
    interval: 5s
    timeout: 3s
    retries: 12
    start_period: 10s
  profiles:
    - perf
    - perf-stress
  networks:
    - monitoring_net
```

Démarre automatiquement avec `--profile perf` et `--profile perf-stress`.

#### Script [`scripts/init_pubsub_emulator.py`](../scripts/init_pubsub_emulator.py)

Crée les topics et la subscription push dans l'émulateur :

| Ressource | Valeur |
|---|---|
| Topic | `projects/test-project/topics/cv-import-topic` |
| Topic DLQ | `projects/test-project/topics/cv-import-dlq` |
| Subscription push | `projects/test-project/subscriptions/cv-import-sub` |
| Push endpoint | `http://cv_api:8004/pubsub/import-cv` |
| Max delivery attempts | 5 (puis DLQ) |
| Ack deadline | 600s (pipeline LLM peut être long) |

#### Fichier [`.env.perf`](../.env.perf)

```bash
PUBSUB_EMULATOR_HOST=pubsub_emulator:8085   # DNS interne Docker
PUBSUB_CV_IMPORT_TOPIC=cv-import-topic
GCP_PROJECT_ID=test-project
PUBSUB_INVOKER_SA_EMAIL=mock@test.iam.gserviceaccount.com
PUBSUB_CV_IMPORT_AUDIENCE=local-test        # Bypass OIDC en local
```

### Workflow d'activation

```bash
# 1. Démarrer avec l'émulateur (profil perf)
docker-compose --env-file .env.perf --profile perf up -d

# 2. Attendre que l'émulateur soit prêt, puis créer topics + subscription
PUBSUB_EMULATOR_HOST=localhost:8085 python3 scripts/init_pubsub_emulator.py

# 3. Déclencher une ingestion Drive (publie sur Pub/Sub)
curl -X POST http://localhost:8006/api/drive/sync  \
     -H "Authorization: Bearer <JWT>"  # force un batch drive_api

# 4. Observer le pipeline en direct
docker logs cv_api --follow | grep -E "PubSub|IMPORTED_CV|ERROR"

# 5. Lancer les tests perf (pipeline Pub/Sub actif)
python3 scripts/local_up.py --perf --no-pull
```

### Comment les données Pub/Sub sont vérifiées

L'émulateur GCP expose une **API REST d'inspection** sur `http://localhost:8085`. Elle permet de vérifier post-test que les messages ont bien transité et ont le bon format.

#### 1 — Lire les messages non-ackés (DLQ ou backlog)

```bash
# Pull les messages restants dans la subscription (non-ackés = erreurs cv_api)
curl -X POST http://localhost:8085/v1/projects/test-project/subscriptions/cv-import-sub:pull \
  -H "Content-Type: application/json" \
  -d '{"maxMessages": 100}'
```

Si des messages sont présents → `cv_api` n'a pas pu les traiter (erreur pipeline, OIDC, DB).

#### 2 — Inspecter la DLQ (messages échoués × 5 tentatives)

```bash
# Créer une subscription temporaire sur la DLQ
curl -X PUT http://localhost:8085/v1/projects/test-project/subscriptions/dlq-inspect \
  -H "Content-Type: application/json" \
  -d '{"topic": "projects/test-project/topics/cv-import-dlq"}'

# Lire les messages de la DLQ
curl -X POST http://localhost:8085/v1/projects/test-project/subscriptions/dlq-inspect:pull \
  -H "Content-Type: application/json" \
  -d '{"maxMessages": 50}'
```

Messages en DLQ → format invalide ou `cv_api` retourne 5xx en permanence.

#### 3 — Validation de contrat via [`scripts/validate_pubsub_emulator.py`](../scripts/validate_pubsub_emulator.py)

Script autonome qui interroge l'émulateur REST, décode les payloads base64, et valide le schéma :

```bash
# Validation de base (subscription principale)
python3 scripts/validate_pubsub_emulator.py

# Avec inspection de la DLQ (messages échoués × 5 tentatives)
python3 scripts/validate_pubsub_emulator.py --dlq

# Vérification croisée drive_api + Pub/Sub
python3 scripts/validate_pubsub_emulator.py --dlq \
  --drive-api http://localhost:8006 \
  --token $(python3 scripts/mcp_cli.py auth)

# Options disponibles
python3 scripts/validate_pubsub_emulator.py --help
```

**Champs validés** :

| Champ | Type | Valeurs valides |
|---|---|---|
| `google_file_id` | str non-vide | — |
| `url` | str non-vide | — |
| `file_type` | enum | `google_doc`, `docx` |
| `action` | enum | `upsert`, `delete` |

**Codes de retour** : `0` = OK, `1` = violations détectées, `2` = émulateur inaccessible.

#### 4 — Vérification croisée drive_api ↔ cv_api

Après un cycle d'ingestion, comparer les statuts dans les deux bases :

```bash
# Statuts drive_api (via API)
curl http://localhost:8006/api/drive/files?limit=50 \
     -H "Authorization: Bearer <JWT>" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); \
    [print(f['google_file_id'], f['status']) for f in d.get('files',[])]"

# Attendu : IMPORTED_CV ou IGNORED_NOT_CV
# Si ERROR ou QUEUED après > 5 min → problème pipeline
```

### Point de vigilance — Validation OIDC en local

> [!WARNING]
> En production, `cv_api /pubsub/import-cv` valide un token OIDC Google RS256. Avec l'émulateur, la push subscription n'inclut pas de token OIDC réel. `PUBSUB_CV_IMPORT_AUDIENCE=local-test` contourne cette validation **uniquement en local**. Ne jamais déployer cette valeur en production.

### Ce que valide l'émulateur vs les tests existants

| Aspect | Tests unitaires Python | Émulateur GCP local |
|---|---|---|
| Format payload Pub/Sub | ✅ Mock Python | ✅ Flux réseau réel |
| Ack/Nack par cv_api | ❌ | ✅ Backoff réel |
| DLQ après 5 échecs | ❌ | ✅ Automatique |
| `MAX_PROCESSING_CONCURRENT` throttling | ❌ | ✅ Mesurable |
| Pipeline LLM complet | ❌ | ✅ Via mock_gemini |
| Patch final drive_api | ❌ | ✅ IMPORTED_CV / ERROR |

---

*Document mis à jour le 2026-05-20 — Maintenu par l'équipe SRE / Platform Engineering.*
