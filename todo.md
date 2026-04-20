# 📅 Roadmap Hebdomadaire (Sprint 16 - 20 Avril)

## 🎯 Objectif : Consolidation Gouvernance & Intelligence BigQuery

---

### 🛡️ Phase 1 : Gouvernance & Sécurité Admin (Lundi)
*Focalisation sur l'identité et les accès privilégiés.*

- [ ] **Audit Trail** : Loguer les changements de statut utilisateur dans la base d'audit.

---

### 🌍 Phase 4 : Intelligence Marché & ROME (Jeudi)
*Croisement des données internes vs externes.*

- [x] **Ingestion ROME** : Charger le référentiel ROME 4.0 et les tendances du marché dans BigQuery.
- [ ] **Analyse de Gap** : Développer un outil MCP croisant AlloyDB et BigQuery pour identifier les compétences manquantes.
- [x] **BigQuery MCP Server** : Unifier l'accès à BigQuery via un nouveau serveur MCP dédié.

---

### 🎨 Phase 5 : Pilotage & Démo (Vendredi)
*Rendre la donnée visuelle et actionnable.*

- [ ] **Dashboard Looker** : Créer une visualisation "Skill Gap" connectée à BigQuery.
- [ ] **Scénario de Démo** : Peaufiner les prompts de l'agent pour illustrer le FinOps et le Staffing Prédictif.
- [ ] **Validation Finale** : Simulation de fin de sprint et revue de code.

---

### 📌 Backlog / Idées (Ancien Todo)
- [ ] Intégration BigQuery ML pour la prédiction de disponibilité.
- [ ] Dashboard de performance des outils MCP (latency vs success rate).
- [ ] Automatisation des rapports hebdomadaires par email via Cloud Functions.
- [ ] Code en python avec un docker pour le service mcp.
- [ ] Déploiement dans le cloud GCP via le projet platform-engineering.
- [ ] **[Platform Engineering] Automatisation du cycle éphémère Matin/Soir** : Créer un Cloud Run Job (`manage-env-job`) + deux Cloud Scheduler Jobs (`07:00 → deploy --env dev`, `19:00 → destroy --env dev`) pour automatiser la création/destruction journalière de la plateforme dev sans intervention manuelle. S'appuyer sur la containerisation de `manage_env` (voir conv. `dee36a0e`).

- [ ] **[SEC-F06 — 🔴 CRITIQUE] Semantic Cache LLM (`agent_router_api`)** : Absence de cache sémantique sur les requêtes entrantes vers l'agent. Un attaquant peut exfiltrer la base de connaissance (CVs, compétences, missions) par variantes de prompt, générant un coût Gemini linéaire non borné (ex : 10 000 requêtes variantes = 10 000 appels facturés).

  **Contexte technique :**
  - Le cache Redis actuel est structurel (clé exacte). Aucune détection de requêtes sémantiquement similaires avant l'appel LLM.
  - Defense FinOps unique : rate limiter WAF (300 req/min/IP), contournable via rotation d'IPs.
  - L'embedding model `gemini-embedding-001` est déjà utilisé dans `cv_api` et `missions_api`.

  **Prompt de relance :**
  > Implémente le Semantic Cache LLM dans `agent_router_api` (F-06 du rapport /analyse-security du 2026-04-16). L'objectif est d'intercepter les requêtes sémantiquement similaires avant l'appel Gemini en utilisant l'embedding `gemini-embedding-001` + cosine similarity sur Redis. TTL=15min, seuil=0.95, liste d'exemptions pour les requêtes temps-réel (disponibilité, aujourd'hui). Logger les hits dans BigQuery `ai_usage` avec `action="semantic_cache_hit"`. Fichiers cibles : `agent_router_api/main.py` + nouveau module `agent_router_api/semantic_cache.py`.

---

