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

### Étape 2c : Audit des dépendances Python & npm

> **Objectif** : détecter les packages obsolètes, les dépendances interdites, les versions non-harmonisées entre services et les opportunités d'optimisation FinOps (context caching, SDK upgrade).

// turbo
```bash
python3 - <<'DEPEOF'
import ssl, urllib.request, json, os, re

# --- 1. Collecte des requirements.txt ---
SERVICES = [
    "agent_hr_api", "agent_ops_api", "agent_missions_api", "agent_router_api",
    "analytics_mcp", "monitoring_mcp", "competencies_api", "cv_api",
    "missions_api", "drive_api", "items_api", "users_api", "prompts_api",
]

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def pypi_latest(pkg):
    try:
        url = f"https://pypi.org/pypi/{pkg}/json"
        with urllib.request.urlopen(url, timeout=8, context=ctx) as r:
            return json.load(r)["info"]["version"]
    except Exception:
        return "N/A"

# --- 2. Packages à contrôler (nom PyPI exact) ---
KEY_PACKAGES = [
    "fastapi", "uvicorn", "google-adk", "google-genai", "mcp",
    "opentelemetry-api", "pydantic", "httpx", "redis", "sqlalchemy",
    "PyJWT", "bcrypt", "tenacity", "prometheus-fastapi-instrumentator",
    "google-cloud-pubsub", "google-cloud-storage", "google-cloud-alloydb-connector",
    "google-auth", "langchain-text-splitters", "json-repair", "grpcio",
    "testcontainers", "fakeredis", "pgvector", "python-docx",
]

# --- 3. Dépendances interdites (sécurité / obsolètes) ---
FORBIDDEN = {
    "python-jose": "❌ INTERDIT — migré vers PyJWT>=2.12.0 (CVE-2022-29217)",
    "jose": "❌ INTERDIT — alias python-jose, utiliser PyJWT",
    "pyjwt<2.8": "❌ INTERDIT — vulnérabilité decode options (PyJWT<2.8)",
    "litellm": "⚠️ À contraindre — version non pinned = risque breaking change",
}

# --- 4. Fetch latest versions ---
print("[1/3] Récupération des dernières versions PyPI...")
latest = {pkg: pypi_latest(pkg) for pkg in KEY_PACKAGES}
print(f"       {len(KEY_PACKAGES)} packages vérifiés.")

# --- 5. Parsing et analyse par service ---
print("\n[2/3] Analyse des requirements.txt par service...\n")
base = os.getcwd()
all_violations = {}

for svc in SERVICES:
    req_path = os.path.join(base, svc, "requirements.txt")
    if not os.path.exists(req_path):
        print(f"  ⚠️  {svc}: requirements.txt ABSENT")
        continue
    lines = open(req_path).read().splitlines()
    violations = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Détection des packages interdits
        for forbidden, msg in FORBIDDEN.items():
            if stripped.lower().startswith(forbidden.lower()):
                violations.append(f"   {msg}  [{stripped}]")
    all_violations[svc] = violations
    status = "❌" if violations else "✅"
    print(f"  {status}  {svc}: {len(violations)} violations")
    for v in violations:
        print(v)

# --- 6. Delta versions (contrainte actuelle vs PyPI latest) ---
print("\n[3/3] Matrice delta contraintes vs PyPI latest:\n")
print(f"{'Package':<40} {'PyPI latest':<15} Contrainte représentative")
print("-" * 90)

# Représentation consolidée (premier service contenant le package)
current_constraints = {}
for svc in SERVICES:
    req_path = os.path.join(base, svc, "requirements.txt")
    if not os.path.exists(req_path):
        continue
    for line in open(req_path).read().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        for pkg in KEY_PACKAGES:
            if stripped.lower().startswith(pkg.lower()):
                if pkg not in current_constraints:
                    current_constraints[pkg] = stripped

for pkg in KEY_PACKAGES:
    constraint = current_constraints.get(pkg, "ABSENT")
    ver = latest.get(pkg, "N/A")
    icon = "✅" if constraint != "ABSENT" else "⚠️"
    print(f"{icon} {pkg:<38} {ver:<15} {constraint}")

# --- 7. Résumé ---
total_violations = sum(len(v) for v in all_violations.values())
if total_violations == 0:
    print("\n✅ Aucune dépendance interdite détectée dans les services.")
else:
    print(f"\n❌ {total_violations} violation(s) de dépendances interdites détectées.")
DEPEOF
```

