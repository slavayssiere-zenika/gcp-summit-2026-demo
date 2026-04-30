---
description: Audit complet de toutes les APIs pour vérifier le respect des Golden Rules de l'architecture Zenika Cloud Run.
---

Ce workflow permet à l'agent de scanner automatiquement toutes les APIs du projet pour vérifier leur conformité aux "Golden Rules" du projet Zenika.

// turbo-all

### Étape 0 : Lecture des README.md (OBLIGATOIRE)

Avant d'inspecter le moindre fichier de code, lire le `README.md` de chaque service détecté. Le README est la source de vérité sur l'architecture, les dépendances critiques et les points d'attention du service.

// turbo
```bash
for d in *_api *_mcp agent_*; do [ -d "$d" ] && { echo "=== $d ==="; [ -f "$d/README.md" ] && head -25 "$d/README.md" || echo ">>> MANQUANT — à créer avant d\'auditer"; }; done
```

Si un README est absent pour un service → le créer conformément au template §13 AGENTS.md **avant** de démarrer l'audit de ce service.

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
- [ ] **Analyse Statique (Flake8)** : Exécuter `flake8` sur le code source (`python3 -m pip install flake8 && python3 -m flake8 src/ --select=F821,F822,E901,F841,E722,E402`) pour détecter les variables non définies (F821), les erreurs de syntaxe (E901), les exceptions silencieuses (E722) et forcer les imports globaux PEP 8 (E402).
- [ ] **Gestion des erreurs** : Absence de `except Exception: pass`. "Failfast" et zéro erreur silencieuse appliqués.
- [ ] **Health Checks (Liveness/Readiness)** : Découplage strict entre la Liveness (`/health` instantané sans appels externes/DB) et la Readiness (`/ready` ou équivalent pour le test de connectivité BDD/BigQuery/Redis).
- [ ] **Contrat d'Environnement (ENV Contract)** : Tout appel à `os.getenv` ou `os.environ` dans le code **doit** avoir une déclaration `ENV` correspondante dans le `Dockerfile`.
- [ ] **Bonnes Pratiques Cloud Run** : 
    - `ENV PYTHONUNBUFFERED=1` doit être présent dans le Dockerfile pour le streaming des logs.
    - Le port d'écoute Uvicorn devrait idéalement s'adapter dynamiquement (`--port ${PORT:-8000}`) ou correspondre strictement à la conf Terraform.
    - Aucune persistance d'état ou écriture sur disque local n'est autorisée (tout fichier temporaire doit utiliser `/tmp` qui consomme la RAM du conteneur).
- [ ] **Anti-Fallback JWT** : L'absence de `SECRET_KEY` **doit** lever une `ValueError` au démarrage. Tout code permissif (`return {"sub": "dev-user"}`) en l'absence de secret est une faille bloquante.
- [ ] **Background Tasks** : Toute tâche asynchrone (Pub/Sub, BackgroundTasks) doit utiliser un token de service dédié généré via `/auth/internal/service-token`. L'usurpation du compte `admin` est formellement proscrite.
- [ ] **Isolation Redis** : Chaque service utilisant Redis doit cibler une base isolée explicite (ex: `/0`, `/1`) dans son URL de connexion.
- [ ] **Taille des fichiers Python (400 lignes max)** : Aucun fichier `.py` dans `src/` ne doit dépasser **400 lignes**. Vérifier avec `find src/ -name "*.py" | xargs wc -l | sort -rn | head -20`. Tout fichier dépassant ce seuil est un signal d'un "God Module" à décomposer en services ou sous-modules. Exception tolérée uniquement pour les fichiers de migration Liquibase ou les fixtures de test.
- [ ] **Taille des fonctions Python (50 lignes max)** : Aucune fonction ou méthode ne doit dépasser **50 lignes** de corps (hors docstring et commentaires). Vérifier avec `python3 -m pip install radon && python3 -m radon cc src/ -a -nb` pour mesurer la complexité cyclomatique (toute fonction de rang `C`, `D` ou `F` est une cible de refactoring prioritaire). Une fonction dépassant 50 lignes indique une violation du principe de responsabilité unique (SRP) et nuit à la testabilité.
- [ ] **Pagination lors de la consommation d'APIs** : Vérifier que tout appel vers une API externe (Google Drive, BigQuery, Cloud Logging, Pub/Sub) ou interne (à la plateforme) qui retourne une liste utilise la pagination ou les page tokens. Rechercher les patterns d'appel unique sans boucle : `grep -rn "\.list(\.execute()\|\.list(" src/` et vérifier la présence d'une boucle `while True` / `nextPageToken` / `skip += limit`. Tout appel `service.files().list(...).execute()` sans `pageToken` ou tout `GET /users/` sans `skip`/`limit` en boucle est un **bug de troncature silencieuse**.