- [ ] **Interface ChatOps (Slack / Google Chat)** : Exporter l'Agent API sous la forme d'un Bot directement accessible en messagerie d'entreprise pour les commerciaux et managers.
- [ ] **Notification Proactives & Actions Push** : Mettre en place un système d'alerte pour les "Skills Gap" dès qu'une opportunité du marché ne trouve plus de correspondance interne.
- [ ] **Génération Automatique de Réponses (RFP Engine)** : Un agent spécialisé capable de générer des réponses techniques ou commerciales aux Appels d'Offres à partir des références passées, des CVs et des expertises de l'équipe disponible.
- [ ] **Amélioration de CV ciblée (IA)** : Fonctionnalité permettant à l'utilisateur de demander à l'agent de réviser ou d'adapter son CV de façon générale ou pour correspondre spécifiquement à une opportunité de mission.
- [ ] **Catalogue ADR Frontend** : Implémenter une interface dans la SPA (Vue.js) pour consulter et indexer visuellement l'ensemble des Architecture Decision Records (ADR) du projet.
- [ ] **Lifecycle d'une Mission** : Mettre en place la suite de la gestion de la mission (depuis le statut de proposition `draft`, jusqu'au `staffing` actif, puis à la `clôture`). Permettre de lier des consultants à une mission de façon persistante.
- [ ] **Amélioration continue des CV** : Fonction - "comment améliorer mon CV ?"
- [ ] **Data Quality CVs** : Identifier : "quels CV sont trop vieux ?"
- [ ] **RGPD / Démo** : Créer une agence fake pour le GCP Summit avec données anonymisées
- [ ] **Évaluation des compétences** : Processus de validation et d'évaluation de la compétence pour chaque consultant
- [ ] **Data Ingestion** : Exclure systématiquement les dossiers nommés `_archives` du scan et de l'indexation

---

### 🤖 Backlog Agent Architecture (issu de l'analyse architecture_agents_analysis)

#### ✅ Déjà réalisé
- [x] **[Axe 1 — P1]** Créer `agent_missions_api` (split HR/Missions) — A2A routing, prompts, LB, Terraform, tests
- [x] **[Axe 1 — P0]** Corriger FinOps URL dans `missions_api` (`agent_api:8002` → `MARKET_MCP_URL`)

#### 📌 À faire

- [ ] **[Axe 2 — P2] Extraire `agent_core` partagé (DRY)** : Créer un package Python `agent_core/` mutualisé entre HR, Ops et Missions contenant :
  - `run_agent_loop()` — boucle générique d'exécution ADK + extraction metadata
  - `finops_logger()` — log BigQuery mutualisé avec retry tenacity
  - `hallucination_guardrail()` — guardrail standardisé
  - `BaseMCPAgent` — classe de base ABC
  - Cela élimine ~300 lignes dupliquées × 3 agents

- [ ] **[Axe 3 — P3] Créer `monitoring_mcp` dédié** : Séparer les outils de monitoring de `market_mcp` pour désencombrer ce dernier. Outils cibles :
  - `get_service_logs` (GCP Cloud Logging)
  - `list_cloud_run_services`
  - `check_all_components_health`
  - `get_infrastructure_topology`
  - `get_finops_report` (BigQuery `ai_usage`)

- [ ] **[Axe 4 — P4] Lifecycle complet des missions dans l'agent** : Ajouter les statuts `draft → analyzing → staffed → active → closed` dans `missions_mcp` :
  - `update_mission_status(mission_id, status)`
  - `assign_consultant_to_mission(mission_id, user_id, role)`
  - `get_mission_timeline(mission_id)`
  - `close_mission(mission_id, outcome_notes)`
  - Extraire la logique de `staffing_heuristics.txt` dans le system prompt de `agent_missions_api`

---

### 🎨 Frontend — Nouvelles pages

- [ ] **[P1] Page Documentation Agents** (`/docs/agents`) : Créer une page Vue.js dans le menu Documentation qui :
  - Affiche les specs méier de chaque agent via son endpoint `GET /spec`
  - Tabs : Router · HR · Ops · Missions
  - Les `spec.md` sont générés par `scripts/generate_specs.py` au moment du `/git-push`
  - Affiche le markdown rendu (comme `Specs.vue`) avec version + statut de santé

---

### 🐛 Bugs identifiés — Tests automatisés (run 93 tests, 2026-04-15)

