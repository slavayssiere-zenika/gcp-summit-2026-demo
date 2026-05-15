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

### Étape 2b : Audit Terraform LB (NOUVEAU — issu de l'audit 2026-05)

Inspecter `platform-engineering/terraform/lb.tf` et `lb-internal.tf` pour détecter les incohérences de routage.

// turbo
```bash
# 1. Vérifier que les sous-agents ne sont PAS exposés directement sur le LB externe
#    (seul agent_router_api doit être le point d'entrée public via le catch-all /api/)
echo "=== Routes directes sous-agents sur LB externe (doit être vide) ==="
grep -n "agent.hr.backend\|agent.ops.backend\|agent.missions.backend" platform-engineering/terraform/lb.tf \
  | grep -v "^#" | grep -v "NOTE:" || echo "✅ Aucune route directe sous-agent sur LB externe"

# 2. Vérifier la cohérence des path_prefix_rewrite entre LB externe et LB interne
echo "=== Réécriture /auth/ — LB externe ==="
grep -A5 'prefix_match = "/auth/"' platform-engineering/terraform/lb.tf | grep path_prefix_rewrite

echo "=== Réécriture /auth/ — LB interne (doit être '/' comme le LB externe) ==="
grep -A5 'prefix_match = "/auth/"' platform-engineering/terraform/lb-internal.tf | grep path_prefix_rewrite

# 3. Détecter les backend_service externes orphelins (définis dans cr_*.tf mais plus référencés dans lb.tf)
echo "=== Backend services externes définis dans cr_*.tf ==="
grep -rn 'resource "google_compute_backend_service"' platform-engineering/terraform/cr_*.tf | grep -v "NOTE:"

echo "=== Backend services externes référencés dans lb.tf ==="
grep -n 'google_compute_backend_service\.' platform-engineering/terraform/lb.tf | grep -v "^#"
```

Violations à signaler :
- ❌ Route directe `/api/agent-hr/`, `/api/agent-ops/`, `/api/agent-missions/` sur le LB externe → réduire la surface d'attaque, supprimer et router tout via `agent_router_api`
- ❌ `path_prefix_rewrite = "/users/"` sur `/auth/` dans le LB interne → bug de routage, corriger en `"/"`
- ❌ `google_compute_backend_service` défini dans `cr_*.tf` mais non référencé dans `lb.tf` → ressource orpheline, à supprimer

### Étape 3 : Audit de Conformité (CHECKLIST AGENTS.md)
Pour chaque service détecté, vérifie rigoureusement les points de la checklist de conformité de `AGENTS.md` en inspectant le code source (`grep_search`, `list_dir`, `view_file`) :

#### 3.1. Règles communes (Tous les services)
- [ ] **Observabilité** : `Instrumentator().instrument(app).expose(app)` est présent dans `main.py`.
- [ ] **Traçabilité** : `FastAPIInstrumentor.instrument_app(app, excluded_urls="health,metrics")` est présent dans `main.py`.
- [ ] **Versioning** : Fichier `VERSION` mis à jour (semver) présent à la racine.
- [ ] **APP_VERSION dynamique** : `SERVICE_VERSION` ou version hardcodée INTERDITE. Le code doit utiliser `os.getenv("APP_VERSION", "dev")`. Vérifier avec :
  ```bash
  grep -rn 'SERVICE_VERSION.*=.*"[0-9]' */main.py *_mcp/mcp_*.py --include="*.py" 2>/dev/null
  grep -rn 'SERVICE_VERSION.*=.*"[0-9]' . --include="*.py" | grep -v ".venv" | grep -v ".git"
  ```
  Toute occurrence de `SERVICE_VERSION: "1.0.0"` ou version figée est une violation — remplacer par `os.getenv("APP_VERSION", "dev")`.
- [ ] **Modèles IA** : Aucun modèle IA hardcodé, utilisation des variables d'environnement.
- [ ] **CORS Sécurisé** : `allow_origins=["*"]` est **INTERDIT**. Doit utiliser une liste dynamique lue depuis `CORS_ORIGINS` env var :
  ```bash
  grep -rn 'allow_origins.*\[\s*"\*"' */main.py --include="*.py" 2>/dev/null
  ```
  Pattern obligatoire :
  ```python
  cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
  app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in cors_origins], ...)
  ```
