# 📜 Projet Zenika Console Agent - Golden Rules

Ce document dicte le comportement, les standards et les contraintes non négociables pour l'Agent Antigravity et les développeurs. **Le non-respect de ces règles cassera la plateforme.**

> **Convention de lecture** : Les règles marquées 🔵 s'appliquent aux **APIs data** (`users_api`, `items_api`, etc.), celles marquées 🟣 aux **agents** (`agent_*`), et celles sans marqueur s'appliquent **à tous les services**.

---

## ✅ CHECKLIST DE CONFORMITÉ (Nouvelles fonctionnalités)

Avant tout PR / déploiement, vérifiez chaque point selon le type de service :

**Pour toute API data** 🔵 :
- [ ] Endpoint protégé par `dependencies=[Depends(verify_jwt)]` sur son `APIRouter` ?
- [ ] Tool MCP créé ou mis à jour dans `mcp_server.py` ?
- [ ] Route `/mcp/{path:path}` proxy vers le sidecar MCP présente dans `main.py` ?
- [ ] `inject(headers)` présent dans **chaque** appel `httpx` sortant ?
- [ ] Changeset Liquibase ajouté dans `db_migrations/changelogs/` (avec section `rollback`) ?
- [ ] Cache Redis invalidé sur les mutations (POST, PUT, DELETE) ?
- [ ] Tests de contrat MCP ajoutés dans `test_mcp_tools.py` ?
- [ ] Tout endpoint liste utilise la **pagination** (`skip`/`limit` + `total`) plutôt qu'une hard limit ?

**Pour tout agent** 🟣 :
- [ ] `verify_jwt()` (validation signature HS256 + claim `sub`) présente localement dans `main.py` ?
- [ ] `protected_router = APIRouter(dependencies=[Depends(verify_jwt)])` utilisé ?
- [ ] `inject(headers)` présent dans chaque appel HTTP sortant vers les APIs ou sous-agents ?
- [ ] `auth_header_var` propagé aux clients MCP pour transmettre le JWT aux APIs cibles ?
- [ ] Tests de session, guardrail, et JWT ajoutés ?
- [ ] `log_ai_consumption` appelé après chaque inférence LLM (tracking FinOps) ?

**Pour tous les services** :
- [ ] `Instrumentator().instrument(app).expose(app)` dans `main.py` ?
- [ ] `FastAPIInstrumentor.instrument_app(app, excluded_urls="health,metrics")` dans `main.py` ?
- [ ] Aucun modèle IA hardcodé (utiliser les variables d'environnement) ?
- [ ] Dockerfile multi-stage, USER non-root, CMD sans shell, `.dockerignore` présent ?
- [ ] **Aucune modification de fichier `VERSION` ni de version dans les fichiers `envs/*.yaml`** — le bump de version appartient exclusivement à `deploy.sh` ?
- [ ] Fichier `router.py` / `main.py` sous le seuil bloquant défini en §14 ?
- [ ] `test_zero_trust.py` présent dans la suite pytest du service ?
- [ ] `@app.exception_handler(Exception)` global implémenté (APIs data uniquement) ?

---

## ⚠️ 1. DIRECTIVES STRICTES ANTIGRAVITY (LLM)

> Cette section est prioritaire sur toutes les autres pour l'agent IA.

1. **Discipline YAML** : Les fichiers `.yml` / `.yaml` exigent 2 espaces d'indentation stricte. Les Tabulations sont **strictement interdites**.
2. **Design Pattern `Container-First`** : Utilisez systématiquement le même `container_name` et `hostname` dans l'écosystème Docker.
3. **Idempotence et Doublons** : Avant de créer ou d'ingérer une ressource, anticipez les redondances dans l'état (les outils LLM ou Base de données doivent gérer silencieusement ou proprement les entités qui existent déjà).
4. **Configuration Centralisée des Modèles IA** : Il est **STRICTEMENT INTERDIT** de hardcoder des constantes de modèles (ex: `gemini-2.5-flash`) dans le code (comme `agent_router_api`, `agent_hr_api`, `agent_ops_api` ou `cv_api`). Ce référentiel doit être unifié via des variables d'environnement centralisées (facilite l'A/B testing et le tracking FinOps).
5. **Auto-génération Sécurisée de Data** : Lors de la création d'entités avec contraintes fortes (ex: création dynamique d'utilisateurs sans mot de passe spécifié par l'humain), les tools du LLM **doivent impérativement** auto-générer la dépendance silencieuse plutôt que d'échouer avec une erreur (ex: HTTP 422 Unprocessable Entity).
6. **Robustesse de Création de Fichiers (Write_To_File)** : Lors de l'utilisation d'outils d'écriture (comme `write_to_file`), les paramètres `TargetFile` et `Overwrite` **DOIVENT IMPÉRATIVEMENT** être générés en tout premier dans l'objet JSON (avant `CodeContent`) pour éviter la saturation de la file de streaming. De plus, il est **strictement interdit** d'écrire des fichiers via des commandes bash (`cat <<EOF` ou `echo`), car une erreur de quote figera le processus en attente d'input, bloquant définitivement l'agent.
7. **Privilège des Appels API (Environnement Dev)** : Lors de tests ou de vérifications métiers, privilégiez les appels API réels sur l'URL de l'environnement dev (définie par la variable `$DEV_BASE_URL` ou l'output Terraform `dev_url`) plutôt que d'exécuter des scripts locaux. Récupérez le token d'authentification via un appel à `auth/login` avec le compte admin (le mot de passe doit être récupéré dynamiquement via les outputs ou variables de Terraform — ne jamais l'écrire en clair).
8. **Standard Python Imports** : Les imports Python **DOIVENT** être placés en haut du fichier (conformément à la PEP 8). Évitez les imports locaux dans les fonctions, sauf cas exceptionnel de dépendance circulaire.
9. **Interpréteur Python** : Utilisez systématiquement la commande `python3` au lieu de `python` pour toute exécution de script ou commande dans le terminal de l'utilisateur.
10. **Failfast & Zéro Erreur Silencieuse** : Il est **STRICTEMENT INTERDIT** d'ignorer silencieusement des erreurs (ex: `except Exception: pass`, ou un simple logger non accompagné d'une levée d'exception). Les services doivent adopter une approche "failfast". Toute exception doit soit être interrompue formelquement (`raise`) pour que le système centralisé gère l'erreur, soit être retournée explicitement sous la forme `{"success": false, "error": ...}` (ex: Tools MCP). Conserver des erreurs silencieuses corrompt la garantie d'intégrité de la plateforme.
11. **🚫 INTERDICTION ABSOLUE — Build Docker & Déploiement GCP** : L'agent Antigravity a **formellement et absolument interdit** d'exécuter toute commande de build ou de déploiement vers GCP. Son périmètre d'action se limite **exclusivement à la modification des fichiers source**. Les commandes suivantes sont **STRICTEMENT PROSCRITES** dans toute circonstance, même si le user le demande explicitement :
    - `docker build`, `docker push`, `docker-compose up --build`
    - `gcloud run deploy`, `gcloud builds submit`, `gcloud artifacts docker push`
    - `terraform apply`, `terraform destroy`
    - Tout script wrapper (`deploy.sh`, `deploys.sh`, `manage_env.py apply`, etc.) invoquant l'une des commandes ci-dessus
    
    **Comportement attendu** : L'agent modifie les fichiers, puis s'arrête et informe le user que le build/déploiement lui incombe. Il peut suggérer la commande à exécuter, mais **ne doit jamais la lancer**. Violer cette règle compromet la stabilité de la plateforme de production.

    > **🚨 RÈGLE ANTI-HALLUCINATION IA** : Si tu t'apprêtes à appeler un outil `run_command` ou `execute_docker` / `execute_gcloud` / `execute_terraform` avec un argument de type `build`, `push`, `deploy`, `apply` ou `destroy`, tu **DOIS immédiatement t'arrêter** et retourner le message : *"Je ne peux pas exécuter cette commande. Mon périmètre se limite à la modification des fichiers source. Veuillez lancer le build/déploiement vous-même."*

