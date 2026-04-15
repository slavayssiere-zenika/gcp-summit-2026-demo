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

### 🚀 Nouvelles Features Proposées
- [ ] **Interface ChatOps (Slack / Google Chat)** : Exporter l'Agent API sous la forme d'un Bot directement accessible en messagerie d'entreprise pour les commerciaux et managers.
- [ ] **Notification Proactives & Actions Push** : Mettre en place un système d'alerte pour les "Skills Gap" dès qu'une opportunité du marché ne trouve plus de correspondance interne.
- [ ] **Génération Automatique de Réponses (RFP Engine)** : Un agent spécialisé capable de générer des réponses techniques ou commerciales aux Appels d'Offres à partir des références passées, des CVs et des expertises de l'équipe disponible.
- [ ] **Amélioration de CV ciblée (IA)** : Fonctionnalité permettant à l'utilisateur de demander à l'agent de réviser ou d'adapter son CV de façon générale ou pour correspondre spécifiquement à une opportunité de mission.
- [ ] **Catalogue ADR Frontend** : Implémenter une interface dans la SPA (Vue.js) pour consulter et indexer visuellement l'ensemble des Architecture Decision Records (ADR) du projet.
- [ ] **Lifecycle d'une Mission** : Mettre en place la suite de la gestion de la mission (depuis le statut de proposition `draft`, jusqu'au `staffing` actif, puis à la `clôture`). Permettre de lier des consultants à une mission de façon persistante.

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

- [ ] **[COM-006 / ANTI-HALL] Hallucination `search_best_candidates`** : L'agent HR invente des ressources inexistantes. Quand une compétence rare retourne 0 profils, il génère quand même une liste de N consultants fictifs au lieu de dire "aucun résultat". **Correctif : valider que la liste retournée par `search_best_candidates` est non-vide avant d'affirmer une disponibilité.** → `agent_hr_api/agent.py`

- [ ] **[ROUTE-006 / MISSIONS-001/002/003] Router ignore `ask_missions_agent`** : Les questions sur les missions client sont systématiquement routées vers `ask_hr_agent` au lieu de `ask_missions_agent`. Le prompt est à jour mais le Router n'a peut-être pas ce tool enregistré. **Correctif : vérifier que `ask_missions_agent` est bien déclaré dans `agent_router_api/agent.py` et que le sous-agent est up.** → `agent_router_api/agent.py`

#### 🟠 Importants

- [ ] **[OPS-002] Bug `list_logs` — crash session ADK** : La requête de logs applicatifs déclenche une erreur `No function call event found for function responses ids`. Le tool `list_logs` de l'Ops agent plante silencieusement. → `agent_ops_api/mcp_server.py`

- [ ] **[OPS-006] Bug `list_gcp_services`** : `ServicesAsyncClient.__init__() got an unexpected keyword argument 'project'`. Le client Cloud Run API est initialisé avec un argument obsolète. **Correctif : remplacer l'init par `ServicesAsyncClient()` puis filtrer par projet via `parent=f"projects/{project}/locations/-"`.** → `agent_ops_api/mcp_server.py`

- [ ] **[ANTI-HALL-001] Guardrail hors-scope — tarte tatin** : Malgré la Règle 0 renforcée, l'agent répond encore à des questions hors-scope (recettes) si la session Redis est contaminée. **Correctif : déployer `agent_router_api` sur Cloud Run** pour activer le correctif `main.py` (priorité `session_id` body sur JWT). Sans redéploiement, l'isolation de session est inactive en GCP dev.

#### 🟡 Mineurs / Ajustements

- [ ] **[MULTI-001 / EDGE-004] Timeout sur requêtes longues** : Certaines requêtes multi-step retournent 0 tokens (timeout ou session Redis expirée). Augmenter `TIMEOUT_SECONDS` à 90s dans `agent_prompt_tests.py` ou investiguer la limite Cloud Run.

- [ ] **[STAFF-003] Détection de conflit de staffing** : Ahmed KANOUN est dit "disponible" pour la mission PR-2026-ZEN-FIN-04 alors qu'il est déjà proposé sur une autre mission. Le tool `get_user_availability` ne détecte pas les missions en cours, seulement les indisponibilités déclarées. **Correctif : enrichir `get_user_availability` pour croiser avec les missions actives.**