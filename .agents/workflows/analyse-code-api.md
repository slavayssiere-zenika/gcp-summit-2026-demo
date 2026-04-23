---
description: Audit complet de toutes les APIs pour vérifier le respect des Golden Rules de l'architecture Zenika Cloud Run.
---

Ce workflow permet à l'agent de scanner automatiquement toutes les APIs du projet pour vérifier leur conformité aux "Golden Rules" du projet Zenika.

// turbo-all

### Étape 1 : Détection et Catégorisation des Services
Utilise l'outil `list_dir` ou `run_command` (ex: `find . -maxdepth 1 -name "*_api" -o -name "*_mcp" -type d`) pour identifier tous les dossiers de services dans le répertoire courant.
Classe chaque service selon la typologie définie dans `AGENTS.md` :
- **APIs Data 🔵** (producteurs MCP avec DB) : ex. `users_api`, `items_api`, `cv_api`, `competencies_api`, `missions_api`, `drive_api`, `prompts_api`
- **Agents 🟣** (consommateurs MCP sans DB) : ex. `agent_router_api`, `agent_hr_api`, `agent_ops_api`, `agent_missions_api`
- **MCP Natif 🟤** (sans DB) : ex. `analytics_mcp`

### Étape 2 : Analyse de configuration de `db_init_job.tf`
Inspecte le fichier `platform-engineering/terraform/db_init_job.tf`.
Vérifie la variable `services = [...]`. Compare cette liste avec la liste des **APIs Data** détectées (qui nécessitent une base de données). Note quelles APIs sont correctement enregistrées pour la création de leur logique DB et IAM.

### Étape 3 : Audit de Conformité (CHECKLIST AGENTS.md)
Pour chaque service détecté, vérifie rigoureusement les points de la checklist de conformité de `AGENTS.md` en inspectant le code source (`grep_search`, `list_dir`, `view_file`) :

#### 3.1. Règles communes (Tous les services)
- [ ] **Observabilité** : `Instrumentator().instrument(app).expose(app)` est présent dans `main.py`.
- [ ] **Traçabilité** : `FastAPIInstrumentor.instrument_app(app, excluded_urls="health,metrics")` est présent dans `main.py`.
- [ ] **Versioning** : Fichier `VERSION` mis à jour (semver) présent à la racine.
- [ ] **Modèles IA** : Aucun modèle IA hardcodé, utilisation des variables d'environnement.
- [ ] **Container Contract** : Dockerfile multi-stage (`AS builder`), utilisateur non-root (`USER`), `CMD` sans shell (utilisation de `python3`), et présence d'un `.dockerignore`.
- [ ] **Gestion des erreurs** : Absence de `except Exception: pass`. "Failfast" et zéro erreur silencieuse appliqués.
- [ ] **Health Checks (Liveness/Readiness)** : Découplage strict entre la Liveness (`/health` instantané sans appels externes/DB) et la Readiness (`/ready` ou équivalent pour le test de connectivité BDD/BigQuery/Redis).

#### 3.2. Spécifique aux APIs Data 🔵
- [ ] **Zero-Trust** : Endpoints protégés par `dependencies=[Depends(verify_jwt)]` sur le `APIRouter`.
- [ ] **Interface MCP** : Tool MCP créé ou mis à jour dans `mcp_server.py`.
- [ ] **Proxy MCP** : Route `/mcp/{path:path}` proxy vers le sidecar MCP présente dans `main.py`.
- [ ] **Traçabilité sortante** : `inject(headers)` présent dans **chaque** appel `httpx` sortant.
- [ ] **Base de données** : Changeset Liquibase présent dans `db_migrations/changelogs/` avec section `rollback`.
- [ ] **Cache** : Cache Redis invalidé sur les mutations (POST, PUT, DELETE).
- [ ] **Tests** : Tests de contrat MCP ajoutés dans `test_mcp_tools.py`.
- [ ] **Golden Pattern Erreur** : Implémentation du pattern global `@app.exception_handler(Exception)` reportant sur `prompts_api`.

#### 3.3. Spécifique aux Agents 🟣
- [ ] **Zero-Trust Local** : `verify_jwt()` (validation signature HS256 + claim `sub`) définie localement dans `main.py`.
- [ ] **Zero-Trust Application** : `protected_router = APIRouter(dependencies=[Depends(verify_jwt)])` obligatoirement utilisé.
- [ ] **A2A & Traçabilité** : `inject(headers)` présent dans **chaque** appel HTTP sortant vers les APIs ou sous-agents.
- [ ] **Propagation JWT** : `auth_header_var` propagé aux clients MCP pour transmettre le JWT aux APIs cibles.
- [ ] **Tests** : Tests de session, guardrail, et propagation JWT ajoutés.
- [ ] **Interdiction MCP** : Absence stricte de fichier `mcp_server.py`.

### Étape 4 : Génération du Rapport
Une fois l'audit terminé, génère un artefact détaillé (ex: `rapport_audit_apis.md`). 
Le rapport doit catégoriser les services (APIs Data, Agents) et contenir une matrice d'audit (avec emojis ✅ ❌) montrant précisément quels points de la **CHECKLIST DE CONFORMITÉ** de `AGENTS.md` sont respectés ou violés, ainsi que le plan d'action recommandé pour corriger les non-conformités.