12. **🚫 INTERDICTION ABSOLUE — Bump de Version** : L'agent Antigravity a **formellement et absolument interdit** de modifier les numéros de version, quelle que soit la raison. La gestion des versions est la **responsabilité exclusive de `deploy.sh`**. Sont strictement interdits :
    - Modifier le contenu d'un fichier `VERSION` (ex: `echo "v0.1.5" > VERSION`)
    - Modifier les champs `*_version` dans les fichiers `platform-engineering/envs/*.yaml` (ex: `cv_api_version: "v0.0.148"`)
    - Incrémenter une version dans un `pyproject.toml`, `package.json`, `setup.py` ou tout autre manifeste de packaging

    **Comportement attendu** : L'agent modifie les fichiers source, puis s'arrête. `deploy.sh` est le seul processus autorisé à détecter les changements et à bumper la version correspondante.

    > **🚨 RÈGLE ANTI-HALLUCINATION IA** : Si tu t'apprêtes à écrire dans un fichier `VERSION`, ou à modifier une clé `*_version` dans un fichier `envs/*.yaml`, tu **DOIS immédiatement t'arrêter** et retourner le message : *"Je ne peux pas modifier les numéros de version. C'est la responsabilité exclusive de `deploy.sh`. Veuillez lancer le script de déploiement pour que la version soit incrémentée automatiquement."*

13. **🚫 INTERDICTION ABSOLUE — Validation d'interface via Browser** : L'agent Antigravity a **formellement et absolument interdit** d'utiliser le `browser_subagent` (ou tout outil d'automatisation de navigateur) pour valider, tester ou inspecter visuellement l'interface de la plateforme. L'application est **protégée par authentification JWT** : tout accès via un navigateur automatisé se soldera systématiquement par un écran de login ou une erreur 401, rendant la validation impossible et la tentative inutile.

    **Comportement attendu** : Pour valider une interface, l'agent doit :
    - Inspecter le code source Vue.js concerné
    - Vérifier la cohérence des API calls via les endpoints API réels (avec token JWT récupéré dynamiquement)
    - S'appuyer sur les logs Cloud Run ou Grafana pour les comportements runtime
    - Demander au user de valider visuellement si nécessaire

    > **🚨 RÈGLE ANTI-HALLUCINATION IA** : Si tu t'apprêtes à appeler `browser_subagent` pour naviguer sur la plateforme ou valider une interface, tu **DOIS immédiatement t'arrêter** et retourner le message : *"Je ne peux pas utiliser le navigateur pour valider l'interface. L'application est protégée par JWT — la session browser sera bloquée sur la page de login. Veuillez valider visuellement vous-même ou me décrire ce que vous observez."*

---

## 🏗️ 2. ARCHITECTURE & STACK

L'environnement est strictement micro-serviciel et repose sur **Docker Compose** (dev local) et **Cloud Run** (GCP).

### APIs Data (producteurs MCP) 🔵
Services exposant une logique métier et un serveur MCP consommable par les agents :
- `users_api` — Gestion des utilisateurs, authentification, JWT
- `items_api` — Gestion des items et catégories
- `competencies_api` — Arbre de compétences, évaluation IA des consultants, scoring Vertex AI Batch
- `cv_api` — Analyse et stockage multimodale des CVs
- `missions_api` — Gestion des missions client (documents)
- `drive_api` — Synchronisation Google Drive
- `prompts_api` — Gestion des system prompts des agents

### Agents IA (consommateurs MCP) 🟣
Services orchestrant des LLMs via Google ADK. Ils **consomment** des tools MCP — ils n'en exposent **pas** :
- `agent_router_api` : routeur intelligent, délègue aux sous-agents via le protocole A2A (FastAPI + Google ADK + Gemini).
- `agent_hr_api` : sous-agent spécialisé RH (compétences, CVs, utilisateurs).
- `agent_ops_api` : sous-agent spécialisé Ops (missions, items, opérationnel).
- `agent_missions_api` : sous-agent spécialisé gestion documentaire des missions.
- Les sous-agents communiquent via HTTP (A2A) et **non** via SSE pour rester stateless.

### MCP Natif (services MCP standalone) 🟤
Services exposant uniquement des tools MCP via HTTP, sans logique métier en base propre :
- `analytics_mcp` — Données marché BigQuery, tracking FinOps (`log_ai_consumption`), outils GCP infra (Cloud Logging, Cloud Run). Exposé via HTTP (`/mcp/tools` + `/mcp/call`) et non via sidecar stdio. **À terme, à scinder en `analytics_mcp` + `monitoring_mcp`** (voir todo.md ADR12 Axe 3).

### Infrastructure
- **Frontend** : `frontend` (Vue.js + proxy Nginx pointant `/api/` vers `agent_router_api`).
- **Data Layer** : PostgreSQL (pgvector) · Redis (namespaces DB isolés, un DB par service — voir règle §6) · Cache Sémantique dans `agent_router_api`.
- **FinOps & Data Analytics** : L'utilisation de l'IA est trackée et centralisée dans Google BigQuery (table `ai_usage` partitionnée par jour) via `analytics_mcp`.
  > **RÈGLE OBLIGATOIRE - Localisation BigQuery** : Tous les datasets et requêtes BigQuery **DOIVENT IMPÉRATIVEMENT** utiliser la localisation `europe-west1` (ou `EU`). Les clients `bigquery.Client` doivent systématiquement inclure le paramètre `location="europe-west1"` pour éviter des erreurs 404 de "Dataset not found in location US".
- **Réseau interne** : `monitoring_net` est obligatoire pour la résolution DNS.

---

## 🤖 3. MCP & AGENT ORCHESTRATION

### Principe fondamental — Producteurs vs Consommateurs

> **RÈGLE IMPÉRATIVE** : Les APIs data **exposent** un serveur MCP (`mcp_server.py`). Les agents **consomment** des tools MCP via `agent_commons.mcp_client`. Ne jamais créer de `mcp_server.py` dans un dossier `agent_*`.

| Type de service | `mcp_server.py` | `mcp_client` | Route `/mcp/{path}` | BDD propre |
|---|---|---|---|---|
| API data 🔵 | ✅ Sidecar stdio | ❌ Non | ✅ Proxy vers sidecar | ✅ PostgreSQL |
| Agent 🟣 | ❌ Interdit | ✅ Consume | ❌ Non pertinent | ❌ Stateless |
| MCP Natif 🟤 | ✅ HTTP direct | ❌ Non | ✅ Exposé directement | ❌ IAM/externe |

### APIs data — Règles MCP 🔵

