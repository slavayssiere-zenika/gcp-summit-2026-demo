# 📅 Roadmap Hebdomadaire (Sprint 16 - 20 Avril)

## 🎯 Objectif : Consolidation Gouvernance & Intelligence BigQuery

---

### 🛡️ Phase 1 : Gouvernance & Sécurité Admin (Lundi)
*Focalisation sur l'identité et les accès privilégiés.*

- [x] **Gestion Inactive** : Ajouter un flag `is_active` pour les utilisateurs et CVs afin de les exclure des recherches/staffing.
- [ ] **Audit Trail** : Loguer les changements de statut utilisateur dans la base d'audit.

---

### 📊 Phase 2 : Observabilité & SLOs (Mardi)
*Passer d'une surveillance réactive à un engagement de niveau de service.*

- [x] **Définition SLIs** : Identifier les métriques de latence (p95) et taux d'erreur par micro-service.
- [x] **Provisionnement SLO** : Créer les dashboards et alertes Cloud Monitoring via Terraform.
- [x] **Health Monitoring** : Intégrer les métriques OTel dans un tableau de bord SLO global.

---

### 🏛️ Phase 3 : BigQuery Foundation & FinOps (Mercredi)
*Mise en place de la brique analytique pour l'IA.*

- [x] **Pipeline BQ** : Créer le dataset et les tables `token_usage` et `agent_latency`.
- [x] **Streaming Logs** : Exporter les métriques de consommation de l'IA (Gemini) vers BigQuery à chaque appel.
- [x] **Outil Agent** : Créer un outil MCP `get_finops_report` pour que l'agent analyse ses propres coûts.

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

### 🚀 Nouvelles Features Proposées
- [ ] **Intégration d'Agendas (Google Calendar/Outlook)** : Connecter la Console avec les calendriers des consultants pour affiner de manière déterministe les disponibilités dans les réponses de l'agent.
- [ ] **Interface ChatOps (Slack / Google Chat)** : Exporter l'Agent API sous la forme d'un Bot directement accessible en messagerie d'entreprise pour les commerciaux et managers.
- [ ] **Notification Proactives & Actions Push** : Mettre en place un système d'alerte pour les "Skills Gap" dès qu'une opportunité du marché ne trouve plus de correspondance interne.
- [ ] **Génération Automatique de Réponses (RFP Engine)** : Un agent spécialisé capable de générer des réponses techniques ou commerciales aux Appels d'Offres à partir des références passées, des CVs et des expertises de l'équipe disponible.