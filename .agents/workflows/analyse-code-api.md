---
description: Audit complet de toutes les APIs pour vérifier le respect des Golden Rules de l'architecture Zenika Cloud Run.
---

Ce workflow permet à l'agent de scanner automatiquement toutes les APIs du projet pour vérifier leur conformité aux "Golden Rules" du projet Zenika.

### Étape 1 : Détection des APIs
Utilise l'outil `list_dir` ou `run_command` (ex: `find . -maxdepth 1 -name "*_api" -type d`) pour identifier tous les dossiers d'APIs dans le répertoire courant (exemple : `users_api`, `items_api`, `cv_api`, `agent_api`, `competencies_api`, `missions_api`, `prompts_api`, etc.).

### Étape 2 : Analyse de configuration de `db_init_job.tf`
Inspecte le fichier `platform-engineering/terraform/db_init_job.tf`.
Vérifie la variable `services = [...]`. Compare cette liste avec la liste des APIs détectées (pour celles qui nécessitent une base de données). Note quelles APIs sont correctement enregistrées pour la création de leur logique DB et IAM.

### Étape 3 : Audit de chaque API (Boucle)
Pour chaque API détectée, vérifie les points d'audit suivants (utilise `grep_search`, `list_dir` ou `view_file` selon ton besoin) :

#### 3.1. Architecture & Container Contract
- Présence d'un `Dockerfile` avec `AS builder` (Multi-stage build).
- Exécution non-root (présence de `USER`).
- Syntaxe `CMD` correcte (pas de script shell direct).
- Présence d'un `.dockerignore`.
- Présence du fichier `VERSION` à la racine de l'API.

#### 3.2. Observabilité & Logging
- Fichier `main.py` contient l'instrumentation OpenTelemetry (avec exclusion de `/health,metrics` via `FastAPIInstrumentor`).
- Déclaration Prometheus (`Instrumentator().instrument(app).expose(app)`).
- Le fichier `logger.py` implémente `pythonjsonlogger` pour JSON et attache `trace_id` / `span_id`.
- Utilisation de `LoggingMiddleware` qui filtre le bruit (`/health`, etc.).
- Les appels HTTP sortants (si visibles dans le code) utilisent `inject(headers)`.
- Implémentation du pattern global `@app.exception_handler(Exception)` reportant sur `prompts_api` (Golden Pattern).

#### 3.3. Sécurité
- Utilisation de `verify_jwt` de `src.auth` pour protéger les routes.

#### 3.4. MCP & Structure
- Présence du fichier `mcp_server.py`.
- L'API route `/mcp/{path:path}` vers le port d'exécution MCP.

#### 3.5. Qualité & Tests
- Dossier de tests ou fichiers `test_main.py` et `conftest.py`.
- Traces de couverture (présence de fichiers configurant le coverage, ou d'artefacts comme `.coverage` ou `coverage.json`).

#### 3.6. Gestion des Erreurs (Failfast Zéro Erreur Silencieuse)
- Absence totale de blocs `except Exception: pass` ou de logs isolés capturant une erreur sans instruction `raise`.
- Vérifier que les actions asynchrones (`asyncio.create_task`) finissent par lever l'exception (`raise e`) ou utiliser un outil explicite centralisé si elles échouent.
- S'assurer que les outils MCP (`mcp_server.py`) retournent contractuellement la forme structurée `{"success": false, "error": "..."}` en cas d'erreur.

### Étape 4 : Génération du Rapport
Une fois toutes les APIs analysées, génère un artefact détaillé (ex: `rapport_audit_apis.md`). 
Le rapport doit contenir, pour chaque API, une matrice ou des encarts visuels (avec emojis ✅ ❌) montrant si chaque Golden Rule est respectée ou non, ainsi que des recommandations de fix pour les APIs non-conformes.