- **Serveur MCP** (`mcp_server.py`) : Chaque API data expose ses fonctionnalités en tant que tools MCP via un processus sidecar stdio.
- **Règle de fonctionnalité** : Toute nouvelle route / logique métier implémentée dans une API data **DOIT IMPÉRATIVEMENT** faire l'objet d'un outil (`Tool`) exposé dans le `mcp_server.py` de cette même API.
- **Route proxy** : La route `@app.api_route("/mcp/{path:path}")` doit être présente dans `main.py` pour relayer les appels MCP vers le sidecar (`MCP_SIDECAR_URL`).
- **Convention de nommage** : Les tools MCP utilisent le format `snake_case` VERBE_RESSOURCE (ex: `get_user_by_id`, `create_competency`, `list_missions`).
- **Gestion d'erreur** : Un tool ne doit **jamais** laisser propager une exception non catchée. Il retourne systématiquement un dictionnaire structuré : `{"success": false, "error": "message lisible"}` en cas d'échec.
- **Pagination obligatoire** : Tout endpoint retournant une liste **DOIT** exposer des paramètres de pagination (`skip`/`limit` ou `page`/`page_size`) plutôt qu'une limite hard-codée. Une hard limit sans pagination est un **bug** — elle masque des données et devient un goulot d'étranglement silencieux.
  ```python
  # ✅ CORRECT — pagination explicite
  @router.get("/")
  async def list_items(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
      total = db.query(Item).count()
      items = db.query(Item).offset(skip).limit(limit).all()
      return {"items": items, "total": total, "skip": skip, "limit": limit}

  # ❌ INTERDIT — hard limit silencieuse
  async def list_items(db: Session = Depends(get_db)):
      return db.query(Item).limit(100).all()  # les données au-delà de 100 sont invisibles
  ```
  - La réponse DOIT inclure `total` (nombre total d'entrées) pour permettre au client de calculer le nombre de pages.
  - La valeur par défaut de `limit` doit être raisonnable (ex: 50) mais configurable par le client jusqu'à un maximum (ex: 500).
  - Les tools MCP exposant des listes DOIVENT également accepter `skip` et `limit` et les transmettre à la requête SQL.

- **Pagination obligatoire lors de la consommation d'APIs externes ou internes** : Toute lecture de ressource distante (API interne de la plateforme, Google Drive, BigQuery, Cloud Logging, Pub/Sub...) qui peut retourner plus d'un élément **DOIT** utiliser la pagination ou les page tokens de l'API cible. Il est **formellement interdit** de supposer qu'une réponse unique contient l'intégralité des données.
  ```python
  # ✅ CORRECT — Google Drive avec page tokens
  page_token = None
  while True:
      response = service.files().list(
          q=query, pageSize=100, pageToken=page_token
      ).execute()
      files.extend(response.get("files", []))
      page_token = response.get("nextPageToken")
      if not page_token:
          break

  # ❌ INTERDIT — appel unique sans pagination
  response = service.files().list(q=query).execute()  # retourne max 100 fichiers silencieusement
  files = response.get("files", [])  # données tronquées invisiblement

  # ✅ CORRECT — BigQuery avec pagination via client iterable
  query_job = client.query(sql)  # utiliser l'itération native du client
  rows = list(query_job)  # BigQuery pagine automatiquement en interne

  # ✅ CORRECT — API interne avec skip/limit
  async def fetch_all_users(client: httpx.AsyncClient, headers: dict) -> list:
      users, skip, limit = [], 0, 100
      while True:
          r = await client.get(f"{USERS_URL}/users/?skip={skip}&limit={limit}", headers=headers)
          batch = r.json().get("users", [])
          users.extend(batch)
          if len(batch) < limit:
              break
          skip += limit
      return users
  ```
  **Règle universelle** : si l'API cible expose un `nextPageToken`, `next_page_token`, `next`, ou un `total` supérieur au count reçu → boucler. Ne jamais s'arrêter à la première réponse.


### Agents — Règles d'orchestration MCP 🟣

- **Enregistrement ADK (`agent.py`)** : Les outils distants doivent être mappés en tant que fonctions ou instances natives dans le fichier `agent.py` de chaque agent avec des **Docstrings riches** (cruciales pour que le LLM sache quand les appeler).
- **Propagation JWT** : L'`auth_header_var` (contextvars) doit être alimenté depuis le Bearer reçu sur `/query` ou `/a2a/query` avant tout appel MCP sortant.
- **Direction HTTP uniquement** : Privilégier les flux **HTTP standards (REST)** au détriment du SSE pour rester stateless.
- **Pas de `mcp_server.py`** : Un agent ne doit jamais exposer un serveur MCP — il n'a rien à offrir aux autres agents via ce protocole. La communication inter-agents utilise exclusivement le protocole A2A (HTTP).
- **Résilience A2A** : Chaque appel inter-agent DOIT implémenter un retry sur les erreurs réseau/5xx et un **mode dégradé** (`degraded: True` dans la réponse) si toutes les tentatives échouent, plutôt que de propaguer une exception 500.
- **Standard timeout/retry `httpx` (OBLIGATOIRE)** : Tout appel HTTP sortant inter-service DOIT utiliser un client avec timeout explicite et stratégie de retry exponentielle :
  ```python
  # Pattern standard — à utiliser dans TOUT appel inter-service
  async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0)) as client:
      for attempt in range(3):
          try:
              res = await client.post(url, headers=headers, json=payload)
              res.raise_for_status()
              break
          except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as e:
              if attempt == 2:
                  raise
              await asyncio.sleep(2 ** attempt)  # backoff : 1s, 2s
  ```
  L'absence de timeout sur un appel `httpx` est un **bug** — elle provoque des cascades de timeouts sur l'ensemble de la plateforme.
- **Tracking FinOps (`log_ai_consumption`) OBLIGATOIRE** : Après chaque appel LLM générant des tokens, l'agent DOIT enregistrer la consommation via `analytics_mcp` :
  ```python
  # OBLIGATOIRE — à appeler après chaque inférence Gemini/Vertex
  await log_ai_consumption(
      model=os.getenv("GEMINI_MODEL"),
      input_tokens=usage.prompt_token_count,
      output_tokens=usage.candidates_token_count,
      user_id=payload["sub"],
      service="agent_hr_api"  # nom du service courant
  )
  ```
  Omettre cet appel constitue une **violation FinOps** — les coûts ne sont plus imputés et les tableaux de bord BigQuery sont faussés.

### Vertex AI Batch Pipeline — Pattern partagé 🔵

Deux services utilisent Vertex AI Batch Prediction pour des opérations LLM massives :

| Service | Fichier | Usage |
|---|---|---|
| `cv_api` | `src/services/bulk_service.py` | Extraction structurée des CVs (JSONL → GCS → Vertex → apply) |
| `competencies_api` | `src/competencies/scoring_service.py` | Scoring IA compétences (user × compétence → score 0-5) |

#### Règles obligatoires pour tout nouveau pipeline Vertex Batch

1. **Bucket GCS partagé `BATCH_GCS_BUCKET`** : Utiliser `google_storage_bucket.cv_batch` (Terraform). Les pipelines s'isolent via des **préfixes distincts** dans la clé GCS :
   - `bulk-reanalyse/` → cv_api
   - `bulk-scoring/` → competencies_api
   - ⚠️ Créer un nouveau bucket uniquement si le pipeline nécessite une région ou une politique de rétention différente.

2. **JSONL format obligatoire** : Chaque ligne = `{"id": "<clé unique>", "request": {"contents": [...], "generationConfig": {...}}}`. L'`id` sert de clé de lookup dans l'index local (`cv_index` / `scoring_index`).

3. **Poll state machine** : Le job Vertex est asynchrone. Il DOIT être pollé en boucle `while True / await asyncio.sleep(60)` avec vérification de `JOB_STATE_SUCCEEDED / JOB_STATE_FAILED / JOB_STATE_CANCELLED`.

4. **State Redis obligatoire** : Tout pipeline batch DOIT persister son état dans Redis via un `BulkTaskManager` (champs requis : `status`, `batch_job_id`, `dest_uri`, `logs`, `errors`, `start_time`). L'`is_running()` doit inclure tous les statuts intermédiaires : `running | uploading | batch_running | applying`.

5. **IAM Service Account (Terraform)** :
   ```hcl
   # Rôle Vertex AI
   resource "google_project_iam_member" "<service>_vertex_user" {
     role   = "roles/aiplatform.user"
     member = "serviceAccount:${google_service_account.<service>_sa.email}"
   }
   # Rôle GCS
   resource "google_storage_bucket_iam_member" "<service>_batch_storage" {
     bucket = google_storage_bucket.cv_batch.name
     role   = "roles/storage.objectAdmin"
     member = "serviceAccount:${google_service_account.<service>_sa.email}"
   }
   ```

6. **Variables d'environnement requises** (injectées via `cr_<service>.tf`) :
   - `GCP_PROJECT_ID` — ID du projet GCP
   - `VERTEX_LOCATION` — Région Vertex AI (ex: `europe-west1`)
   - `BATCH_GCS_BUCKET` — Nom du bucket GCS (`google_storage_bucket.cv_batch.name`)

7. **Coût** : Le tarif Vertex AI Batch est **-50% vs l'API online**. Privilégier ce mode dès que N > 100 requêtes LLM groupées.

### MCP Natif — Règles spécifiques 🟤

- **Exposition HTTP** : Les services MCP natifs exposent leurs tools via `GET /mcp/tools` (liste) et `POST /mcp/call` (invocation) — pas via sidecar stdio.
- **Pas de BDD propre** : Un MCP natif consomme des APIs externes (BigQuery, Cloud Logging…) via IAM — jamais via une base PostgreSQL interne.
- **JWT obligatoire** : Même règle Zero-Trust que les APIs data — `APIRouter(dependencies=[Depends(verify_jwt)])` sans exception.
- **Pas de fallback JWT en dev** : Il est **STRICTEMENT INTERDIT** de retourner un payload par défaut `{"sub": "dev-user"}` quand `SECRET_KEY` est absente. L'absence de secret doit lever une erreur au démarrage (`raise ValueError(...)`) indépendamment de l'environnement.

---

## 🛡️ 4. SÉCURITÉ ZERO-TRUST (JWT)

Aucune API n'est considérée comme sécurisée par défaut dans le réseau interne.

- **Verrouillage par défaut** : TOUS les endpoints (sauf `/health`, `/metrics`, `/docs`, `/openapi.json`, `/spec`, `/version`) **DOIVENT** être protégés statiquement par le validateur `dependencies=[Depends(verify_jwt)]` sur leur `APIRouter`.
  > **🚨 RÈGLE ANTI-HALLUCINATION IA** : L'Agent (toi) a l'interdiction formelle d'écrire `APIRouter()`. L'instanciation DOIT systématiquement s'écrire avec les dépendances : `APIRouter(dependencies=[Depends(verify_jwt)])`. Si tu écris un router public par inadvertance, c'est une violation critique de cette instruction. Pour garantir ceci, un test global Zero-Trust `test_zero_trust.py` doit exister dans les suites pytest de chaque service pour inspecter statiquement l'arbre des routes FastAPI.
- **Implémentation `verify_jwt`** :
  - Pour les **APIs data** 🔵 : utiliser `from src.auth import verify_jwt` (module partagé).
  - Pour les **agents** 🟣 et **MCP natifs** 🟤 : définir `verify_jwt()` localement dans `main.py`. La fonction DOIT valider la signature HS256, l'expiration ET la présence du claim `sub`.
  ```python
  def verify_jwt(auth: HTTPAuthorizationCredentials = Depends(security)) -> dict:
      try:
          payload = jwt.decode(auth.credentials, SECRET_KEY, algorithms=["HS256"])
          if not payload.get("sub"):
              raise HTTPException(status_code=401, detail="Claim 'sub' manquant")
          return payload
      except JWTError:
          raise HTTPException(status_code=401, detail="Token invalide ou expiré")
  ```
- **INTERDIT — Fallback JWT permissif** : Le pattern suivant est **strictement proscrit** dans tout service, quel que soit l'environnement :
  ```python
  # ❌ DANGEREUX — NE JAMAIS FAIRE
  if not SECRET_KEY:
      return {"sub": "dev-user", "role": "admin"}  # bypass silencieux
  ```
  Si `SECRET_KEY` est absente, le service **DOIT lever une erreur au démarrage**. Pour le dev local, utiliser un fichier `.env` avec une valeur de dev dédiée :
  ```bash
  # .env (dev local — OBLIGATOIREMENT listé dans .gitignore)
  SECRET_KEY=dev-secret-unsafe-do-not-use-in-production
  JWT_EXPIRE_MINUTES=60
  DATABASE_URL=postgresql://user:pass@localhost:5432/dbname
  ```
  > **RÈGLE** : Le fichier `.env` **DOIT impérativement** être présent dans `.gitignore` de chaque service. Un `.env` commité est une faille de sécurité critique équivalente à un secret en clair dans le code source.
- **Propagation de l'Identité (Synchrone)** : Lorsqu'un microservice (ou un appel MCP) contacte un autre microservice, le Header HTTP `Authorization: Bearer <token>` **DOIT** être capturé depuis la requête entrante et transmis explicitement dans la requête sortante.
- **Propagation de l'Identité (Asynchrone & Tâches de Fond)** : Pour toute exécution en arrière-plan (ex: Bulk reanalysis) ou déclenchée par un système ordonnanceur (Cloud Scheduler), le token d'authentification (`auth_token`) ou l'identité du compte de service **DOIT IMPÉRATIVEMENT** être propagé. Cela garantit l'imputation correcte des coûts associés dans le système FinOps.
- **Durée de vie & Refresh** : Les tokens JWT ont une durée de vie courte (configurable via `JWT_EXPIRE_MINUTES`). Pour les tâches longues ou asynchrones, utiliser un token de service dédié (compte de service GCP) plutôt qu'un token utilisateur susceptible d'expirer en mid-flight. Il n'existe **pas** de mécanisme de refresh automatique côté microservice — la responsabilité du renouvellement incombe au client initiateur.
- **🚨 RÈGLE ABSOLUE — INTERDICTION D'UTILISER LE COMPTE ADMIN POUR REFRESHER UN TOKEN** :
  Il est **STRICTEMENT ET ABSOLUMENT INTERDIT** d'utiliser le compte `admin` (ou tout identifiant d'utilisateur humain) pour obtenir, rafraîchir ou relayer un token dans le cadre d'une tâche de fond, d'un batch ou d'un processus automatisé. Cette pratique est une faille de sécurité critique :
  - Elle donne aux tâches automatisées les droits illimités d'un superadmin
  - Elle rend les logs FinOps non-traçables (toutes les actions sont imputées à "admin")
  - Elle contourne le principe de moindre privilège
  
  **La seule approche autorisée pour les background tasks** est d'appeler `POST /auth/internal/service-token` AVANT de lancer la tâche, en transmettant le JWT de l'utilisateur appelant (qui doit avoir le rôle `admin`) afin d'obtenir un token de service à longue durée de vie imputé à l'identité du service :
  ```python
  # ✅ CORRECT — appel avant de lancer la background task
  async with httpx.AsyncClient() as client:
      res = await client.post(
          f"{USERS_API_URL}/auth/internal/service-token",
          headers={"Authorization": auth_header}  # JWT de l'appelant
      )
      service_token = res.json()["access_token"]
  background_tasks.add_task(my_bg_task, service_token)

  # ❌ INTERDIT — ne jamais faire
  service_token = login_as_admin_and_get_token()  # violation absolue
  ```