Checklist de l'audit des dépendances :

- [ ] **Zéro dépendance interdite** : `python-jose`, `jose` absents de tous les `requirements.txt`. Toute occurrence → migrer vers `PyJWT>=2.12.0`.
- [ ] **`litellm` contraint** : la version doit être pinned (`litellm>=X.Y.0`) ou verrouillée pour éviter un breaking change imprévisible lors d'un rebuild Cloud Run.
- [ ] **`PyJWT>=2.12.0`** : version minimale obligatoire (fix `options={"verify_signature": False}` utilisé dans `auth_router.py`).
- [ ] **`uvicorn>=0.47.0`** : fix du SIGTERM lifespan Cloud Run (réduction des 502 au redémarrage).
- [ ] **`google-genai>=2.0.0`** : API unifiée `genai.Client()` + context caching. Contrainte `>=1.x` interdite.
- [ ] **`pydantic>=2.13.0`** : harmonisation sur tous les services (fix `model_rebuild()` async + +20% sérialisation).
- [ ] **`prometheus-fastapi-instrumentator>=7.0.0`** : API stable, fix compteurs sous concurrence.
- [ ] **Pas de version pinned exacte** (`==X.Y.Z`) dans les `requirements.txt` de production : préférer `>=X.Y.Z` pour bénéficier des patches de sécurité automatiquement.
- [ ] **Context caching Gemini activé** : vérifier la présence de `gemini_cache.py` dans `competencies_api/src/competencies/` et `cv_api/src/`. Sans ce module, les appels Gemini répétitifs (scoring bulk, taxonomie) ne bénéficient pas de la réduction FinOps -30à-50%.
  ```bash
  # Vérifier la présence des modules de context caching
  ls competencies_api/src/competencies/gemini_cache.py 2>/dev/null && echo "✅ competencies_api" || echo "❌ competencies_api — gemini_cache.py absent"
  ls cv_api/src/gemini_cache.py 2>/dev/null && echo "✅ cv_api" || echo "❌ cv_api — gemini_cache.py absent"
  ```
- [ ] **Frontend npm à jour** : vérifier que `vue`, `vite`, `vitest` utilisent le caret `^` (ex: `^3.5.x`) — les patches sont résolus automatiquement au prochain `npm install`.
  ```bash
  # Détecter les versions pinned exactes dans package.json (risque de gel sur vulnérabilité)
  node -e "const d=require('./frontend/package.json'); const all={...d.dependencies,...d.devDependencies}; Object.entries(all).filter(([k,v])=>!v.startsWith('^')&&!v.startsWith('~')).forEach(([k,v])=>console.log('\u26a0\ufe0f',k,v))" 2>/dev/null || echo "N/A"
  ```

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

#### 3.6. Détection Générale de Code Dupliqué inter-conteneurs

> **Objectif** : identifier **tout** bloc de code similaire entre services, sans liste de patterns pré-établie.
> Deux niveaux : clones textuels (pylint R0801) + similarité structurelle par paires de fichiers (difflib).

**Niveau 1 — Clones textuels avec pylint R0801**

// turbo
```bash
SERVICES="users_api items_api competencies_api cv_api missions_api drive_api prompts_api analytics_mcp monitoring_mcp agent_hr_api agent_ops_api agent_missions_api agent_router_api agent_commons shared"
PY_FILES=""
for svc in $SERVICES; do
  [ -d "$svc" ] && PY_FILES="$PY_FILES $(find $svc -name '*.py' \
    ! -path '*/venv/*' ! -path '*/.venv/*' ! -path '*/__pycache__/*' \
    ! -path '*/build/*' ! -path '*/dist/*' ! -path '*/test_env/*' \
    ! -path '*/migrations/*' ! -path '*/changelogs/*' 2>/dev/null)"
done
echo "=== PYLINT R0801 — Clones textuels (min 4 lignes similaires) ==="
echo "Fichiers : $(echo $PY_FILES | wc -w)"
python3 -m pylint $PY_FILES \
  --disable=all --enable=R0801 \
  --min-similarity-lines=4 \
  --ignore-comments=yes --ignore-docstrings=yes --ignore-imports=yes \
  2>/dev/null | grep -E "^Similar|^=|^\s+[0-9]+:" | head -100 \
  || echo "ℹ️  pylint non disponible — pip install pylint"
```

