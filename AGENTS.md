# 📜 Projet Zenika Console Agent - Golden Rules

Ce document dicte le comportement, les standards et les contraintes non négociables pour l'Agent Antigravity et les développeurs. **Le non-respect de ces règles cassera la plateforme.**

---

## 🏗️ 1. ARCHITECTURE & STACK
L'environnement est strictement micro-serviciel et repose sur **Docker Compose**.
- **Microservices natifs** : `users_api`, `items_api`, `competencies_api`, `cv_api`, `missions_api` (gestion multimodale de documents).
- **Orchestrateur** : `agent_api` (FastAPI + Google ADK + Gemini).
- **Frontend** : `frontend` (Vue.js + proxy Nginx pointant `/api/` vers `agent_api`).
- **Data Layer** : PostgreSQL (namespaces partagés), Redis (Cache/Queue, incluant un Cache Sémantique pour bypasser les appels LLM redondants).
- **FinOps & Data Analytics** : L'utilisation de l'IA est trackée et centralisée dans Google BigQuery (table `ai_usage` partitionnée par jour) pour l'optimisation des coûts.
- **Réseau interne** : `monitoring_net` est obligatoire pour la résolution DNS.

---

## 🤖 2. MCP & AGENT ORCHESTRATION
L'Agent intelligent dialogue avec l'écosystème via le protocole MCP (Model Context Protocol).
- **Serveurs MCP Autonomes** : Chaque sous-service possède son propre serveur MCP (incluant des services externes type `market_mcp`). **ATTENTION** : La directive architecturale principale est de privilégier les flux **HTTP standards (REST)** dès que possible au détriment du protocole SSE (Server-Sent Events) pour des raisons de scalabilité et de simplicité (stateless).
- **Règle de Fonctionnalité** : Toute nouvelle route / logique métier implémentée dans une API **DOIT IMPÉRATIVEMENT** faire l'objet d'un outil (`Tool`) exposé dans le `mcp_server.py` de cette même API.
- **Enregistrement ADK (`agent.py`)** : Les outils distants doivent être mappés en tant que fonctions ou instances natives dans `agent_api/agent.py` avec des **Docstrings riches** (cruciales pour que le LLM sache quand les appeler). Attention à correctement scoper et initialiser les instances de clients MCP pour éviter les fuites de variable.

---

## 🛡️ 3. SÉCURITÉ ZERO-TRUST (JWT)
Aucune API n'est considérée comme sécurisée par défaut dans le réseau interne.
- **Verrouillage par défaut** : TOUS les endpoints (sauf `/health`, `/metrics`, `/docs`) **DOIVENT** être protégés statiquement par le validateur `dependencies=[Depends(verify_jwt)]` sur leur `APIRouter`.
- **Propagation de l'Identité (Synchrone)** : Lorsqu'un microservice (ou un appel MCP) contacte un autre microservice, le Header HTTP `Authorization: Bearer <token>` **DOIT** être capturé depuis la requête entrante et transmis explicitement dans la requête sortante.
- **Propagation de l'Identité (Asynchrone & Tâches de Fond)** : Pour toute exécution en arrière-plan (ex: Bulk reanalysis) ou déclenchée par un système ordonnanceur (Cloud Scheduler), le token d'authentification (`auth_token`) ou l'identité du compte de service **DOIT IMPÉRATIVEMENT** être propagé. Cela garantit l'imputation correcte des coûts associés dans le système FinOps.

---

## 📊 4. OBSERVABILITÉ & TRACING
Le monitoring n'est pas une option, c'est l'épine dorsale du debugging asynchrone.
- **Métrique (Prometheus)** : `Instrumentator().instrument(app).expose(app)` est obligatoire dans le `main.py` de toute nouvelle API.
- **Trace (Tempo/OTel)** : *L'oubli de cette règle brise toute la chaîne.* Lors de toute exécution distribuée (ex: Ingestion RAG, import inter-APIs), `inject(headers)` est STRICTEMENT obligatoire avant chaque requête HTTP sortante `httpx` pour propager le Span. Le `OTEL_SERVICE_NAME` doit strictement correspondre au `container_name` Docker.
- **Qualité de la Topologie** : Lors de l'interrogation du traçage (ex: via Google Cloud Trace ou MCP filter), les métriques de bruit comme les `healthchecks` ou `metrics` **DOIVENT ÊTRE FILTRÉES** pour ne conserver que la topologie pertinente de la logique métier. Le formatage des requêtes doit scrupuleusement suivre l'API Google Cloud Trace.

---

## 💾 5. DATA, CACHE & SEEDING
- **Synchronisation BDD (Liquibase)** : Toute modification de la structure de données (nouveau champ, nouvelle table) ou ajout de nouvelle API **DOIT impérativement** être accompagnée d'une mise à jour du fichier `changelog.yaml` Liquibase correspondant dans `db_migrations/changelogs/`. Puis, le script de réinitialisation (`seed_data.py`) doit être ajusté si des données initiales sont impactées.
- **Cache Redis** : Toute modification métier (POST, PUT, DELETE) **DOIT** purger ou invalider le cache Redis associé (ex: suppression des patterns `items:list:*`).
- **Sessions** : Injection par dépendance stricte via `Depends(get_db)`.

---