#### 🔴 Critiques

- [x] **[COM-006 / ANTI-HALL] Hallucination `search_best_candidates`** : L'agent HR invente des ressources inexistantes. Quand une compétence rare retourne 0 profils, il génère quand même une liste de N consultants fictifs au lieu de dire "aucun résultat". **Correctif : GUARDRAIL 2 implémenté dans `agent_hr_api/agent.py` — `_is_empty_candidate_result()` + interception post-run + substitution de réponse + step `GUARDRAIL_COM006` injecté en Expert Mode. 23 tests unitaires ajoutés dans `test_guardrail.py`.**

- [x] **[ROUTE-006 / MISSIONS-001/002/003] Router ignore `ask_missions_agent`** : Les questions sur les missions client sont systématiquement routées vers `ask_hr_agent` au lieu de `ask_missions_agent`. **Cause racine : `agent_missions_api.system_instruction` absente du `PROMPTS_MAP` dans `sync_prompts.py` → la base GCP n'a jamais reçu la distinction HR/Missions.** ✅ Correctifs : (1) ajout de `agent_missions_api` dans `PROMPTS_MAP`, (2) `sync_prompts.py` ajouté en étape 2 du workflow `/git-push`.

#### 🟠 Importants

- [x] **[OPS-002] Bug `list_logs` — crash session ADK** : La requête de logs applicatifs (et certaines questions Missions) déclenchait une erreur `No function call event found for function responses ids`. **Cause racine : la session Redis contenait un `function_response` orphelin (sans `function_call` correspondant) suite à une interruption en mi-stream, provoquant une `ValueError` dans le `Runner ADK` non interceptée, retournant `{"response": "Erreur: ...", "source": "error"}` (sans `usage`/`steps`/`session_id`) qui cassait le schema validator et l'UI FinOps. Correctif : wrapping de la boucle `runner.run_async()` dans un `try/except ValueError` dans `run_agent_query` — l'erreur "No function call event found" est interceptée, un warning `adk_runner:SESSION_CORRUPTION` est ajouté aux `steps`, et une réponse dégradée STRUCTURÉE (schema-complète) est retournée avec un message utilisateur actionnable. 3 tests OPS-002 ajoutés dans `agent_router_api/test_main.py`.** → `agent_router_api/agent.py`

- [x] **[OPS-006] Bug `list_gcp_services`** : `ServicesAsyncClient.__init__() got an unexpected keyword argument 'project'`. **Correctif : `ServicesAsyncClient()` initialisé sans argument `project` + `get_gcp_project_id_from_metadata()` interroge `http://metadata.google.internal` (priorité : env var > metadata server > google.auth.default). Filtre projet appliqué via `parent=f"projects/{project_id}/locations/-"`. 6 tests OPS-006 ajoutés dans `market_mcp/tests/test_mcp_server.py`.** → `market_mcp/mcp_server.py`

- [ ] **[ANTI-HALL-001] Guardrail hors-scope — tarte tatin** : Malgré la Règle 0 renforcée, l'agent répond encore à des questions hors-scope (recettes) si la session Redis est contaminée. **Correctif : déployer `agent_router_api` sur Cloud Run** pour activer le correctif `main.py` (priorité `session_id` body sur JWT). Sans redéploiement, l'isolation de session est inactive en GCP dev.

#### 🟡 Mineurs / Ajustements

- [ ] **[MULTI-001 / EDGE-004] Timeout sur requêtes longues** : Certaines requêtes multi-step retournent 0 tokens (timeout ou session Redis expirée). Augmenter `TIMEOUT_SECONDS` à 90s dans `agent_prompt_tests.py` ou investiguer la limite Cloud Run.