**Niveau 2 — Similarité structurelle par paires de fichiers (difflib)**

Le script suivant compare **toutes les paires de fichiers Python** entre tous les services. Il ne présuppose aucun pattern — il détecte toute similarité au-dessus du seuil configuré.

// turbo
```bash
python3 << 'PYEOF'
import os, sys
from difflib import SequenceMatcher
from itertools import combinations
from pathlib import Path

SERVICES = [
    "users_api", "items_api", "competencies_api", "cv_api",
    "missions_api", "drive_api", "prompts_api", "analytics_mcp",
    "monitoring_mcp", "agent_hr_api", "agent_ops_api",
    "agent_missions_api", "agent_router_api", "agent_commons",
]
EXCLUDE_DIRS = {
    "venv", ".venv", "__pycache__", "build", "dist", "test_env",
    "migrations", "changelogs", "zenika_shared_schemas.egg-info",
}
EXCLUDE_FILES = {"conftest.py"}

SIMILARITY_THRESHOLD = 0.40
MIN_SIGNIFICANT_LINES = 20
MIN_MATCHING_LINES = 8
BLOCK_MIN_SIZE = 6


def normalize(path: Path) -> list:
    """Lignes significatives : sans blancs, commentaires, imports, decorateurs."""
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return []
    out = []
    for line in raw:
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            continue
        if s[:3] in ('"""', "'''"):
            continue
        if s.startswith("@"):
            continue
        if s.startswith("import ") or s.startswith("from "):
            continue
        out.append(s)
    return out


def collect(base: str) -> dict:
    result = {}
    for svc in SERVICES:
        p = Path(base) / svc
        if not p.is_dir():
            continue
        files = []
        for f in p.rglob("*.py"):
            if any(part in EXCLUDE_DIRS for part in f.parts):
                continue
            if f.name in EXCLUDE_FILES:
                continue
            if len(normalize(f)) >= MIN_SIGNIFICANT_LINES:
                files.append(f)
        result[svc] = files
    return result


def extract_common_blocks(la: list, lb: list) -> list:
    m = SequenceMatcher(None, la, lb, autojunk=False)
    return [la[b.a:b.a + b.size] for b in m.get_matching_blocks() if b.size >= BLOCK_MIN_SIZE]


base = os.getcwd()
files_by_svc = collect(base)
total_files = sum(len(v) for v in files_by_svc.values())
print(f"Services : {len(files_by_svc)}  |  Fichiers : {total_files}  (>= {MIN_SIGNIFICANT_LINES} lignes significatives)")
print(f"Seuil : {SIMILARITY_THRESHOLD*100:.0f}% similarite  |  {MIN_MATCHING_LINES} lignes communes min\n")

pairs, clones = 0, []
for svc_a, svc_b in combinations(sorted(files_by_svc), 2):
    for fa in files_by_svc[svc_a]:
        la = normalize(fa)
        for fb in files_by_svc[svc_b]:
            lb = normalize(fb)
            pairs += 1
            m = SequenceMatcher(None, la, lb, autojunk=False)
            ratio = m.ratio()
            matching = sum(b.size for b in m.get_matching_blocks())
            if ratio >= SIMILARITY_THRESHOLD and matching >= MIN_MATCHING_LINES:
                clones.append({
                    "ratio": ratio,
                    "matching": matching,
                    "fa": str(fa).replace(base + "/", ""),
                    "fb": str(fb).replace(base + "/", ""),
                    "blocks": extract_common_blocks(la, lb),
                })

print(f"Paires comparees : {pairs}")
print("-" * 70)

if not clones:
    print("OK Aucun clone detecte — architecture DRY conforme.")
    sys.exit(0)

clones.sort(key=lambda c: c["ratio"], reverse=True)
print(f"ATTENTION {len(clones)} paires similaires detectees :\n")
for c in clones:
    pct = c["ratio"] * 100
    severity = "BLOQUANT" if pct >= 70 else ("MAJEUR" if pct >= 55 else "MINEUR")
    print(f"[{severity}] {pct:.1f}%  |  {c['matching']} lignes communes")
    print(f"  A: {c['fa']}")
    print(f"  B: {c['fb']}")
    if c["blocks"]:
        first_block = c["blocks"][0]
        sample = first_block[:8]
        print(f"  Bloc commun le plus long ({len(first_block)} lignes — extrait) :")
        for line in sample:
            print(f"    {line[:110]}")
        if len(first_block) > 8:
            print(f"    ... +{len(first_block) - 8} lignes")
        if len(c["blocks"]) > 1:
            print(f"  ({len(c['blocks'])} blocs communs distincts au total)")
    print()

print("-" * 70)
print("Criticite : BLOQUANT >=70%  |  MAJEUR 55-70%  |  MINEUR 40-55%")
print("Correction : factoriser dans shared/ ou agent_commons/")
print("Exception  : annoter # Duplication intentionnelle — <raison>")
PYEOF
```

