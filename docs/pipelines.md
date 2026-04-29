# 📦 Documentation des Pipelines CI/CD

> ⚙️ Document auto-généré le **2026-04-29 21:12 UTC** par `scripts/generate_pipeline_docs.py`.

> Ne pas éditer manuellement — vos modifications seront écrasées au prochain `/git-push`.

---

## 🌐 Matrice des Environnements

| Paramètre | **DEV** | **PRD** | **UAT** |
| --- | --- | --- | --- | --- |

### ☁️ GCP

| Paramètre | **DEV** | **PRD** | **UAT** |
| --- | --- | --- | --- | --- |
| `project_id` | `slavayssiere-sandbox-462015` | `prod-ia-staffing` | `slavayssiere-sandbox-462015` |
| `base_domain` | `zenika.slavayssiere.fr` | `zenika.slavayssiere.fr` | `zenika.slavayssiere.fr` |

### 🐳 Registre d'images

| Paramètre | **DEV** | **PRD** | **UAT** |
| --- | --- | --- | --- | --- |
| `image_registry` | `europe-west1-docker.pkg.dev/slavayssiere-sandbox-462015/z-gcp-summit-services` | `europe-west1-docker.pkg.dev/slavayssiere-sandbox-462015/z-gcp-summit-services` | `europe-west1-docker.pkg.dev/slavayssiere-sandbox-462015/z-gcp-summit-services` |

### 🚀 Cloud Run

| Paramètre | **DEV** | **PRD** | **UAT** |
| --- | --- | --- | --- | --- |
| `cloudrun_min_instances` | `1` | `0` | `1` |
| `cloudrun_max_instances` | `10` | `50` | `5` |

### 🗄️ AlloyDB

| Paramètre | **DEV** | **PRD** | **UAT** |
| --- | --- | --- | --- | --- |
| `alloydb_cpu` | `2` | `2` | `2` |

### 🛡️ Sécurité

| Paramètre | **DEV** | **PRD** | **UAT** |
| --- | --- | --- | --- | --- |
| `waf_rate_limit` | `2000` | `10000` | `1000` |

### 🤖 Modèles IA

| Paramètre | **DEV** | **PRD** | **UAT** |
| --- | --- | --- | --- | --- |
| `gemini_router_model` | `gemini-3.1-pro-preview"` | `gemini-3.1-pro-preview"` | `gemini-3.1-pro-preview"` |
| `gemini_hr_model` | `gemini-3.1-flash-lite-preview"` | `gemini-3.1-flash-lite-preview"` | `gemini-3.1-flash-lite-preview"` |
| `gemini_ops_model` | `gemini-3.1-flash-lite-preview"` | `gemini-3.1-flash-lite-preview"` | `gemini-3.1-flash-lite-preview"` |
| `gemini_missions_model` | `gemini-3.1-flash-lite-preview"` | `gemini-3.1-flash-lite-preview"` | `gemini-3.1-flash-lite-preview"` |
| `gemini_cv_model` | `gemini-3.1-flash-lite-preview"` | `gemini-3.1-flash-lite-preview"` | `gemini-3.1-flash-lite-preview"` |
| `gemini_pro_model` | `gemini-3.1-pro-preview"` | `gemini-2.5-pro"` | `gemini-3.1-pro-preview"` |
| `gemini_embedding_model` | `gemini-embedding-001"` | `gemini-embedding-001"` | `gemini-embedding-001"` |

### 📊 Observabilité

| Paramètre | **DEV** | **PRD** | **UAT** |
| --- | --- | --- | --- | --- |
| `trace_sampling_rate` | `1.0` | `0.1` | `0.5` |

---

## 🚀 Pipeline de Déploiement — `scripts/deploy.sh`

> Dernière modification : `2026-04-23` · Cible : `slavayssiere-sandbox-462015` / `europe-west1` · Registre : `z-gcp-summit-services`

### Utilisation

```bash
# Déployer tous les services (bump patch)
bash scripts/deploy.sh all

# Déployer des services spécifiques avec bump minor
bash scripts/deploy.sh users_api cv_api minor

# Build Docker uniquement (sans déploiement Cloud Run)
bash scripts/deploy.sh all --no-deploy

# Ignorer les services sans modification
bash scripts/deploy.sh all --skip-unchanged
```

### Options de versioning (SemVer)

| Option | Effet |
| --- | --- |
| `patch` (défaut) | Incrémente la version `Z` en `vX.Y.Z` |
| `minor` | Incrémente la version `Y`, remet `Z` à 0 |
| `major` | Incrémente la version `X`, remet `Y.Z` à 0 |
| `none` | Utilise la version actuelle sans modification |
| `--no-deploy` | Build et push Docker uniquement — ne déploie pas sur Cloud Run |
| `--skip-unchanged` | Ignore le build des services sans changement (basé sur le hash SHA1) |

### Services disponibles

#### 🔵 APIs Data (exposent un sidecar MCP)