- **Rotation des secrets** : La clé de signature JWT (`SECRET_KEY`) ne doit jamais être committée. Elle est injectée via Secret Manager GCP. Elle DOIT être purgée de l'environnement processus après lecture (`os.environ.pop("SECRET_KEY", None)`) pour empêcher sa lecture par le LLM.

---

## 📊 5. OBSERVABILITÉ & TRACING

Le monitoring n'est pas une option, c'est l'épine dorsale du debugging asynchrone.

- **Métrique (Prometheus)** :
  - **Règle** : `Instrumentator().instrument(app).expose(app)` est obligatoire dans le `main.py` de **tout** service (API data et agent).
  - **Règle** : `FastAPIInstrumentor.instrument_app(app, excluded_urls="health,metrics")` est **également obligatoire** — sans lui, les routes HTTP ne génèrent pas de spans OTel automatiques.
  - **Raison** : Sans ces deux lignes, le service disparaît des dashboards Grafana et des traces Tempo.
- **Gestion Globale des Erreurs (Golden Pattern)** :
  - **Règle** : Toute API Data **DOIT** implémenter un `@app.exception_handler(Exception)` global pour intercepter les erreurs 500 inattendues. L'erreur doit être relayée silencieusement et de façon asynchrone (via `asyncio.create_task` et `httpx`) vers `prompts_api` (`POST /errors/report`), en propageant le `token` JWT d'origine extrait de la requête.
  - **Raison** : Automatiser la boucle de feedback et l'amélioration continue des System Prompts en redirigeant les échecs vers le moteur d'inférence.
