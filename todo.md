# 📅 Roadmap Hebdomadaire (Sprint 16 - 20 Avril)

## 🎯 Objectif : Consolidation Gouvernance & Intelligence BigQuery

---

### 🛡️ Phase 1 : Gouvernance & Sécurité Admin (Lundi)
*Focalisation sur l'identité et les accès privilégiés.*

- [ ] **Gestion Inactive** : Ajouter un flag `is_active` pour les utilisateurs et CVs afin de les exclure des recherches/staffing.
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
- [ ] **Infrastructure as Code** : Refactoriser `cloudrun.tf` pour isoler chaque service Cloud Run dans son propre fichier (split monolith).
- [ ] Intégration BigQuery ML pour la prédiction de disponibilité.
- [ ] Dashboard de performance des outils MCP (latency vs success rate).
- [ ] Automatisation des rapports hebdomadaires par email via Cloud Functions.
- [ ] Code en python avec un docker pour le service mcp.
- [ ] Déploiement dans le cloud GCP via le projet platform-engineering.

### 🚀 Nouvelles Features Proposées
- [ ] **Intégration d'Agendas (Google Calendar/Outlook)** : Connecter la Console avec les calendriers des consultants pour affiner de manière déterministe les disponibilités dans les réponses de l'agent.
- [ ] **Interface ChatOps (Slack / Google Chat)** : Exporter l'Agent API sous la forme d'un Bot directement accessible en messagerie d'entreprise pour les commerciaux et managers.
- [ ] **Notification Proactives & Actions Push** : Mettre en place un système d'alerte pour les "Skills Gap" dès qu'une opportunité du marché ne trouve plus de correspondance interne.
- [ ] **Génération Automatique de Réponses (RFP Engine)** : Un agent spécialisé capable de générer des réponses techniques ou commerciales aux Appels d'Offres à partir des références passées, des CVs et des expertises de l'équipe disponible.
- [ ] **Amélioration de CV ciblée (IA)** : Fonctionnalité permettant à l'utilisateur de demander à l'agent de réviser ou d'adapter son CV de façon générale ou pour correspondre spécifiquement à une opportunité de mission.
- [ ] **Catalogue ADR Frontend** : Implémenter une interface dans la SPA (Vue.js) pour consulter et indexer visuellement l'ensemble des Architecture Decision Records (ADR) du projet.
- [ ] **Lifecycle d'une Mission** : Mettre en place la suite de la gestion de la mission (depuis le statut de proposition `draft`, jusqu'au `staffing` actif, puis à la `clôture`). Permettre de lier des consultants à une mission de façon persistante.