- [ ] **Imports top-level (PEP8 §8)** : Aucun import Python à l'intérieur d'une fonction ou d'un `@app.exception_handler`. Détecter les violations avec :
  ```bash
  # Imports locaux dans les fonctions (E402 / violation §8 Golden Rules)
  grep -rn "^\s\+from \|^\s\+import " */main.py *_mcp/mcp_*.py --include="*.py" 2>/dev/null \
    | grep -v "^\s*#" | grep -v "__init__"
  # Alternative plus précise
  grep -Pn "^    (from|import) " */main.py 2>/dev/null
  ```
  Toute occurrence dans un bloc indenté (4+ espaces) est une violation — remonter au top-level du fichier.
- [ ] **Container Contract** : Dockerfile multi-stage (`AS builder`), utilisateur non-root (`USER`), `CMD` sans shell (utilisation de `python3`), et présence d'un `.dockerignore`.
- [ ] **Dépendances Docker superflues** : Le SDK Python Google Cloud (`google-cloud-*`) est suffisant. `google-cloud-cli` (~500MB) est formellement interdit dans les Dockerfiles des agents :
  ```bash
  grep -rn "google-cloud-cli\|google-cloud-sdk" */Dockerfile agent_*/Dockerfile 2>/dev/null
  ```
  Si présent → supprimer. Aucun agent n'exécute de commandes `gcloud` CLI en runtime.
