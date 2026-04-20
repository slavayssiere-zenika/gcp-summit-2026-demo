# 📅 Roadmap Hebdomadaire (Sprint 16 - 20 Avril)

## 🎯 Objectif : Consolidation Gouvernance & Intelligence BigQuery

---

### 🛡️ Phase 1 : Gouvernance & Sécurité Admin (Lundi)
*Focalisation sur l'identité et les accès privilégiés.*

- [ ] **Audit Trail** : Loguer les changements de statut utilisateur dans la base d'audit.

---

### 🌍 Phase 4 : Intelligence Marché & ROME (Jeudi)
*Croisement des données internes vs externes.*

- [ ] **Analyse de Gap** : Développer un outil MCP croisant AlloyDB et BigQuery pour identifier les compétences manquantes.

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

- [x] **[SEC-F06 — ✅ FAIT] Semantic Cache LLM (`agent_router_api`)** : `semantic_cache.py` + intégration dans `main.py`, cosine similarity Redis, TTL=15min, seuil=0.95, exemptions temps-réel, métriques Prometheus, log BQ `action="semantic_cache_hit"`. Tests dans `tests/test_semantic_cache.py`.

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

### 🤖 Backlog Agent Architecture

#### 📌 À faire

- [x] **[Axe 2/ADR12-1 — P2] Extraire `agent_commons` partagé (DRY)** : Package Python mutualisé entre HR, Ops et Missions — `mcp_client`, `session`, `metadata`, `mcp_proxy`, `runner`, `guardrails`, `finops` — ~680 lignes supprimées, 32 tests ✅

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

### 🐛 Bugs ouverts

#### 🔴 Critiques

- [ ] **[ANTI-HALL-001] Guardrail hors-scope — tarte tatin** : Malgré la Règle 0 renforcée, l'agent répond encore à des questions hors-scope (recettes) si la session Redis est contaminée. **Correctif : déployer `agent_router_api` sur Cloud Run** pour activer le correctif `main.py` (priorité `session_id` body sur JWT). Sans redéploiement, l'isolation de session est inactive en GCP dev.

#### 🟡 Mineurs / Ajustements

- [ ] **[MULTI-001 / EDGE-004] Timeout sur requêtes longues** : Certaines requêtes multi-step retournent 0 tokens (timeout ou session Redis expirée). Augmenter `TIMEOUT_SECONDS` à 90s dans `agent_prompt_tests.py` ou investiguer la limite Cloud Run.

---

### 🏗️ ADR-0012 — Axes d'Amélioration Architecture Multi-Agent A2A

#### 🟡 Moyen Terme — Structurel

- [x] **[ADR12-3] Cache sémantique pré-délégation** : ✅ Couvert par SEC-F06 — `SemanticCache.get()` intercepte dans `main.py` ligne 153, **avant** `run_agent_query` donc avant toute délégation A2A. TTL=15min, seuil=0.95, metrics Prometheus.

- [x] **[ADR12-4] Contrat Pydantic A2A formalisé** : `agent_commons/schemas.py` — `A2ARequest`, `A2AResponse`, `AgentStep`, `TokenUsage`. Source de vérité unique, validation auto FastAPI, round-trip testé. 20 tests ✅.

- [x] **[ADR12-5] Endpoint `/health/agents` agrégé sur le Router** : `GET /health/agents` public sur `agent_router_api` — sonde HR + Ops + Missions en parallèle (`asyncio.gather`), retourne `healthy`/`degraded`/`unhealthy`, HTTP 503 si tout est KO. Métriques `agent_health_probe_total`. 6 tests ✅.

- [ ] **[ADR12-6] Consumer-Driven Contract Tests (A2A)** : Tests de contrat entre le Router (consumer) et chaque sous-agent (provider) pour détecter les régressions de protocole A2A en CI avant déploiement (ex: avec `pact-python`).

#### 🟢 Long Terme — Évolutivité

- [ ] **[ADR12-7] Agent Discovery dynamique** : Remplacer le câblage statique des URLs (`AGENT_HR_API_URL`, etc.) par un registre de services Redis/Consul. Les nouveaux agents s'auto-enregistrent, le Router les découvre sans modification de code.

- [ ] **[ADR12-8] Agent Generalist pour requêtes triviales** : Créer un `agent_general_api` avec modèle léger (ex: `gemini-flash`) pour les requêtes ne nécessitant pas d'outil (FAQ, aide navigation), évitant la double inférence coûteuse sur des questions simples.

- [ ] **[ADR12-9] Parallélisation des appels A2A multi-domaine** : Pour les requêtes cross-domaine, le Router devrait pouvoir appeler HR + Missions en parallèle via `asyncio.gather`, réduisant la latence de ~3-5s à ~1.5s sur les requêtes composites.