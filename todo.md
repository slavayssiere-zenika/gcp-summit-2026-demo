# 🗺️ Product Roadmap & Todo (Updated 2026-04-23)

## 🏁 Sprint 16 (En cours) : Focus GCP Summit Demo & Finalisation
*Objectif : Mettre la plateforme sur les rails pour la démonstration finale GCP Summit.*

- [ ] **Analyse de Tension (Skill Gap)** : Développer un outil croisant les compétences requises par les Missions (demande) et les compétences des Consultants (offre) pour identifier nos besoins de recrutement.
- [ ] **Dashboard Looker** : Créer une visualisation "Skill Gap" connectée à BigQuery.
- [ ] **Scénario de Démo GCP Summit** : Peaufiner les prompts de l'agent pour illustrer le FinOps et le Staffing Prédictif.
- [ ] **RGPD / Démo** : Créer une agence fake pour le GCP Summit avec données anonymisées.
- [ ] **Validation Finale** : Simulation de fin de sprint et revue de code.

## ⚙️ Sprint 17 : MCO, SRE & Observabilité Antigravity
*Objectif : Stabiliser les opérations, l'expérience développeur (DevEx) et les outils de debugging IA.*

- [ ] **[Platform Engineering] Automatisation du cycle éphémère Matin/Soir** : Créer un Cloud Run Job (`manage-env-job`) + Cloud Scheduler Jobs (`07:00 deploy`, `19:00 destroy`).
- [ ] **Sécurité IAM / Accès Zero-Trust (IDE vers GCP)** : Créer un CLI proxy MCP (`mcp_gcp_proxy.py`).
- [ ] **Infrastructure Cloud Run** : Restreindre serveurs MCP Cloud Run à "Cloud Run Invoker".
- [ ] **Observabilité & Debugging GCP** : Tool MCP `search_cloud_logs_by_trace` et `get_recent_500_errors`.
- [ ] **Infrastructure & Ops GCP** : Tool MCP `inspect_pubsub_dlq` et `get_redis_invalidation_state`.
- [ ] **Base de Données & Auth GCP** : Tool MCP `execute_read_only_query` et `generate_dev_jwt`.
- [ ] **Dashboard de performance des outils MCP** : (latency vs success rate).

## 🚀 Sprint 18 : Features Métiers, ML & ChatOps
*Objectif : Rendre le produit plus interactif et intégrer des capacités prédictives/génératives avancées.*

- [ ] **Interface ChatOps (Slack / Google Chat)** : Exporter l'Agent API sous forme de Bot.
- [ ] **Intégration BigQuery ML** : Pour la prédiction de disponibilité.
- [ ] **Notification Proactives & Actions Push** : Système d'alerte pour les "Skills Gap".
- [ ] **Génération Automatique de Réponses (RFP Engine)** : Agent spécialisé pour la réponse aux Appels d'Offres.
- [ ] **Amélioration de CV ciblée (IA)** : Adapter un CV à une opportunité de mission.
- [ ] **Évaluation des compétences** : Processus de validation.
- [ ] **Automatisation des rapports hebdomadaires par email** : Via Cloud Functions.

## 🏗️ Sprint 19 : Tech Debt & Next-Gen Architecture A2A
*Objectif : Remboursement de la dette technique et évolution de l'architecture multi-agent.*

- [ ] **Déterminisme des Conteneurs** : Remplacer tags mutables (`:3.11-slim`) par Digests SHA256.
- [ ] **Upgrade Python & Node** : Python 3.12/3.13 et Node 22+ LTS.
- [ ] **Mise à niveau Terraform Google Provider** : Bump `hashicorp/google` (`~> 5.15.0`).
- [ ] **Dépendances Lockfiles** : Adoption de `uv` ou `pip-tools`.
- [ ] **Code en python avec un docker pour le service mcp**.
- [ ] **Déploiement dans le cloud GCP via le projet platform-engineering**.
- [ ] **Catalogue ADR Frontend** : Implémenter l'interface de consultation des ADR dans la SPA.
- [ ] **Data Quality CVs** : Identification des CV obsolètes.
- [ ] **[ADR12-6] Consumer-Driven Contract Tests (A2A)** : Tests de contrat Router/Sous-agents.
- [ ] **[ADR12-7] Agent Discovery dynamique** : Registre de services Redis/Consul.
- [ ] **[ADR12-8] Agent Generalist** : Créer `agent_general_api` (ex: `gemini-flash`).
- [ ] **[ADR12-9] Parallélisation des appels A2A multi-domaine**.