| Service | Description | Cible Cloud Run |
| --- | --- | --- |
| `users_api` | Gestion des utilisateurs, authentification JWT | `users-api-dev` |
| `items_api` | Gestion des items et catégories | `items-api-dev` |
| `competencies_api` | Arbre de compétences | `competencies-api-dev` |
| `cv_api` | Analyse et stockage multimodale des CVs | `cv-api-dev` |
| `prompts_api` | Gestion des system prompts des agents | `prompts-api-dev` |
| `drive_api` | Synchronisation Google Drive | `drive-api-dev` |
| `missions_api` | Gestion des missions client | `missions-api-dev` |
| `analytics_mcp` | FinOps & BigQuery analytics (MCP natif) | `analytics-mcp-dev` |
| `monitoring_mcp` | Monitoring Cloud Run / Logs (MCP natif) | `monitoring-mcp-dev` |

#### 🟣 Agents IA (build depuis la racine avec `agent_commons`)

| Service | Description | Cible Cloud Run |
| --- | --- | --- |
| `agent_router_api` | Orchestrateur A2A — routeur principal (Gemini Pro) | `agent-router-api-dev` |
| `agent_hr_api` | Sous-agent RH — CVs, compétences, utilisateurs | `agent-hr-api-dev` |
| `agent_ops_api` | Sous-agent Ops — items, missions, opérationnel | `agent-ops-api-dev` |
| `agent_missions_api` | Sous-agent Missions — gestion documentaire staffing | `agent-missions-api-dev` |

#### ⚙️ Services Spéciaux

| Service | Description |
| --- | --- |
| `frontend` | SPA Vue.js — build npm + upload GCS + invalidation CDN |
| `db_migrations` | Liquibase — migration du schéma AlloyDB (Cloud Run Job) |
| `db_init` | Initialisation AlloyDB (Cloud Run Job, accès VPC uniquement) |
| `sync_prompts` | Synchronisation des system prompts vers prompts_api |

### Flux d'exécution

```
deploy.sh [SERVICE] [BUMP_TYPE] [OPTIONS]
     │
     ├─► Compute hash SHA1 du service (--skip-unchanged)
     ├─► Bump version dans SERVICE/VERSION
     ├─► docker build --platform linux/amd64
     ├─► docker push → Artifact Registry (europe-west1)
     ├─► gcloud run services update (ou jobs update + execute)
     └─► sync_system_prompts() si service impacté
```

> **Sync automatique des prompts** : après tout déploiement impactant
> `prompts_api`, `agent_*`, `cv_api` ou `missions_api`, le script
> appelle automatiquement `sync_system_prompts()` via `scripts/sync_prompts.py`.

---

## ⚙️ Pipeline d'Infrastructure — `platform-engineering/manage_env.py`

> Dernière modification : `2026-04-24`

### Description

`manage_env.py` est l'outil de gestion des environnements GCP.
Il lit la configuration depuis `platform-engineering/envs/<env>.yaml`
et pilote Terraform, les validations de santé et le seeding FinOps.

### Commandes disponibles

| Commande | Arguments | Description |
| --- | --- | --- |
| `plan` | `--env <dev|uat|prd>` | Exécute `terraform plan` sur l'environnement cible sans appliquer |
| `apply` | `--env <dev|uat|prd>` | ⚠️ Interdit à l'agent — déploiement Terraform (réservé au développeur) |
| `sanity` | `--env <dev|uat|prd>` | Vérifie la disponibilité de chaque endpoint Cloud Run + MCP |
| `sync-frontend` | `--env <dev|uat|prd>` | Upload les assets frontend depuis le bucket GCS vers le bucket de l'env |
| `seed-finops` | `--env <dev|uat|prd>` | Initialise les tables BigQuery FinOps (`model_pricing`, `ai_usage`) |
| `status` | `--env <dev|uat|prd>` | Affiche les versions déployées par service et leur statut Cloud Run |

### Priorité des versions d'images

```
YAML (envs/<env>.yaml)  >  VERSION (fichier local du service)
```
Si une version est explicitement définie dans le fichier YAML de l'environnement,
elle prend le dessus sur le fichier `VERSION` local du microservice.

### Flux d'exécution (plan/apply)

```
manage_env.py plan --env dev
     │
     ├─► Lecture de platform-engineering/envs/dev.yaml
     ├─► Calcul des URLs d'images : {image_registry}/{service}:{version}
     ├─► Sélection workspace Terraform : tf workspace select dev
     ├─► terraform plan -var-file=... (variables injectées depuis YAML)
     └─► Rapport des changements détectés
```

---

## 🔧 Scripts Auxiliaires

| Script | Rôle |
| --- | --- |
| `scripts/run_tests.sh` | Lance tous les `pytest` en parallèle pour chaque microservice |
| `scripts/generate_specs.py` | Régénère `spec.md` dans chaque service via l'OpenAPI FastAPI |
| `scripts/generate_changelog.py` | Met à jour `changelog.md` avec les rapports de couverture |
| `scripts/sync_prompts.py` | Pousse les system prompts vers `prompts_api` (AlloyDB) |
| `scripts/generate_pipeline_docs.py` | Régénère ce document `docs/pipelines.md` (auto) |
| `scripts/async_manage_env.sh` | Wrapper asynchrone pour `manage_env.py` (runs en background) |
| `platform-engineering/manage_env.py` | Gestion complète des environnements GCP (plan/apply/sanity/seed) |

---

## 📚 Ressources complémentaires

- [AGENTS.md](../AGENTS.md) — Golden Rules de l'architecture
- [spec.md](../platform-engineering/spec.md) — Spécifications API auto-générées
- [changelog.md](../changelog.md) — Historique des versions et couvertures
- [todo.md](../todo.md) — Backlog technique (ADRs)