- [ ] **Analyse Statique (Flake8 étendu)** : Exécuter `flake8` sur le code source avec les règles complètes du projet :
  ```bash
  # Vérification globale sur tous les services (120 chars max, W503 ignoré)
  for d in *_api *_mcp agent_*; do
    [ -d "$d" ] && python3 -m flake8 "$d/main.py" "$d/mcp_app.py" "$d/mcp_server.py" \
      --max-line-length=120 --extend-ignore=W503 2>/dev/null && echo "✅ $d" || echo "❌ $d"
  done
  # Cibler les codes critiques sur src/
  python3 -m flake8 src/ --select=F821,F822,E901,F841,E722,E402,F401,F811 --max-line-length=120
  ```
  Les codes F401 (import inutilisé) et F811 (redéfinition d'import) détectent les imports dupliqués entre top-level et handler local.
- [ ] **Test Coverage des Schémas (100%)** : Tout fichier `schemas.py` contenant des modèles Pydantic doit faire l'objet de tests unitaires dédiés (ex: `test_schemas.py`) garantissant formellement 100% de couverture sur les validateurs et alias.
- [ ] **Gestion des erreurs** : Absence de `except Exception: pass` ET absence de `raise e` dans un bloc `except` best-effort (masque l'erreur originale). Pattern correct :
  ```python
  # ✅ Best-effort : logguer sans relancer
  except Exception as e:
      logging.error("Failed to report: %s", e)   # ne pas raise
  ```
  Vérifier avec : `grep -rn "raise e$\|raise err$" */main.py --include="*.py"`.
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
- [ ] **Contrats d'interface inter-services (ADR-0015)** : Vérifier que toutes les réponses HTTP inter-service sont validées via `model_validate()` et non via `.get("clé", [])` silencieux. Rechercher les violations avec :
  ```bash
  # Détecter les parsings silencieux (anti-pattern)
  grep -rn '\.json()\.\.get\(\|res\.json()\.get(' src/ --include='*.py' | grep -v '# Contrat intentionnel' | grep -v '# Fallback intentionnel'
  # Vérifier la présence des imports shared/schemas dans les fichiers consommateurs
  grep -rn 'from shared.schemas' src/ --include='*.py'
  # Vérifier que model_validate est utilisé sur les réponses inter-service
  grep -rn 'model_validate' src/ --include='*.py'
  ```
  Tout `.get("items", [])` ou `.get("users", [])` sur une réponse `httpx` **sans** `# Contrat intentionnel` est une **violation** — migrer vers `PaginationResponse[dict].model_validate()` ou le schema spécifique dans `shared/schemas/`.

#### 3.2. Spécifique aux APIs Data 🔵
- [ ] **Zero-Trust** : Endpoints protégés par `dependencies=[Depends(verify_jwt)]` sur le `APIRouter`.
- [ ] **Interface MCP** : Tool MCP créé ou mis à jour dans `mcp_server.py`.
- [ ] **Proxy MCP** : Route `/mcp/{path:path}` proxy vers le sidecar MCP présente dans `main.py`.
- [ ] **Traçabilité sortante** : `inject(headers)` présent dans **chaque** appel `httpx` sortant.
- [ ] **Base de données** : Changeset Liquibase présent dans `db_migrations/changelogs/` avec section `rollback`.
- [ ] **Cache** : Cache Redis invalidé sur les mutations (POST, PUT, DELETE).
- [ ] **Tests** : Tests de contrat MCP ajoutés dans `test_mcp_tools.py`.
- [ ] **Golden Pattern Erreur** : Implémentation du pattern global `@app.exception_handler(Exception)` reportant sur `prompts_api`. Vérifier que `StarletteHTTPException` et `RequestValidationError` sont importés au **top-level** et non dans le handler :
  ```bash
  # Détecter les imports locaux dans les handlers d'exception (violation §8)
  grep -A5 "exception_handler(Exception)" */main.py | grep "from fastapi\|from starlette"
  ```
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
- [ ] **Contrat MCP (ADR-0015)** : `MCPHttpClient.call_tool()` doit utiliser `McpToolResult.model_validate()` (via `agent_commons/mcp_client.py`). Vérifier que le fichier `agent_commons/agent_commons/mcp_client.py` contient `McpToolResult.model_validate()` et **non** `.get("result", [])`. Ce check est global — une violation dans `agent_commons` affecte les 4 agents simultanément.
  ```bash
  # Vérifier la présence du pattern correct dans mcp_client.py
  grep -n 'McpToolResult\|model_validate\|\.get("result"' agent_commons/agent_commons/mcp_client.py
  ```
- [ ] **Dead Code Auth (NOUVEAU — issu de l'audit 2026-05)** : Les sous-agents (`agent_hr_api`, `agent_ops_api`, `agent_missions_api`) **NE DOIVENT PAS** exposer les endpoints `/login`, `/me`, `/logout`. Ce sont des workers A2A uniquement appelés par `agent_router_api` via le LB interne. Seul `agent_router_api` (le BFF) est autorisé à proxifier ces endpoints. Vérifier avec :
  ```bash
  # Détecter les endpoints auth dans les sous-agents (doit être vide)
  for agent in agent_hr_api agent_ops_api agent_missions_api; do
    echo "=== $agent ==="
    grep -n '@app\.\(get\|post\)(.*"/\(login\|logout\|me\)"' "$agent/main.py" \
      && echo "❌ Dead code auth détecté dans $agent" \
      || echo "✅ Aucun endpoint auth parasite"
  done
  ```
  Si des endpoints `/login`, `/me`, `/logout` sont trouvés dans un sous-agent → les supprimer et vérifier que le frontend s'authentifie via `/auth/` → `users_api` directement.

#### 3.4. Appels externes — Retry, Timeout & Résilience (Tous les services)

Chaque appel HTTP sortant (vers une API interne, un service Google, Pub/Sub, Vertex AI…) **doit** respecter les règles de résilience suivantes. L'absence de ces mécanismes est une **violation bloquante** : un timeout réseau non capturé peut mettre en cascade l'intégralité du service (worker coroutine bloquée → pool épuisé → HTTP 503).

- [ ] **Timeout explicite sur tous les appels `httpx`** : Tout client `httpx.AsyncClient` ou appel `.get()` / `.post()` **doit** définir un `timeout` explicite. Un appel sans timeout peut bloquer un worker Cloud Run indéfiniment. Détecter les violations :
  ```bash
  # Appels httpx sans timeout (anti-pattern)
  grep -rn 'httpx\.AsyncClient\|httpx\.get\|httpx\.post\|client\.get\|client\.post\|client\.put\|client\.delete\|client\.patch' \
    */src/ */main.py agent_*/main.py --include='*.py' 2>/dev/null \
    | grep -v 'timeout' | grep -v '# noqa' | grep -v '.venv'
  # Vérifier la présence d'un timeout global sur les AsyncClient
  grep -rn 'httpx\.AsyncClient(' */src/ */main.py agent_*/main.py --include='*.py' 2>/dev/null \
    | grep -v 'timeout'
  ```
  Pattern obligatoire :
  ```python
  # ✅ Timeout global sur le client (recommandé)
  async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0)) as client:
      resp = await client.get(url, headers=headers)

  # ✅ Timeout par appel (acceptable si le client est partagé)
  resp = await client.post(url, json=payload, timeout=30.0)

  # ❌ INTERDIT — pas de timeout
  resp = await client.get(url)  # bloque indéfiniment si le service est lent
  ```

- [ ] **Retry avec backoff exponentiel sur les erreurs transitoires** : Les appels vers des services externes (APIs internes, Google APIs, Pub/Sub, Vertex AI) **doivent** implémenter une stratégie de retry pour les codes HTTP `429`, `502`, `503`, `504` et les `httpx.TimeoutException`. Détecter les appels sans retry :
  ```bash
  # Rechercher les patterns de retry existants
  grep -rn 'tenacity\|retry\|backoff\|asyncio\.sleep.*retry\|for.*attempt' \
    */src/ agent_*/src/ --include='*.py' 2>/dev/null | grep -v '.venv'
  # Détecter les blocs except qui swallowent silencieusement les erreurs réseau
  grep -rn 'except.*httpx\|except.*TimeoutException\|except.*ConnectError' \
    */src/ agent_*/src/ --include='*.py' 2>/dev/null | grep -v '.venv'
  ```
  Pattern obligatoire (bibliothèque `tenacity` — déjà dans les dépendances) :
  ```python
  from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

  @retry(
      retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
      wait=wait_exponential(multiplier=1, min=1, max=10),
      stop=stop_after_attempt(3),
      reraise=True,
  )
  async def _call_with_retry(client: httpx.AsyncClient, url: str, headers: dict) -> httpx.Response:
      resp = await client.get(url, headers=headers, timeout=30.0)
      if resp.status_code in (429, 502, 503, 504):
          raise httpx.HTTPStatusError(f"Transient {resp.status_code}", request=resp.request, response=resp)
      return resp
  ```
  > **Règle minimale acceptable** : si `tenacity` n'est pas encore intégré, un bloc `for attempt in range(3)` avec `asyncio.sleep(2 ** attempt)` est toléré temporairement — mais **uniquement** si l'erreur est logguée et que l'exception finale est bien re-levée.

- [ ] **Gestion explicite des codes d'erreur HTTP non-2xx** : Tout appel vers une API interne ou externe **doit** vérifier explicitement `resp.status_code` après l'appel. Ne jamais supposer qu'une réponse est valide sans vérification. Détecter les usages non-sécurisés :
  ```bash
  # Appels dont le status_code n'est jamais vérifié dans le même bloc
  grep -rn 'await client\.' */src/ agent_*/src/ --include='*.py' 2>/dev/null \
    | grep -v 'status_code\|raise_for_status\|# Contrat intentionnel' | grep -v '.venv'
  # Vérifier la présence de raise_for_status() ou de vérification manuelle
  grep -rn 'raise_for_status\|status_code ==' */src/ agent_*/src/ --include='*.py' 2>/dev/null | grep -v '.venv'
  ```
  Pattern recommandé :
  ```python
  resp = await client.post(url, json=payload, headers=headers, timeout=30.0)
  if resp.status_code == 200:
      data = MyModel.model_validate(resp.json())
  elif resp.status_code in (429, 503):
      raise httpx.HTTPStatusError("Service temporairement indisponible", request=resp.request, response=resp)
  else:
      logger.error("[service] Erreur inattendue %s: %s", resp.status_code, resp.text[:200])
      raise httpx.HTTPStatusError(f"Erreur {resp.status_code}", request=resp.request, response=resp)
  ```

- [ ] **Pas de swallow silencieux des erreurs réseau** : Un `except Exception: pass` ou un `except httpx.TimeoutException: logger.warning(...)` sans `raise` sur un appel critique **masque les défaillances** et rend le monitoring aveugle. Distinguer :
  - **Appels best-effort** (ex: reporting FinOps, notifications non-critiques) : log + return None acceptable.
  - **Appels bloquants** (ex: récupération d'un utilisateur pour une décision métier) : log + `raise` obligatoire.
  ```bash
  # Détecter les except vides ou trop larges sur des appels httpx
  grep -B5 'except Exception.*pass\|except.*httpx.*pass' */src/ agent_*/src/ --include='*.py' -rn 2>/dev/null | grep -v '.venv'
  ```

- [ ] **Timeout sur les appels Google SDK (Vertex AI, BigQuery, Pub/Sub)** : Les SDK Google Python ne définissent pas toujours de timeout par défaut. Vérifier que les appels critiques passent un `timeout` ou utilisent `asyncio.wait_for()` :
  ```bash
  # Détecter les appels Vertex AI sans timeout
  grep -rn 'predict\|generate_content\|submit_batch\|create_batch' \
    */src/ agent_*/src/ --include='*.py' 2>/dev/null \
    | grep -v 'timeout\|wait_for\|# noqa' | grep -v '.venv'
  # Détecter les appels Pub/Sub publisher sans timeout
  grep -rn 'publisher\.publish\|subscriber\.pull' \
    */src/ agent_*/src/ --include='*.py' 2>/dev/null \
    | grep -v 'timeout\|result(' | grep -v '.venv'
  ```
  Pattern obligatoire pour les appels SDK bloquants :
  ```python
  # ✅ Vertex AI — timeout via asyncio.wait_for (appels synchrones wrappés en async)
  try:
      response = await asyncio.wait_for(
          asyncio.get_event_loop().run_in_executor(None, lambda: model.predict(instances)),
          timeout=120.0,
      )
  except asyncio.TimeoutError:
      logger.error("[vertex] Timeout après 120s sur predict — service indisponible")
      raise

  # ✅ Pub/Sub — timeout sur .result() bloquant
  future = publisher.publish(topic_path, data)
  try:
      message_id = future.result(timeout=30)
  except TimeoutError:
      logger.error("[pubsub] Timeout publish après 30s")
      raise
  ```

- [ ] **Résumé cartographique des appels sortants** : Pour chaque service audité, produire une carte synthétique listant :
  1. Les URLs/services appelés (APIs internes, Google APIs, Pub/Sub topics…)
  2. Le timeout configuré (ou `⚠️ ABSENT`)
  3. La stratégie de retry (tenacity / boucle manuelle / `⚠️ ABSENT`)
  4. Le type d'appel (bloquant / best-effort)

  Cette carte doit apparaître dans le rapport final (Étape 5) pour permettre une évaluation rapide de la résilience globale de l'architecture.

#### 3.5. BackgroundTasks PubSub & Endpoints "Pool Sink" — Règle 429 obligatoire (NOUVEAU — post-mortem 2026-05-13)

> **Contexte** : lors d'un import massif de 839 CVs en push PubSub, cv_api a lancé ~800 BackgroundTasks simultanées appelant toutes `POST /user/{id}/assign/bulk` vers competencies_api. Le pool AlloyDB (30 connexions) a été saturé en quelques secondes. Sans retry ni guard 429, chaque HTTP 500 transitoire a généré un `processing_error` permanent en base — 1437 CVs affectés en 30 minutes.

**Règle 1 — Côté serveur : tout endpoint "pool sink" doit retourner 429 avant de crasher**

Un "pool sink" est tout endpoint qui : (a) est susceptible d'être appelé en masse par des BackgroundTasks, ET (b) dépend d'un pool DB pour chaque requête. Il doit protéger son pool via un semaphore et retourner HTTP **429** (pas 500) quand la concurrence est dépassée.

- [ ] **Guard 429 sur les endpoints "pool sink"** : Détecter les endpoints batch/bulk appelés par BackgroundTasks sans semaphore serveur :
  ```bash
  # Détecter les routes bulk/assign sans semaphore guard
  grep -rn '@router\.\(post\|put\).*bulk\|@router\.\(post\|put\).*assign' \
    */src/ --include='*.py' 2>/dev/null | grep -v '.venv'
  # Vérifier la présence d'un semaphore guard avant get_db() dans ces routes
  grep -rn 'asyncio.Semaphore\|_get_.*sem\|sem.locked()' \
    */src/ --include='*.py' 2>/dev/null | grep -v '.venv'
  ```
  Pattern obligatoire (issu de `competencies_api/assignments_router.py`) :
  ```python
  # Semaphore module-level — partagé entre toutes les coroutines de l'instance
  _ENDPOINT_SEM: asyncio.Semaphore | None = None

  def _get_sem() -> asyncio.Semaphore:
      global _ENDPOINT_SEM
      if _ENDPOINT_SEM is None:
          _ENDPOINT_SEM = asyncio.Semaphore(int(os.getenv("ENDPOINT_SEMAPHORE", "5")))
      return _ENDPOINT_SEM

  @router.post("/resource/bulk")
  async def bulk_endpoint(db: AsyncSession = Depends(get_db)):
      sem = _get_sem()
      if sem.locked():  # 429 AVANT d'acquérir une connexion DB
          raise HTTPException(status_code=429, detail="Service sous charge — réessayer.")
      async with sem:
          # ... logique métier avec DB
  ```
  > **Pourquoi 429 et pas 503 ?** Le 503 indique une indisponibilité du service entier (utilisé par le Load Balancer pour retirer l'instance du pool). Le 429 indique une surcharge transitoire sur cet endpoint spécifique — c'est le signal que l'appelant DOIT retenter. Cloud Run ne retire pas l'instance du pool sur un 429.

**Règle 2 — Côté appelant : toute BackgroundTask PubSub doit retry sur 429 avec jitter**

Un 429 sur un endpoint "pool sink" est **toujours transitoire** (le pool se libère en quelques ms). Sans retry, chaque 429 devient un `processing_error` permanent. Avec retry exponentiel + jitter, la plupart des 429 se résolvent dès la 2e tentative.

- [ ] **Retry 429 dans les BackgroundTasks PubSub** : Détecter les appels HTTP dans des BackgroundTasks sans retry sur 429 :
  ```bash
  # Fichiers contenant des BackgroundTasks avec des appels HTTP
  grep -rln 'background_tasks\|BackgroundTasks\|bg_process' \
    */src/ --include='*.py' 2>/dev/null | grep -v '.venv'
  # Dans ces fichiers, vérifier que les appels HTTP ont un retry sur 429
  for f in $(grep -rln 'background_tasks\|BackgroundTasks' */src/ --include='*.py' 2>/dev/null); do
    echo "=== $f ==="
    grep -n 'status_code.*429\|for attempt\|asyncio.sleep.*attempt' "$f" || \
      echo "  ⚠️ Aucun retry sur 429 détecté dans les BackgroundTasks"
  done
  ```
  Pattern obligatoire (issu de `cv_storage_service.py`) :
  ```python
  # Retry avec jitter — évite le thundering herd sur un pic d'import
  for attempt in range(4):
      try:
          resp = await client.post(url, json=payload, timeout=30.0)
          if resp.status_code not in (429, 500, 502, 503, 504):
              break  # succès ou erreur métier non retriable (4xx != 429)
          wait = min(2 ** attempt + random.uniform(0, 1), 30.0)
          logger.warning("[service] HTTP %s → retry %d/4 dans %.1fs", resp.status_code, attempt + 1, wait)
      except httpx.TimeoutException:
          wait = min(2 ** attempt + random.uniform(0, 1), 30.0)
          resp = None
      if attempt < 3:
          await asyncio.sleep(wait)

  if resp is None or resp.status_code >= 400:
      # Seulement après 4 tentatives échouées → erreur permanente
      errors.append(f"Échec après 4 tentatives (HTTP {resp.status_code if resp else 'timeout'})")
  ```
  > **Pourquoi le jitter est critique ?** Sans jitter, 800 instances retentent exactement à `t+1s`, `t+2s`, `t+4s` — recréant exactement le pic de charge qui a provoqué le 429. Le `random.uniform(0, 1)` désynchronise les retries pour que le pool se libère progressivement.

- [ ] **500 transformés en 429 côté serveur** : Vérifier que les appels retryables ne swallowent pas le 500 initial (qui peut venir du pool DB avant l'ajout du guard 429). Le retry doit inclure `500` dans la liste des codes retriables pendant la période de transition :
  ```bash
  # Vérifier que les retry loops incluent 429 ET 500 (pool overflow non wrappé)
  grep -rn 'status_code not in\|status_code in.*429' \
    */src/ --include='*.py' 2>/dev/null | grep -v '.venv'
  # ✅ Correct : (429, 500, 502, 503, 504) — 500 inclus pour les services sans guard 429
  # ⚠️ Accepté temporairement jusqu'à ce que tous les endpoints aient leur guard 429
  ```

#### 3.6. Détection de Code Dupliqué inter-conteneurs (NOUVEAU — issu du refacto 2026-05)

> **Contexte** : chaque fois qu'un bloc de code (JWT, OTel, auth) est copié-collé dans plusieurs services, la bibliothèque `shared/` doit être étendue pour l'absorber. Cette étape détecte automatiquement les duplications patentes avant qu'elles ne s'enkystent.

// turbo
```bash
python3 << 'EOF'
import os, re

SERVICES = [
    "users_api", "items_api", "competencies_api", "cv_api",
    "missions_api", "drive_api", "prompts_api", "analytics_mcp",
    "monitoring_mcp", "agent_hr_api", "agent_ops_api",
    "agent_missions_api", "agent_router_api",
]

# Patterns de code dupliqué connus — source de vérité : shared/
PATTERNS = [
    # ❌ Secret JWT défini localement (doit lever ValueError si absent)
    ("🔴 SECRET_KEY défini localement",
     r"^SECRET_KEY\s*=\s*os\.getenv\(",
     "→ Supprimer. shared.auth.jwt le fait au démarrage avec fail-fast."),
    # ❌ jwt.decode() local (doit passer par verify_jwt de shared)
    ("🔴 jwt.decode() local",
     r"jwt\.decode\(.*SECRET_KEY",
     "→ Remplacer par Depends(verify_jwt) de shared.auth.jwt."),
    # ❌ TracerProvider boilerplate (doit utiliser setup_mcp_tracer_provider)
    ("🟠 TracerProvider boilerplate local",
     r"TracerProvider\s*\(",
     "→ Remplacer par setup_mcp_tracer_provider() de shared.mcp_server_utils."),
    # ❌ Bloc OTel conditionnel (exporter if/elif/else)
    ("🟠 Bloc exporter OTel conditionnel local",
     r'os\.getenv\("TRACE_EXPORTER".*==.*"(http|gcp|grpc)"',
     "→ Déjà géré dans shared.mcp_server_utils.setup_mcp_tracer_provider()."),
    # ❌ auth.py local non-délégué (doit être une façade vers shared)
    ("🟠 auth.py local avec logique JWT propre",
     r"def verify_jwt\s*\(",
     "→ Vérifier que verify_jwt délègue à shared.auth.jwt et ne réimplémente pas."),
    # ❌ security = HTTPBearer() au niveau module dans les agents (doublon du Depends)
    ("🟡 security = HTTPBearer() au niveau module (agent)",
     r"^security\s*=\s*HTTPBearer\(\)",
     "→ Utiliser HTTPBearer() directement dans Depends() — pas de variable module."),
    # ❌ ALGORITHM hardcodé localement (doit venir de shared.auth.jwt)
    ("🟡 ALGORITHM hardcodé localement",
     r'^ALGORITHM\s*=\s*"HS256"',
     "→ Importer depuis shared.auth.jwt import ALGORITHM."),
    # ❌ agent_card() inline sans make_agent_card() (A2A duplication)
    ("🟡 agent_card() inline sans make_agent_card()",
     r'"defaultInputModes":\s*\["text"\]',
     "→ Utiliser agent_commons.a2a_utils.make_agent_card() pour factoriser."),
    # ❌ setup_logging() dupliqué (doit venir de shared.observability)
    ("🟡 setup_logging définie localement",
     r"def setup_logging\s*\(",
     "→ Importer depuis shared.observability.setup_logging."),
    # ❌ import jose/jwt dans les fichiers de tests de services (vérifier si local ou shared)
    ("🟡 import jose dans un test (hors history_routes)",
     r"from jose import jwt|import jose",
     "→ Vérifier : seules history_routes.py (get_unverified_claims) et shared/auth/jwt.py sont autorisés."),
]

base = os.getcwd()
violations = {}

for svc in SERVICES:
    path = os.path.join(base, svc)
    if not os.path.isdir(path):
        continue

    svc_violations = []
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in ("venv", ".venv", "__pycache__", "build", "dist", "test_env")]
        for fname in files:
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(root, fname)
            rel = fpath.replace(path + "/", "")
            try:
                lines = open(fpath).readlines()
            except Exception:
                continue
            for pname, pat, remedy in PATTERNS:
                for i, line in enumerate(lines, start=1):
                    if re.search(pat, line.strip()):
                        svc_violations.append((pname, remedy, rel, i, line.strip()[:100]))
                        break  # une seule occurrence par fichier par pattern

    if svc_violations:
        violations[svc] = svc_violations

if not violations:
    print("✅ Aucune duplication inter-conteneurs détectée. Tous les services délèguent à shared/.")
else:
    total = sum(len(v) for v in violations.values())
    print(f"❌ {total} violations de duplication détectées dans {len(violations)} services :\n")
    for svc, items in violations.items():
        print(f"\n{'─'*60}")
        print(f"  SERVICE: {svc}")
        print(f"{'─'*60}")
        for pname, remedy, rel, lineno, snippet in items:
            print(f"  {pname}")
            print(f"    📄 {rel}:{lineno}")
            print(f"    💬 {snippet}")
            print(f"    💡 {remedy}")
EOF
```

- [ ] **0 violations 🔴 rouge** (sécurité critique — bloquer le PR)
- [ ] **0 violations 🟠 orange** (OTel/auth dupliqués — planifier refacto avant prochain deploy)
- [ ] **< 3 violations 🟡 jaune** (mineurs — acceptable en feature branch courte)

> **Règle** : tout bloc identifié ci-dessus déjà présent dans `shared/` ou `agent_commons/` est une violation. La correction consiste à supprimer le code local et importer depuis la bibliothèque partagée. Documenter les exceptions légitimes avec `# Duplication intentionnelle — <raison>`.

#### 3.7. Cohérence des tests suite au refacto shared/

- [ ] **Tests qui importent l'ancien `auth.py` local** : après migration de `auth.py` en façade, vérifier que les tests pointent vers `shared.auth.jwt` :
  ```bash
  # Détecter les test_auth.py qui importent encore depuis le auth.py local
  grep -rn "from auth import verify_jwt\|from auth import.*SECRET_KEY" \
    */tests/ --include="*.py" 2>/dev/null | grep -v "# Duplication intentionnelle"
  ```
  Si trouvé → mettre à jour l'import en `from shared.auth.jwt import SECRET_KEY, verify_jwt`.

- [ ] **Tests qui moulent le module `auth` local au lieu de `shared.auth.jwt`** :
  ```bash
  # monkeypatch sur l'ancien chemin (cassé après migration)
  grep -rn 'monkeypatch.setattr.*"auth\.' */tests/ --include="*.py" 2>/dev/null
  ```
  Si trouvé → corriger le chemin de patch en `"shared.auth.jwt.<symbol>"`.

### Étape 4 : Exécution des Tests
Pour chaque service détecté, exécute la suite de tests pour vérifier la robustesse du code :

// turbo
```bash
for d in *_api *_mcp agent_*; do
  if [ -d "$d" ] && [ -d "$d/tests" ]; then
    echo "=== Tests : $d ==="
    cd "$d"
    echo "Exécution de pytest..."
    python3 -m pytest tests/ || echo "Erreur pytest dans $d"
    cd ..
  fi
done
```

### Étape 5 : Génération du Rapport
Une fois l'audit et les tests terminés, génère un artefact détaillé (ex: `rapport_audit_apis.md`).
Le rapport doit catégoriser les services (APIs Data, Agents) et contenir une matrice d'audit (avec emojis ✅ ❌) montrant précisément quels points de la **CHECKLIST DE CONFORMITÉ** de `AGENTS.md` sont respectés ou violés, un résumé de l'état des tests, accompagnés du plan d'action recommandé pour corriger les non-conformités.

Le rapport doit inclure une **section dédiée à l'audit Terraform LB** (issue de l'Étape 2b) avec :
- La carte de routage effective (externe + interne)
- Les incohérences de `path_prefix_rewrite` détectées
- Les ressources `google_compute_backend_service` orphelines
- Les sous-agents exposés directement sans justification

Le rapport doit inclure une **section dédiée à la résilience des appels externes** (issue de l'Étape 3.4) avec :
- La **carte des appels sortants** par service (URL cible · timeout · retry · criticité)
- La liste des violations détectées (appels sans timeout, swallow silencieux, absence de retry sur erreurs transitoires)
- La **priorisation des corrections** selon la criticité du chemin concerné :
  - 🔴 **Bloquant** : appel sans timeout sur un chemin critique (ex: auth, scoring, ingestion)
  - 🟠 **Majeur** : appel sans retry sur une ressource externe instable (ex: Vertex AI, Pub/Sub)
  - 🟡 **Mineur** : appel best-effort sans retry mais avec log (ex: FinOps reporting)
- Le **pattern de correction recommandé** pour chaque violation (tenacity, asyncio.wait_for, raise_for_status)