- **Trace (Tempo/OTel)** :
  - **Règle** : *L'oubli de cette règle brise toute la chaîne.* Lors de toute exécution distribuée (ex: Ingestion RAG, import inter-APIs), `inject(headers)` est **STRICTEMENT obligatoire** avant chaque requête HTTP sortante `httpx` pour propager le Span.
  - **Raison** : Sans propagation, les traces sont fragmentées et le debugging distribué devient impossible.
  - **Exemple** : `from opentelemetry.propagate import inject; inject(headers); httpx.post(..., headers=headers)`
  - Le `OTEL_SERVICE_NAME` (dans `TracerProvider`) doit strictement correspondre au `container_name` Docker (ex: `"agent-hr-api"` ↔ `agent_hr_api`).
- **Qualité de la Topologie** : Lors de l'interrogation du traçage (ex: via Google Cloud Trace ou MCP filter), les métriques de bruit comme les `healthchecks` ou `metrics` **DOIVENT ÊTRE FILTRÉES** pour ne conserver que la topologie pertinente de la logique métier.

---

## 💾 6. DATA, CACHE & SEEDING

- **Synchronisation BDD (Liquibase)** 🔵 *(APIs data uniquement — les agents sont stateless et n'ont pas de BDD)* :
  - **Règle** : Toute modification de la structure de données (nouveau champ, nouvelle table) ou ajout de nouvelle API **DOIT impérativement** être accompagnée d'une mise à jour du fichier `changelog.yaml` Liquibase correspondant dans `db_migrations/changelogs/`.
  - **Rollback obligatoire** : Chaque changeset modifiant le schéma (ALTER TABLE, DROP COLUMN, DROP TABLE) **DOIT** inclure une section `rollback` explicite pour permettre un retour en arrière propre en cas de déploiement raté.
  - Le script de réinitialisation (`seed_data.py`) doit être ajusté si des données initiales sont impactées.
- **Cache Redis — Isolation des namespaces** *(critique)* :
  - **Règle** : Chaque service utilisant Redis **DOIT** avoir son propre DB Redis dédié (0-15) ou un préfixe de clé unique. **Une collision de DB entre deux services est un bug à corriger immédiatement** — elle provoque des invalidations de cache erronées et des fuites de données silencieuses.
  - **Matrice de référence** : Documenter l'attribution des DB Redis dans le KI `env-vars-matrix` (colonne `REDIS_URL`). Toute nouvelle attribution doit y être enregistrée.
  - **Invalidation** : Toute modification métier (POST, PUT, DELETE) **DOIT** purger ou invalider le cache Redis associé (ex: suppression des patterns `items:list:*`).
- **Cache Sémantique** 🟣 *(agent_router_api)* :
  - Le cache sémantique Redis (`SemanticCache`) est géré exclusivement par `agent_router_api`. Les sous-agents n'y accèdent pas directement.
  - Toute modification du prompt ou du contexte de session doit considérer l'invalidation du cache sémantique.
- **Sessions** : Injection par dépendance stricte via `Depends(get_db)`.

---

## 🎨 7. UI & FRONTEND STANDARDS

L'apparence de la SPA (Vue.js) doit refléter le branding premium de Zenika.

- **Charte Graphique** : Zenika Red (`#E31937`), Anthracite (`#1A1A1A`), White (`#FFFFFF`).
- **Style** : Privilégier le *Glassmorphism*, les transitions douces, et des composants hautement responsifs (breakpoints : mobile `< 768px`, tablette `768–1024px`, desktop `> 1024px`).
- **Iconographie** : L'utilisation de SVG aléatoires est proscrite. Utiliser exclusivement la librairie `lucide-vue-next`.
- **Accessibilité** : Chaque composant interactif doit disposer d'un attribut `aria-label` explicite. Le ratio de contraste des textes doit respecter le niveau **WCAG 2.1 AA** (4.5:1 minimum).
- **Performance** : Les composants Vue lourds (pages, modales) doivent être chargés en lazy loading (`defineAsyncComponent` / `import()`).
- **UX de l'Agent** : Les dialogues et textes d'interface de l'Agent doivent adopter un ton **professionnel, contextuel et compact**.
- **Persistance et Mode Expert (History)** : Toute l'interface historisant l'usage de l'agent (`/history`) doit scrupuleusement reconstruire les méta-données expertes (étapes d'outils, usage de tokens FinOps, pensées) de façon native (`steps`, `thoughts`, `usage`, `parsedData`).

### Périmètre d'action de l'agent côté frontend

| Fichier / répertoire | L'agent peut modifier ? | Condition |
|---|---|---|
| `src/components/*.vue` | ✅ Oui | Respecter la charte graphique et `lucide-vue-next` |
| `src/views/*.vue` | ✅ Oui | Lazy loading obligatoire (`defineAsyncComponent`) |
| `src/stores/*.ts` (Pinia) | ✅ Oui | Un store par domaine métier, pas de logique HTTP dans le store |
| `src/router/index.ts` | ✅ Oui | Ajouter les guards d'authentification sur toute nouvelle route |
| `vite.config.ts` | ⚠️ Validation user requise | Impact sur le build de prod — ne jamais modifier sans accord explicite |
| `nginx.conf` | ⚠️ Validation user requise | Impact sur le routing prod — ne jamais modifier sans accord explicite |
| `Dockerfile` (frontend) | ⚠️ Validation user requise | Respecte le Container Contract §9 |