#### 3.2. Spécifique aux APIs Data 🔵
- [ ] **Zero-Trust** : Endpoints protégés par `dependencies=[Depends(verify_jwt)]` sur le `APIRouter`.
- [ ] **Interface MCP** : Tool MCP créé ou mis à jour dans `mcp_server.py`.
- [ ] **Proxy MCP** : Route `/mcp/{path:path}` proxy vers le sidecar MCP présente dans `main.py`.
- [ ] **Traçabilité sortante** : `inject(headers)` présent dans **chaque** appel `httpx` sortant.
- [ ] **Base de données** : Changeset Liquibase présent dans `db_migrations/changelogs/` avec section `rollback`.
- [ ] **Cache** : Cache Redis invalidé sur les mutations (POST, PUT, DELETE).
- [ ] **Tests** : Tests de contrat MCP ajoutés dans `test_mcp_tools.py`.
- [ ] **Golden Pattern Erreur** : Implémentation du pattern global `@app.exception_handler(Exception)` reportant sur `prompts_api`.
- [ ] **Readiness Anti-Pool-Starvation** : La fonction `check_db_connection()` dans `database.py` **doit** utiliser `asyncio.wait_for(_ping(), timeout=5.0)` et retourner `True` (optimiste) sur `asyncio.TimeoutError`. Sans ce guard, un pool AlloyDB saturé par un batch background (ex: bulk scoring, Vertex AI) bloque le `/ready` endpoint 30s → HTTP 503 injustifié lors du Sanity Check. Pattern obligatoire :
  ```python
  async def check_db_connection() -> bool:
      global engine
      if not engine:
          return False
      try:
          async def _ping():
              async with engine.connect() as conn:
                  await conn.execute(text("SELECT 1"))
          await asyncio.wait_for(_ping(), timeout=5.0)
          return True
      except asyncio.TimeoutError:
          logger.warning("[DB] Pool saturé (timeout 5s) — retour optimiste: True.")
          return True
      except Exception as e:
          logger.error(f"[DB] Database connection test failed: {e}")
          return False
  ```
- [ ] **Pagination des endpoints listés** : Tout endpoint retournant une liste (`GET /resource/`) DOIT accepter `skip: int = 0, limit: int = 50` et inclure `total` dans la réponse. Rechercher les violations avec : `grep -rn "\.limit(" src/` et vérifier que toute hard limit est accompagnée de paramètres `skip`/`limit` et d'un champ `total` dans la réponse.

#### 3.3. Spécifique aux Agents 🟣
- [ ] **Zero-Trust Local** : `verify_jwt()` (validation signature HS256 + claim `sub`) définie localement dans `main.py`.
- [ ] **Zero-Trust Application** : `protected_router = APIRouter(dependencies=[Depends(verify_jwt)])` obligatoirement utilisé.
- [ ] **A2A & Traçabilité** : `inject(headers)` présent dans **chaque** appel HTTP sortant vers les APIs ou sous-agents.
- [ ] **Propagation JWT** : `auth_header_var` propagé aux clients MCP pour transmettre le JWT aux APIs cibles.
- [ ] **Tests** : Tests de session, guardrail, et propagation JWT ajoutés.
- [ ] **Interdiction MCP** : Absence stricte de fichier `mcp_server.py`.
- [ ] **Code Mutualisé** : Le package `agent_commons` (qui existe déjà) DOIT être utilisé pour tout le code commun (JWT, Guardrails, FinOps, etc.) plutôt que de dupliquer la logique dans chaque agent.

### Étape 4 : Génération du Rapport
Une fois l'audit terminé, génère un artefact détaillé (ex: `rapport_audit_apis.md`). 
Le rapport doit catégoriser les services (APIs Data, Agents) et contenir une matrice d'audit (avec emojis ✅ ❌) montrant précisément quels points de la **CHECKLIST DE CONFORMITÉ** de `AGENTS.md` sont respectés ou violés, ainsi que le plan d'action recommandé pour corriger les non-conformités.