## 🎨 6. UI & FRONTEND STANDARDS
L'apparence de la SPA (Vue.js) doit refléter le branding premium de Zenika.
- **Charte Graphique** : Zenika Red (`#E31937`), Anthracite (`#1A1A1A`), White (`#FFFFFF`).
- **Style** : Privilégier le *Glassmorphism*, les transitions douces, et des composants hautements responsifs.
- **Iconographie** : L'utilisation de SVG aléatoires est proscrite. Utiliser exclusivement la librairie `lucide-vue-next`.
- **UX de l'Agent** : Les dialogues et textes d'interface de l'Agent doivent adopter un ton **professionnel, contextuel et compact**.
- **Persistance et Mode Expert (History)** : Toute l'interface historisant l'usage de l'agent (`/history`) doit scrupuleusement reconstruire les méta-données expertes (étapes d'outils, usage de tokens FinOps, pensées) de façon native (`steps`, `thoughts`, `usage`, `parsedData`).

---

## ⚠️ 7. DIRECTIVES STRICTES ANTIGRAVITY (LLM)
1. **Discipline YAML** : Les fichiers `.yml` / `.yaml` exigent 2 espaces d'indentation stricte. Les Tabulations sont **strictement interdites**.
2. **Design Pattern `Container-First`** : Utilisez systématiquement le même `container_name` et `hostname` dans l'écosystème Docker.
3. **Idempotence et Doublons** : Avant de créer ou d'ingérer une ressource, anticipez les redondances dans l'état (les outils LLM ou Base de données doivent gérer silencieusement ou proprement les entités qui existent déjà).
4. **Configuration Centralisée des Modèles IA** : Il est **STRICTEMENT INTERDIT** de hardcoder des constantes de modèles (ex: `gemini-2.5-flash`) dans le code (comme `agent_api` ou `cv_api`). Ce référentiel doit être unifié via des variables d'environnement centralisées (facilite l'A/B testing et le tracking FinOps).
5. **Auto-génération Sécurisée de Data** : Lors de la création d'entités avec contraintes fortes (ex: création dynamique d'utilisateurs sans mot de passe spécifié par l'humain), les tools du LLM **doivent impérativement** auto-générer la dépendance silencieuse plutôt que d'échouer avec une erreur (ex: HTTP 422 Unprocessable Entity).
6. **Robustesse de Création de Fichiers (Write_To_File)** : Lors de l'utilisation d'outils d'écriture (comme `write_to_file`), les paramètres `TargetFile` et `Overwrite` **DOIVENT IMPÉRATIVEMENT** être générés en tout premier dans l'objet JSON (avant `CodeContent`) pour éviter la saturation de la file de streaming. De plus, il est **strictement interdit** d'écrire des fichiers via des commandes bash (`cat <<EOF` ou `echo`), car une erreur de quote figera le processus en attente d'input, bloquant définitivement l'agent.
7. **Privilège des Appels API (Environnement Dev)** : Lors de tests ou de vérifications métiers, privilégiez les appels API réels sur `https://dev.zenika.slavayssiere.fr` plutôt que d'exécuter des scripts locaux. Récupérez le token d'authentification via un appel à `auth/login` avec le compte admin (le mot de passe doit être récupéré dynamiquement via les outputs ou variables de Terraform).

---

## 🐳 8. DOCKER & CLOUD RUN STANDARDS (CONTAINER CONTRACT)
Tous les conteneurs du projet doivent impérativement respecter les règles dictées par le *Container Contract* de Cloud Run et les standards d'optimisations :
1. **Zéro-Trust Non-Root** : L'exécution de processus en tant que `root` (UID 0) est interdite. Les conteneurs Python doivent créer et switcher sur un `USER appuser`. Le front-end doit utiliser une image `nginx-unprivileged` sur le port `8080`.
2. **Multi-Stage Builds** : Chaque Dockerfile se doit d'utiliser des étapes de build (`AS builder`) pour séparer les outils de compilation (ex: `gcc`) du binaire final en prod. Cela renforce la sécurité et réduit l'empreinte de l'image.
3. **Graceful Shutdown (CMD System)** : Interdiction d'utiliser des appels shell comme `CMD ["sh", "-c", "..."]`. Favorisez l'appel de module cible : `CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]` pour palier l'absence potentielle de shell liés aux packages `distroless` ou les wrappers pip.
4. **Hygiène du Cache (.dockerignore)** : Les directives `COPY . .` doivent être sécurisées par des fichiers `.dockerignore` stricts (interdisant l'inclusion de `__pycache__`, environnements virtuels ou données de tests) pour maximiser la vitesse de Build.

---

## 🚀 9. DÉPLOIEMENT, VERSIONING & TERRAFORM
1. **Semantic Versioning** : Chaque microservice évolue indépendamment. **DOIT** posséder un fichier `VERSION` (Patch/Minor/Major) à sa racine. Cette version est lue pour le cycle de déploiement et est injectée dynamiquement.
2. **Injection Environnementale** : La variable d'environnement `APP_VERSION` doit toujours être synchronisée et injectée sur les conteneurs Cloud Run pour une parfaite observabilité (notamment via un endpoint `/version`).
3. **Idempotence des Déploiements** : Un script de déploiement (ex: `manage_env.py`) doit pouvoir être exécuté de façon répétée sans causer d'erreur HTTP asynchrone ; des invalidations de CDN ou d'imports non conditionnés doivent être évités s'ils génèrent des erreurs `409 Conflict`.
4. **Cycle de vie Cloud Run (Terraform)** : La balise `deletion_protection = false` n'est plus supportée sur les ressources `google_cloud_run_v2_service` et se doit d'être retirée des manifests HCL.