- **Gestion des erreurs API (frontend)** : Les erreurs HTTP doivent être interceptées dans les stores Pinia et affichées via le système de notification global (toast). `console.error` seul est insuffisant.
- **Stores Pinia** : Un store = un domaine métier (ex: `useAuthStore`, `useCvStore`). La logique de fetch HTTP appartient au store, pas au composant.

> **🚨 RÈGLE ANTI-HALLUCINATION IA** : Si tu t'apprêtes à modifier `vite.config.ts` ou `nginx.conf`, tu **DOIS immédiatement t'arrêter** et demander la validation explicite du user avant de procéder.

---

## 🧪 8. TESTS & QUALITÉ

Les tests ne sont pas optionnels — ils sont le contrat de non-régression de la plateforme.

- **Tests unitaires** : Toute logique métier non triviale (calcul, transformation, validation) doit être couverte par des tests `pytest` dans un fichier `test_*.py` au niveau du service.
- **Tests de contrats MCP** 🔵 *(APIs data uniquement)* : Les tools exposés dans `mcp_server.py` doivent disposer d'un test d'invocation de base dans `test_mcp_tools.py` (appel du tool avec des paramètres valides, vérification de la structure de retour).
- **Tests d'agents** 🟣 : Les agents doivent disposer de tests couvrant :
  - `test_session.py` — Cycle de vie d'une session ADK
  - `test_guardrail.py` — Comportement des guardrails (réponses hors périmètre)
  - `test_jwt_propagation.py` — Propagation correcte du token JWT entre agents
  - `test_mcp.py` — Appels MCP sortants mockés (vérification que le client MCP est correctement initialisé et que le JWT est propagé)
- **Tests d'intégration** : Les endpoints critiques (auth, mutations de données) doivent être couverts par des tests d'intégration utilisant un client HTTP de test (ex: `httpx.AsyncClient` avec `app` FastAPI).
- **CI Gate** : La pipeline CI doit bloquer un merge si les tests échouent. La couverture minimale est à définir par équipe, mais ne doit pas régresser entre deux PRs.

---

## 🐳 9. DOCKER & CLOUD RUN STANDARDS (CONTAINER CONTRACT)

Tous les conteneurs du projet doivent impérativement respecter les règles dictées par le *Container Contract* de Cloud Run et les standards d'optimisations :

1. **Zéro-Trust Non-Root** : L'exécution de processus en tant que `root` (UID 0) est interdite. Les conteneurs Python doivent créer et switcher sur un `USER appuser`. Le front-end doit utiliser une image `nginx-unprivileged` sur le port `8080`.
2. **Multi-Stage Builds** : Chaque Dockerfile se doit d'utiliser des étapes de build (`AS builder`) pour séparer les outils de compilation (ex: `gcc`) du binaire final en prod. Cela renforce la sécurité et réduit l'empreinte de l'image.
3. **Graceful Shutdown (CMD System)** : Interdiction d'utiliser des appels shell comme `CMD ["sh", "-c", "..."]`. Favorisez l'appel de module cible : `CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]` pour pallier l'absence potentielle de shell liés aux packages `distroless` ou les wrappers pip. **Utiliser `python3`, jamais `python`.**
   - **Cette règle s'applique également aux fichiers Terraform `cr_*.tf`** : `command = ["python3"]` et non `command = ["python"]` dans les définitions `containers {}` de Cloud Run.
