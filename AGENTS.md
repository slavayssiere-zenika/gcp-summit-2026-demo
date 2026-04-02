# 📜 Projet Zenika Console Agent - Golden Rules

Ce document dicte le comportement, les standards et les contraintes non négociables pour l'Agent Antigravity et les développeurs. **Le non-respect de ces règles cassera la plateforme.**

---

## 🏗️ 1. ARCHITECTURE & STACK
L'environnement est strictement micro-serviciel et repose sur **Docker Compose**.
- **Microservices natifs** : `users_api`, `items_api`, `competencies_api`, `cv_api`.
- **Orchestrateur** : `agent_api` (FastAPI + Google ADK + Gemini).
- **Frontend** : `frontend` (Vue.js + proxy Nginx pointant `/api/` vers `agent_api`).
- **Data Layer** : PostgreSQL (namespaces partagés), Redis (Cache/Queue).
- **Réseau interne** : `monitoring_net` est obligatoire pour la résolution DNS.

---

## 🤖 2. MCP & AGENT ORCHESTRATION
L'Agent intelligent dialogue avec l'écosystème via le protocole MCP (Model Context Protocol).
- **Serveurs MCP Autonomes** : Chaque sous-service possède son propre serveur MCP. **ATTENTION** : La directive architecturale principale est de privilégier les flux **HTTP standards (REST)** dès que possible au détriment du protocole SSE (Server-Sent Events) pour des raisons de scalabilité et de simplicité (stateless).
- **Règle de Fonctionnalité** : Toute nouvelle route / logique métier implémentée dans une API **DOIT IMPÉRATIVEMENT** faire l'objet d'un outil (`Tool`) exposé dans le `mcp_server.py` de cette même API.
- **Enregistrement ADK (`agent.py`)** : Les outils distants doivent être mappés en tant que fonctions ou instances natives dans `agent_api/agent.py` avec des **Docstrings riches** (cruciales pour que le LLM sache quand les appeler).

---

## 🛡️ 3. SÉCURITÉ ZERO-TRUST (JWT)
Aucune API n'est considérée comme sécurisée par défaut dans le réseau interne.
- **Verrouillage par défaut** : TOUS les endpoints (sauf `/health`, `/metrics`, `/docs`) **DOIVENT** être protégés statiquement par le validateur `dependencies=[Depends(verify_jwt)]` sur leur `APIRouter`.
- **Propagation de l'Identité** : Lorsqu'un microservice (ou un appel MCP) contacte un autre microservice, le Header HTTP `Authorization: Bearer <token>` **DOIT** être capturé depuis la requête entrante et transmis explicitement dans la requête sortante.

---

## 📊 4. OBSERVABILITÉ & TRACING
Le monitoring n'est pas une option, c'est l'épine dorsale du debugging asynchrone.
- **Métrique (Prometheus)** : `Instrumentator().instrument(app).expose(app)` est obligatoire dans le `main.py` de toute nouvelle API.
- **Trace (Tempo/OTel)** : *L'oubli de cette règle brise toute la chaîne.* Lors de toute exécution distribuée (ex: Ingestion RAG, import inter-APIs), `inject(headers)` est STRICTEMENT obligatoire avant chaque requête HTTP sortante `httpx` pour propager le Span. Le `OTEL_SERVICE_NAME` doit strictement correspondre au `container_name` Docker.

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

---

## ⚠️ 7. DIRECTIVES STRICTES ANTIGRAVITY (LLM)
1. **Discipline YAML** : Les fichiers `.yml` / `.yaml` exigent 2 espaces d'indentation stricte. Les Tabulations sont **strictement interdites**.
2. **Design Pattern `Container-First`** : Utilisez systématiquement le même `container_name` et `hostname` dans l'écosystème Docker.
3. **Idempotence et Doublons** : Avant de créer ou d'ingérer une ressource, anticipez les redondances dans l'état (les outils LLM ou Base de données doivent gérer silencieusement ou proprement les entités qui existent déjà).

---

## 🐳 8. DOCKER & CLOUD RUN STANDARDS (CONTAINER CONTRACT)
Tous les conteneurs du projet doivent impérativement respecter les règles dictées par le *Container Contract* de Cloud Run et les standards d'optimisations :
1. **Zéro-Trust Non-Root** : L'exécution de processus en tant que `root` (UID 0) est interdite. Les conteneurs Python doivent créer et switcher sur un `USER appuser`. Le front-end doit utiliser une image `nginx-unprivileged` sur le port `8080`.
2. **Multi-Stage Builds** : Chaque Dockerfile se doit d'utiliser des étapes de build (`AS builder`) pour séparer les outils de compilation (ex: `gcc`) du binaire final en prod. Cela renforce la sécurité et réduit l'empreinte de l'image.
3. **Graceful Shutdown (CMD System)** : Interdiction d'utiliser des appels shell comme `CMD ["sh", "-c", "..."]`. Favorisez l'appel de module cible : `CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]` pour palier l'absence potentielle de shell liés aux packages `distroless` ou les wrappers pip.
4. **Hygiène du Cache (.dockerignore)** : Les directives `COPY . .` doivent être sécurisées par des fichiers `.dockerignore` stricts (interdisant l'inclusion de `__pycache__`, environnements virtuels ou données de tests) pour maximiser la vitesse de Build.
