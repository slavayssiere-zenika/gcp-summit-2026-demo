# 📜 Projet Zenika Console Agent - Golden Rules

Ce document dicte le comportement, les standards et les contraintes non négociables pour l'Agent Antigravity et les développeurs. **Le non-respect de ces règles cassera la plateforme.**

---

## ✅ CHECKLIST DE CONFORMITÉ (Nouvelles fonctionnalités)

Avant tout PR / déploiement, vérifiez chaque point :

- [ ] Endpoint protégé par `dependencies=[Depends(verify_jwt)]` sur son `APIRouter` ?
- [ ] Tool MCP créé ou mis à jour dans `mcp_server.py` ?
- [ ] `inject(headers)` présent dans **chaque** appel `httpx` sortant ?
- [ ] Changeset Liquibase ajouté dans `db_migrations/changelogs/` (avec section `rollback`) ?
- [ ] Cache Redis invalidé sur les mutations (POST, PUT, DELETE) ?
- [ ] `Instrumentator().instrument(app).expose(app)` dans `main.py` ?
- [ ] Fichier `VERSION` mis à jour (semver) ?
- [ ] Tests unitaires / contrats MCP ajoutés ou mis à jour ?
- [ ] Aucun modèle IA hardcodé (utiliser les variables d'environnement) ?

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

---

## 🏗️ 2. ARCHITECTURE & STACK

L'environnement est strictement micro-serviciel et repose sur **Docker Compose** (dev local) et **Cloud Run** (GCP).

- **Microservices natifs** : `users_api`, `items_api`, `competencies_api`, `cv_api`, `missions_api` (gestion multimodale de documents).
- **Orchestrateur Multi-Agent (A2A)** :
  - `agent_router_api` : routeur intelligent, délègue aux sous-agents via le protocole A2A (FastAPI + Google ADK + Gemini).
  - `agent_hr_api` : sous-agent spécialisé RH (compétences, CVs, utilisateurs).
  - `agent_ops_api` : sous-agent spécialisé Ops (missions, items, opérationnel).
  - Les sous-agents communiquent via HTTP (A2A) et **non** via SSE pour rester stateless.
- **Frontend** : `frontend` (Vue.js + proxy Nginx pointant `/api/` vers `agent_router_api`).
- **Data Layer** : PostgreSQL (namespaces partagés), Redis (Cache/Queue, incluant un Cache Sémantique pour bypasser les appels LLM redondants).
- **FinOps & Data Analytics** : L'utilisation de l'IA est trackée et centralisée dans Google BigQuery (table `ai_usage` partitionnée par jour) pour l'optimisation des coûts.
- **Réseau interne** : `monitoring_net` est obligatoire pour la résolution DNS.

---

## 🤖 3. MCP & AGENT ORCHESTRATION

L'Agent intelligent dialogue avec l'écosystème via le protocole MCP (Model Context Protocol).

- **Serveurs MCP Autonomes** : Chaque sous-service possède son propre serveur MCP (incluant des services externes type `market_mcp`). **ATTENTION** : La directive architecturale principale est de privilégier les flux **HTTP standards (REST)** dès que possible au détriment du protocole SSE (Server-Sent Events) pour des raisons de scalabilité et de simplicité (stateless).
- **Règle de Fonctionnalité** :
  - **Règle** : Toute nouvelle route / logique métier implémentée dans une API **DOIT IMPÉRATIVEMENT** faire l'objet d'un outil (`Tool`) exposé dans le `mcp_server.py` de cette même API.
  - **Convention de nommage** : Les tools MCP utilisent le format `snake_case` VERBE_RESSOURCE (ex: `get_user_by_id`, `create_competency`, `list_missions`).
  - **Gestion d'erreur** : Un tool ne doit **jamais** laisser propager une exception non catchée. Il retourne systématiquement un dictionnaire structuré : `{"success": false, "error": "message lisible"}` en cas d'échec, sans lever de `ToolException` non gérée.
- **Enregistrement ADK (`agent.py`)** : Les outils distants doivent être mappés en tant que fonctions ou instances natives dans le fichier `agent.py` de chaque agent avec des **Docstrings riches** (cruciales pour que le LLM sache quand les appeler). Attention à correctement scoper et initialiser les instances de clients MCP pour éviter les fuites de variable.

---

## 🛡️ 4. SÉCURITÉ ZERO-TRUST (JWT)

Aucune API n'est considérée comme sécurisée par défaut dans le réseau interne.

- **Verrouillage par défaut** : TOUS les endpoints (sauf `/health`, `/metrics`, `/docs`) **DOIVENT** être protégés statiquement par le validateur `dependencies=[Depends(verify_jwt)]` sur leur `APIRouter`.
- **Propagation de l'Identité (Synchrone)** : Lorsqu'un microservice (ou un appel MCP) contacte un autre microservice, le Header HTTP `Authorization: Bearer <token>` **DOIT** être capturé depuis la requête entrante et transmis explicitement dans la requête sortante.
- **Propagation de l'Identité (Asynchrone & Tâches de Fond)** : Pour toute exécution en arrière-plan (ex: Bulk reanalysis) ou déclenchée par un système ordonnanceur (Cloud Scheduler), le token d'authentification (`auth_token`) ou l'identité du compte de service **DOIT IMPÉRATIVEMENT** être propagé. Cela garantit l'imputation correcte des coûts associés dans le système FinOps.
- **Durée de vie & Refresh** : Les tokens JWT ont une durée de vie courte (configurable via `JWT_EXPIRE_MINUTES`). Pour les tâches longues ou asynchrones, utiliser un token de service dédié (compte de service GCP) plutôt qu'un token utilisateur susceptible d'expirer en mid-flight. Il n'existe **pas** de mécanisme de refresh automatique côté microservice — la responsabilité du renouvellement incombe au client initiateur.
- **Rotation des secrets** : La clé de signature JWT (`JWT_SECRET_KEY`) ne doit jamais être committée. Elle est injectée via Secret Manager GCP.

---

## 📊 5. OBSERVABILITÉ & TRACING

Le monitoring n'est pas une option, c'est l'épine dorsale du debugging asynchrone.

- **Métrique (Prometheus)** :
  - **Règle** : `Instrumentator().instrument(app).expose(app)` est obligatoire dans le `main.py` de toute nouvelle API.
  - **Raison** : Sans cette ligne, le service disparaît des dashboards Grafana et des alertes.
- **Trace (Tempo/OTel)** :
  - **Règle** : *L'oubli de cette règle brise toute la chaîne.* Lors de toute exécution distribuée (ex: Ingestion RAG, import inter-APIs), `inject(headers)` est **STRICTEMENT obligatoire** avant chaque requête HTTP sortante `httpx` pour propager le Span.
  - **Raison** : Sans propagation, les traces sont fragmentées et le debugging distribué devient impossible.
  - **Exemple** : `from opentelemetry.propagate import inject; inject(headers); httpx.post(..., headers=headers)`
  - Le `OTEL_SERVICE_NAME` doit strictement correspondre au `container_name` Docker.
- **Qualité de la Topologie** : Lors de l'interrogation du traçage (ex: via Google Cloud Trace ou MCP filter), les métriques de bruit comme les `healthchecks` ou `metrics` **DOIVENT ÊTRE FILTRÉES** pour ne conserver que la topologie pertinente de la logique métier. Le formatage des requêtes doit scrupuleusement suivre l'API Google Cloud Trace.

---

## 💾 6. DATA, CACHE & SEEDING

- **Synchronisation BDD (Liquibase)** :
  - **Règle** : Toute modification de la structure de données (nouveau champ, nouvelle table) ou ajout de nouvelle API **DOIT impérativement** être accompagnée d'une mise à jour du fichier `changelog.yaml` Liquibase correspondant dans `db_migrations/changelogs/`.
  - **Rollback obligatoire** : Chaque changeset modifiant le schéma (ALTER TABLE, DROP COLUMN, DROP TABLE) **DOIT** inclure une section `rollback` explicite pour permettre un retour en arrière propre en cas de déploiement raté.
  - Le script de réinitialisation (`seed_data.py`) doit être ajusté si des données initiales sont impactées.
- **Cache Redis** :
  - **Règle** : Toute modification métier (POST, PUT, DELETE) **DOIT** purger ou invalider le cache Redis associé (ex: suppression des patterns `items:list:*`).
  - **Raison** : Un cache périmé génère des incohérences silencieuses difficiles à diagnostiquer.
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

---

## 🧪 8. TESTS & QUALITÉ

Les tests ne sont pas optionnels — ils sont le contrat de non-régression de la plateforme.

- **Tests unitaires** : Toute logique métier non triviale (calcul, transformation, validation) doit être couverte par des tests `pytest` dans un fichier `test_*.py` au niveau du service.
- **Tests de contrats MCP** : Les tools exposés dans `mcp_server.py` doivent disposer d'un test d'invocation de base dans `test_mcp_tools.py` (appel du tool avec des paramètres valides, vérification de la structure de retour).
- **Tests d'intégration** : Les endpoints critiques (auth, mutations de données) doivent être couverts par des tests d'intégration utilisant un client HTTP de test (ex: `httpx.AsyncClient` avec `app` FastAPI).
- **CI Gate** : La pipeline CI doit bloquer un merge si les tests échouent. La couverture minimale est à définir par équipe, mais ne doit pas régresser entre deux PRs.

---

## 🐳 9. DOCKER & CLOUD RUN STANDARDS (CONTAINER CONTRACT)

Tous les conteneurs du projet doivent impérativement respecter les règles dictées par le *Container Contract* de Cloud Run et les standards d'optimisations :

1. **Zéro-Trust Non-Root** : L'exécution de processus en tant que `root` (UID 0) est interdite. Les conteneurs Python doivent créer et switcher sur un `USER appuser`. Le front-end doit utiliser une image `nginx-unprivileged` sur le port `8080`.
2. **Multi-Stage Builds** : Chaque Dockerfile se doit d'utiliser des étapes de build (`AS builder`) pour séparer les outils de compilation (ex: `gcc`) du binaire final en prod. Cela renforce la sécurité et réduit l'empreinte de l'image.
3. **Graceful Shutdown (CMD System)** : Interdiction d'utiliser des appels shell comme `CMD ["sh", "-c", "..."]`. Favorisez l'appel de module cible : `CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]` pour palier l'absence potentielle de shell liés aux packages `distroless` ou les wrappers pip.
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

1. **Semantic Versioning** : Chaque microservice évolue indépendamment. **DOIT** posséder un fichier `VERSION` (Patch/Minor/Major) à sa racine. Cette version est lue pour le cycle de déploiement et est injectée dynamiquement.
2. **Injection Environnementale** : La variable d'environnement `APP_VERSION` doit toujours être synchronisée et injectée sur les conteneurs Cloud Run pour une parfaite observabilité (notamment via un endpoint `/version`).
3. **Idempotence des Déploiements** : Un script de déploiement (ex: `manage_env.py`) doit pouvoir être exécuté de façon répétée sans causer d'erreur HTTP asynchrone ; des invalidations de CDN ou d'imports non conditionnés doivent être évités s'ils génèrent des erreurs `409 Conflict`.
4. **Cycle de vie Cloud Run (Terraform)** : La balise `deletion_protection = false` n'est plus supportée sur les ressources `google_cloud_run_v2_service` et se doit d'être retirée des manifests HCL.
5. **Persistance des Ressources Externes** : Le compte de service Drive (`sa-drive-*-v2`) **NE DOIT PAS** être supprimé en cas de destruction de l'environnement (Terraform Destroy), car cela forcerait la réaffectation manuelle et chronophage des droits d'accès au niveau des partages Google Drive.
6. **Gestion du State Terraform** :
   - Le backend Terraform doit pointer sur un bucket GCS dédié avec versioning activé et state locking (via le backend `gcs`).
   - Les fichiers `terraform.tfvars` contenant des valeurs sensibles **DOIVENT** être listés dans `.gitignore` et ne jamais être committés.
   - Un `terraform plan` **DOIT** être exécuté et relu avant tout `terraform apply` en environnement non-dev.