- [x] **[STAFF-003] Détection de conflit de staffing** : Ahmed KANOUN est dit "disponible" pour la mission PR-2026-ZEN-FIN-04 alors qu'il est déjà proposé sur une autre mission. **Correctif : (1) Nouvel endpoint `GET /missions/user/{user_id}/active` dans `missions_api` qui retourne les missions où le user figure dans `proposed_team` (avec filtre sentinelle `user_id=0`). (2) `get_user_availability` dans `users_api/mcp_server.py` enrichi avec un appel croisé + champs `active_missions`, `is_available`, `conflict_detected`, `summary`. Dégradation gracieuse si `missions_api` est indisponible. (3) Description du Tool MCP mise à jour pour guider le LLM. 4 tests STAFF-003 ajoutés.**

---

### 🏗️ ADR-0012 — Axes d'Amélioration Architecture Multi-Agent A2A

> Source : [ADR 0012](docs/adr/0012-architecture-multi-agent-a2a.md) — Rédigé le 2026-04-16

#### 🔴 Court Terme — Critique

- [ ] **[ADR12-1] Librairie partagée `agent_commons`** : ~300 lignes dupliquées dans `run_agent_query` entre `agent_hr_api`, `agent_ops_api`, `agent_missions_api`. Créer un package Python `agent_commons/` avec :
  - `run_agent_and_collect()` — boucle ADK générique + extraction steps/thoughts
  - `check_hallucination_guardrail()` — guardrail standardisé
  - `log_tokens_to_bq()` — fire-and-forget FinOps mutualisé
  - *(Note: déjà listé en Axe 2 P2 dans le Backlog Agent Architecture — consolider les deux tickets)*

- [x] **[ADR12-2] Circuit-Breaker + Retry sur les appels A2A** : Actuellement, un sous-agent KO retourne une erreur opaque sans retry ni dégradation gracieuse. Implémenter :
  - 1 retry avec backoff 2s via `tenacity` ou `httpx` sur chaque `POST /a2a/query`
  - Réponse structurée `{"degraded": true, "reason": "..."}` côté Router ✅
  - Métriques Prometheus : `a2a_call_duration_seconds{agent}` + `a2a_call_errors_total{agent}` + `a2a_call_retries_total{agent}` ✅

- [ ] **[ADR12-3] Cache sémantique pré-délégation** : Pour les requêtes identiques ou très proches, le Router doit vérifier le cache Redis sémantique (`market_mcp`) avant de déclencher une double inférence LLM. Économie cible : ~100% du coût sur les requêtes répétées.

#### 🟡 Moyen Terme — Structurel

- [ ] **[ADR12-4] Contrat Pydantic A2A formalisé** : Définir des modèles Pydantic partagés `A2ARequest` / `A2AResponse` / `AgentStep` utilisés par le Router ET les sous-agents. Bénéfices : validation auto + docs OpenAPI précises sur `/a2a/query`.

- [ ] **[ADR12-5] Endpoint `/health/agents` agrégé sur le Router** : Sonder les 3 sous-agents (`GET /health`) et retourner un statut agrégé. Le frontend peut désactiver dynamiquement les features selon l'état des sous-agents (ex: bouton "Staffing" grisé si `agent_missions_api` est KO).

- [ ] **[ADR12-6] Consumer-Driven Contract Tests (A2A)** : Tests de contrat entre le Router (consumer) et chaque sous-agent (provider) pour détecter les régressions de protocole A2A en CI avant déploiement (ex: avec `pact-python`).

#### 🟢 Long Terme — Évolutivité

- [ ] **[ADR12-7] Agent Discovery dynamique** : Remplacer le câblage statique des URLs (`AGENT_HR_API_URL`, etc.) par un registre de services Redis/Consul. Les nouveaux agents s'auto-enregistrent, le Router les découvre sans modification de code.

- [ ] **[ADR12-8] Agent Generalist pour requêtes triviales** : Créer un `agent_general_api` avec modèle léger (ex: `gemini-flash`) pour les requêtes ne nécessitant pas d'outil (FAQ, aide navigation), évitant la double inférence coûteuse sur des questions simples.

- [ ] **[ADR12-9] Parallélisation des appels A2A multi-domaine** : Pour les requêtes cross-domaine, le Router devrait pouvoir appeler HR + Missions en parallèle via `asyncio.gather`, réduisant la latence de ~3-5s à ~1.5s sur les requêtes composites.