**Niveau 3 — Cohérence des tests post-refacto shared/**

// turbo
```bash
echo "=== Tests qui importent l'ancien auth.py local (doivent pointer vers shared.auth.jwt) ==="
grep -rn "from auth import verify_jwt\|from auth import.*SECRET_KEY" \
  */tests/ --include="*.py" 2>/dev/null \
  | grep -v "# Duplication intentionnelle" \
  && echo "CORRIGER : remplacer par 'from shared.auth.jwt import ...'" \
  || echo "OK — Aucun import auth local dans les tests"

echo ""
echo "=== monkeypatch sur chemin 'auth.' (casse apres migration vers shared) ==="
grep -rn 'monkeypatch\.setattr.*"auth\.' */tests/ --include="*.py" 2>/dev/null \
  && echo "CORRIGER : utiliser 'shared.auth.jwt.<symbol>'" \
  || echo "OK — Aucun monkeypatch sur chemin auth local"
```

**Seuils de conformité :**

| Criticité | Seuil similarité | Action attendue |
|---|---|---|
| 🔴 **Bloquant** | ≥ 70% | Bloquer le PR — refacto immédiat vers `shared/` ou `agent_commons/` |
| 🟠 **Majeur** | 55–70% | Planifier avant prochain deploy |
| 🟡 **Mineur** | 40–55% | Backlog — acceptable en feature branch courte |

> **Exclusions** : `conftest.py`, migrations Liquibase, fixtures de test.
> Toute duplication jugée légitime doit être annotée `# Duplication intentionnelle — <raison>` pour être tracée et exclue des futures analyses.


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

Le rapport doit inclure une **section dédiée à l'audit des dépendances** (issue de l'Étape 2c) avec :
- La **matrice de delta** par package clé : contrainte actuelle vs dernière version PyPI/npm
- Les **violations critiques** (`python-jose`, JWT vulnérable, `google-genai<2.0`) classées par priorité :
  - 🔴 **Bloquant** : dépendance interdite ou CVE connue (ex: `python-jose` → PyJWT)
  - 🟠 **Majeur** : version major disponible avec gain significatif (FinOps, sécurité OIDC)
  - 🟡 **Mineur** : patch disponible — couvert par la contrainte `>=X.Y.Z` actuelle
- Le **statut context caching Gemini** : présence de `gemini_cache.py`, TTL configuré, services couverts
- Le **plan de bump** recommandé : liste des `requirements.txt` à modifier avec les commandes `sed` exactes

Le rapport doit inclure une **section dédiée à la résilience des appels externes** (issue de l'Étape 3.4) avec :
- La **carte des appels sortants** par service (URL cible · timeout · retry · criticité)
- La liste des violations détectées (appels sans timeout, swallow silencieux, absence de retry sur erreurs transitoires)
- La **priorisation des corrections** selon la criticité du chemin concerné :
  - 🔴 **Bloquant** : appel sans timeout sur un chemin critique (ex: auth, scoring, ingestion)
  - 🟠 **Majeur** : appel sans retry sur une ressource externe instable (ex: Vertex AI, Pub/Sub)
  - 🟡 **Mineur** : appel best-effort sans retry mais avec log (ex: FinOps reporting)
- Le **pattern de correction recommandé** pour chaque violation (tenacity, asyncio.wait_for, raise_for_status)