4. **Hygiène du Cache (.dockerignore)** : Les directives `COPY . .` doivent être sécurisées par des fichiers `.dockerignore` stricts (interdisant l'inclusion de `__pycache__`, environnements virtuels ou données de tests) pour maximiser la vitesse de Build.
5. **Dockerfile comme Contrat de Configuration (ENV Contract)** : Le `Dockerfile` est la **source de vérité exhaustive** des variables d'environnement qu'un service consomme. Les règles sont :
   - Toute variable lue via `os.getenv()` dans le code **DOIT** avoir un `ENV nom=valeur_locale` correspondant dans le Dockerfile (avec une valeur de dev local safe).
   - Une variable présente dans le code mais **absente du Dockerfile est un bug** à corriger immédiatement.
   - **3 niveaux d'env vars** selon leur origine :
     - *Comportement applicatif* (`LOG_LEVEL`, `TRACE_EXPORTER`, `ROOT_PATH`, URLs locales) → défaut dans Dockerfile, optionnellement surchargé par Cloud Run.
     - *Infrastructure* (`DATABASE_URL`, `REDIS_URL`, `ALLOYDB_INSTANCE_URI`) → **jamais de défaut dans Dockerfile**, toujours injecté par Cloud Run TF.
     - *Secrets* (`GOOGLE_API_KEY`, `SECRET_KEY`) → **jamais dans Dockerfile**, toujours via `secret_key_ref` dans Cloud Run TF + binding IAM `secretAccessor`.
   - Le fichier `cr_<service>.tf` Terraform doit surcharger toutes les valeurs infra/secrets. Les env vars présentes dans le Dockerfile **sans override TF** utilisent leur valeur de dev par défaut — ce comportement est intentionnel et accepté pour les variables comportementales.
   - **Consulter le KI `env-vars-matrix`** pour la matrice de référence complète (service → variables → secrets requis).

---

## 🚀 10. DÉPLOIEMENT, VERSIONING & TERRAFORM

1. **Semantic Versioning — Ownership exclusif de `deploy.sh`** : Chaque microservice possède un fichier `VERSION` (semver) à sa racine. Ce fichier et les entrées `*_version` des fichiers `platform-engineering/envs/*.yaml` sont **la propriété exclusive de `deploy.sh`**.
   - **L'agent Antigravity (LLM) n'a JAMAIS le droit de modifier un fichier `VERSION` ni un champ `*_version` dans les `envs/*.yaml`**, quelle que soit la raison, y compris après une modification de code source.
   - **`agent_commons` doit impérativement avoir un fichier `VERSION`** — c'est une bibliothèque partagée critique dont toute modification impacte les 4 agents. Son version doit être gérée indépendamment et référencée dans les `requirements.txt` des agents (ex: `agent-commons>=1.2.0`).
   - Le cycle complet est : **code modifié** (par l'agent) → **`deploy.sh` détecte les changements** → **bump de version automatique** → **build & push**. L'agent intervient uniquement sur la première étape.
2. **Injection Environnementale** : La variable d'environnement `APP_VERSION` doit toujours être synchronisée et injectée sur les conteneurs Cloud Run pour une parfaite observabilité (notamment via un endpoint `/version`).
3. **Idempotence des Déploiements** : Un script de déploiement (ex: `manage_env.py`) doit pouvoir être exécuté de façon répétée sans causer d'erreur HTTP asynchrone ; des invalidations de CDN ou d'imports non conditionnés doivent être évités s'ils génèrent des erreurs `409 Conflict`.
4. **Cycle de vie Cloud Run (Terraform)** : La balise `deletion_protection = false` n'est plus supportée sur les ressources `google_cloud_run_v2_service` et se doit d'être retirée des manifests HCL.
5. **Persistance des Ressources Externes** : Le compte de service Drive (`sa-drive-*-v2`) **NE DOIT PAS** être supprimé en cas de destruction de l'environnement (Terraform Destroy), car cela forcerait la réaffectation manuelle et chronophage des droits d'accès au niveau des partages Google Drive.
6. **Gestion du State Terraform** :
   - Le backend Terraform doit pointer sur un bucket GCS dédié avec versioning activé et state locking (via le backend `gcs`).
   - Les fichiers `terraform.tfvars` contenant des valeurs sensibles **DOIVENT** être listés dans `.gitignore` et ne jamais être committés.
   - Un `terraform plan` **DOIT** être exécuté et relu avant tout `terraform apply` en environnement non-dev.

---

## 🧠 11. MÉMOIRE PERSISTANTE ANTIGRAVITY (OBLIGATOIRE)

> **RÈGLE ABSOLUE** : Ces workflows s'exécutent automatiquement, sans attendre que le user le demande.

### Ordre de priorité des mécanismes — TOUJOURS respecter cet ordre

| Priorité | Mécanisme | Quand l'utiliser |
|---|---|---|
| **1️⃣ MCP natif** | Outils `mcp_antigravity-memory_*` | **Toujours en premier** — disponibles nativement dans le contexte agent, sans dépendance réseau |
| **2️⃣ CLI** | `antigravity_cli.py` | Si le contexte n'expose pas les tools MCP (shell interactif) |
| **3️⃣ HTTP direct** | `curl http://localhost:8000/api/...` | Fallback si CLI échoue (`"Operation not permitted"`) |

```bash
# Méthode 2 : CLI (si pas de contexte MCP)
CLI="python3 /Users/sebastien.lavayssiere/Code/mcp-local/antigravity-memory/scripts/antigravity_cli.py"

# Méthode 3 : API HTTP directe (fallback ultime)
# POST /api/errors  |  POST /api/learnings  |  GET /api/search?q=...
```

### Référentiel des tools MCP disponibles

| Tool MCP | Action | Équivalent CLI |
|---|---|---|
| `mcp_antigravity-memory_search_past_errors` | Recherche dans les erreurs passées | `$CLI search-error "<mots-clés>"` |
| `mcp_antigravity-memory_search_learnings` | Recherche sémantique dans les connaissances | `$CLI search-learning "<concept>"` |
| `mcp_antigravity-memory_log_error_and_solution` | Enregistre une erreur résolue | `POST /api/errors` |
| `mcp_antigravity-memory_log_learning` | Enregistre un savoir réutilisable | `POST /api/learnings` |
| `mcp_antigravity-memory_update_error_entry` | Corrige/met à jour une entrée d'erreur | `PUT /api/errors/{id}` |
| `mcp_antigravity-memory_trace_root_cause` | Remonte la chaîne causale d'une erreur | — |
| `mcp_antigravity-memory_get_rules_prompt` | Récupère les Golden Rules prioritaires | — |
| `mcp_antigravity-memory_request_new_mcp_tool` | Propose un outil MCP manquant au backlog | `$CLI suggest-tool` |
| `mcp_antigravity-memory_search_tool_backlog` | Vérifie si un outil est déjà en backlog | — |

---

### 🔴 WORKFLOW A — FACE À UNE ERREUR (avant tout fix)

**Déclenché par :** un log d'erreur, un stack trace, un comportement inattendu.

> 🚨 **RÈGLE BLOQUANTE (DoD)** : Si tu as modifié du code suite à une exception, une erreur HTTP, un crash ou un comportement inattendu, ton **dernier appel d'outil** de la session DOIT impérativement être `mcp_antigravity-memory_log_error_and_solution`. Il est INTERDIT d'annoncer "C'est corrigé" sans avoir enregistré l'erreur en mémoire.

**Étape 1 — Chercher en mémoire AVANT de coder :**
```
# Priorité 1 — MCP natif (TOUJOURS en premier)
→ mcp_antigravity-memory_search_past_errors(query="<technologie ou mots-clés de l'erreur>")

# Priorité 2 — CLI
$CLI search-error "<technologie ou mots-clés de l'erreur>"

# Priorité 3 — HTTP fallback
curl -s "http://localhost:8000/api/search?q=<mots-cles>&type=error" | python3 -m json.tool
```
- Résultat trouvé → appliquer la solution mémorisée directement
- Aucun résultat → analyser manuellement, puis logger après fix

**Étape 2 — Logger immédiatement après résolution (pas à la fin de session) :**
```
# Priorité 1 — MCP natif
→ mcp_antigravity-memory_log_error_and_solution(
    task_context="<service, fonction, action>",
    error_message="<message d'erreur exact copié depuis les logs>",
    successful_solution="<fix précis : fichier, ligne, changement>",
    tags=["<tech>", "<service>"]
  )

# Priorité 3 — HTTP fallback
curl -s -X POST http://localhost:8000/api/errors \
  -H "Content-Type: application/json" \
  -d '{
    "task_context": "<service, fonction, action>",
    "error_message": "<message d erreur exact copié depuis les logs>",
    "successful_solution": "<fix précis : fichier, ligne, changement>",
    "tags": ["<tech>", "<service>"]
  }' | python3 -m json.tool
```

---

### 🔴 WORKFLOW B — AVANT TOUTE IMPLÉMENTATION COMPLEXE (pré-vol)

**Déclenché si :** modifier ≥2 fichiers, migration DB, configuration service, changement architectural.
```
# Priorité 1 — MCP natif
→ mcp_antigravity-memory_search_past_errors(query="<technologie concernée>")
→ mcp_antigravity-memory_search_learnings(query="<pattern ou concept>")

# Priorité 2 — CLI
$CLI search-error "<technologie concernée>"
$CLI search-learning "<pattern ou concept>"
```
- Si résultat → lire et appliquer avant d'écrire du code

---

### 🟠 WORKFLOW C — DÈS QU'UN SAVOIR RÉUTILISABLE EST ACQUIS

**Le déclencheur est la DÉCOUVERTE, pas la fin de la tâche.**
Exemples : dépendance manquante, ENV Contract violé, bug architectural, convention implicite du projet.

```
# Priorité 1 — MCP natif
→ mcp_antigravity-memory_log_learning(
    topic="<titre concis — ce que quelqu'un chercherait dans 3 mois>",
    content="<explication complète et autonome avec exemple de code>",
    source_context="<source : fichier, ligne, service, erreur>",
    tags=["<tech>"]
  )

# Priorité 3 — HTTP fallback
curl -s -X POST http://localhost:8000/api/learnings \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "<titre concis>",
    "content": "<explication complete et autonome avec exemple de code>",
    "context": "<source : fichier, ligne, service, erreur>",
    "tags": ["<tech>"]
  }' | python3 -m json.tool
```

**Test de qualité :** Le `content` doit permettre d'appliquer le savoir sans accès au contexte original.

---

### 🟡 WORKFLOW D — OUTIL MANQUANT DÉTECTÉ

```
# Priorité 1 — MCP natif
→ mcp_antigravity-memory_search_tool_backlog(query="<nom ou concept>")  # vérifier si déjà demandé
→ mcp_antigravity-memory_request_new_mcp_tool(
    tool_name="<nom>",
    description="<description technique>",
    use_case="<contexte d'usage>"
  )

# Priorité 2 — CLI
$CLI suggest-tool "<nom>" "<description>" "<use_case>"
```

---

### ❌ ANTI-PATTERNS INTERDITS

| Comportement interdit | Comportement attendu |
|---|---|
| Utiliser la CLI ou curl SANS d'abord essayer le tool MCP | MCP natif en priorité 1 — toujours |
| Fixer un bug sans `search_past_errors` d'abord | `mcp_antigravity-memory_search_past_errors` systématique avant tout debug |
| Logger les apprentissages "à la fin" de la session | Logger **au moment de la découverte** |
| Sauter le log parce que le user ne l'a pas demandé | Le log est automatique, jamais optionnel |
| Logger un `content` vague ou dépendant du contexte | Le `content` doit être **autonome** (lisible sans accès au code original) |
| Logger un message vague | Logger le message d'erreur **exact** + fichier + ligne |
| Clôturer un ticket de bug sans mémoriser | **`mcp_antigravity-memory_log_error_and_solution` est le pré-requis pour clore un bug** |

---


## ⚠️ 12. DISCIPLINE DE SESSION ANTIGRAVITY

Pour éviter la fragmentation de la mémoire et la perte de contexte, l'agent doit imposer la rigueur suivante dans ses interactions :

- **Session longue par thème** : Une conversation Antigravity doit couvrir 1 thème cohérent (ex: "Observabilité", "MCP alignment", "Frontend UX") — pas 1 seul petit ticket Jira isolé.
- **task.md obligatoire** : Pour toute session impliquant ≥3 fichiers ou ≥2 services, l'agent DOIT créer un `task.md` actif dans l'artifact directory et le tenir à jour de manière proactive.
- **Handoff explicite** : Si une session devient trop longue et doit s'arrêter, l'agent DOIT générer un artefact `walkthrough.md` résumant l'état exact et les prochaines étapes pour permettre la reprise immédiate sans perte de contexte dans la session suivante.

---

## 📖 13. README.md PAR SERVICE (CONTRAT OBLIGATOIRE)

Chaque service, agent et bibliothèque partagée possède un fichier `README.md` à sa racine. Ce fichier est le **contrat de connaissance** du service — il évite à l'agent de re-scanner des centaines de lignes de code à chaque intervention.

### Services couverts
`users_api` · `items_api` · `competencies_api` · `cv_api` · `missions_api` · `drive_api` · `prompts_api` · `analytics_mcp` · `monitoring_mcp` · `agent_router_api` · `agent_hr_api` · `agent_ops_api` · `agent_missions_api` · `agent_commons` · `frontend`

### Règles obligatoires

1. **Lecture avant intervention** : Avant toute analyse ou modification d'un service, l'agent DOIT lire son `README.md`. Si le fichier est absent → signaler au user et le créer avant de continuer.

2. **Mise à jour après modification** : Après toute modification de code, l'agent DOIT mettre à jour les sections impactées du `README.md` du service concerné :
   - Section **Fichiers clés** : mettre à jour les compteurs de lignes si significatifs
   - Section **Dernière modification** : `YYYY-MM-DD — vX.X.X — résumé en 1 ligne`
   - Section **Gotchas connus** : ajouter tout nouveau comportement surprenant découvert

3. **Un README stale > 5 sessions** est considéré invalide → re-scanner le code et mettre le README à jour.

### Format standard du README

```markdown
# <service_name>

## Rôle
[1 phrase]

## Type
🔵 API data | 🟣 Agent | 🟤 MCP natif | 📦 Bibliothèque | 🎨 Frontend

## Fichiers clés
| Fichier | Lignes | État |
|---|---|---|
| `src/router.py` | XXX | ✅ OK / ⚠️ Zone alerte / 🚨 Zone bloquante |

## Variables d'environnement
| Var | Type | Valeur dev |

## Redis
DB n° — namespace `prefix:*`

## Endpoints clés / MCP tools exposés

## Gotchas connus
- [comportements non-évidents]

## Dernière modification
YYYY-MM-DD — vX.X.X — résumé du changement
```

> **🚨 RÈGLE ANTI-HALLUCINATION IA** : Si tu t'apprêtes à modifier un service sans avoir lu son `README.md`, tu **DOIS d'abord lire le fichier** `<service>/README.md`. Ne jamais supposer l'état d'un service depuis une session précédente sans vérifier le README.

## 📏 14. QUALITÉ DU CODE — TAILLE DES FICHIERS (RÈGLE OBLIGATOIRE)

La longueur des fichiers Python est un indicateur critique de couplage et de violation du **Single Responsibility Principle (SRP)**. Les fichiers longs produits de façon incrémentale par l'agent sont un **anti-pattern nommé "God Router"** : un seul fichier concentre transport HTTP, logique métier, accès BDD et intégrations externes.

### Seuils obligatoires

| Type de fichier | Seuil d'alerte | Seuil bloquant |
|---|---|---|
| `router.py` | > 300 lignes | > 400 lignes |
| `main.py` (agent) | > 400 lignes | > 600 lignes |
| `mcp_server.py` | > 400 lignes | > 600 lignes |
| Toute fonction / méthode | > 60 lignes | > 80 lignes |
| Tout autre fichier | > 400 lignes | > 600 lignes |

### Règles strictes

1. **Avant d'ajouter une feature dans un fichier existant**, l'agent DOIT vérifier le nombre de lignes :
   - Si le fichier est en **zone d'alerte** (> 300L pour un router) → proposer un découpage avant d'implémenter.
   - Si le fichier est en **zone bloquante** → **REFUS D'AJOUTER** sans refactoring préalable.

2. **Pattern Service Layer obligatoire pour les routers** : Tout `router.py` dépassant 400 lignes DOIT être accompagné d'un dossier `services/` contenant des modules thématiques :
   ```
   src/
   ├── router.py          # Transport HTTP uniquement (< 400L)
   └── services/
       ├── import_service.py      # Logique d'import
       ├── search_service.py      # Logique de recherche
       └── analytics_service.py  # Logique analytique
   ```

3. **Toute fonction > 80 lignes** DOIT être décomposée. Les fonctions privées (`_bg_*`, `_run_*`) qui orchestrent des pipelines complets doivent être extraites dans le service layer.

4. **Règle ANTI-HALLUCINATION** : Si tu t'apprêtes à ajouter du code dans un fichier `router.py` et que ce fichier fait déjà > 400 lignes, tu **DOIS immédiatement t'arrêter** et retourner le message : *"Ce router.py fait déjà X lignes (> 400). Je dois d'abord extraire la logique existante dans un service layer avant d'ajouter la nouvelle feature. Voici mon plan de refactoring..."*

### Architecture cible (Service Layer Pattern)

```
# ❌ God Router (anti-pattern observé)
router.py   → 5000 lignes, 8 domaines fonctionnels, 5 fonctions > 100L

# ✅ Service Layer (pattern correct)
router.py              → ~300L  (HTTP in/out + délégation)
services/
  ├── cv_import.py     → ~300L  (pipeline d'import)
  ├── search.py        → ~200L  (recherche vectorielle)
  ├── taxonomy.py      → ~400L  (orchestration LLM)
  ├── bulk.py          → ~400L  (batch Vertex AI)
  └── analytics.py     → ~200L  (KPIs et data quality)
```

> **Contexte** : Ce pattern a été violé dans `cv_api/src/cvs/router.py` (5 039 lignes) et `competencies_api/src/competencies/router.py` (2 461 lignes) suite à des accumulations incrémentales sans refactoring. Ces fichiers sont en cours de remédiation (session 2026-04-29).
