# 🚀 Zenika Console : Plateforme de Staffing & Intelligence Collaborative

Bienvenue sur la **Zenika Console**, une architecture micro-services de pointe conçue pour moderniser la gestion des talents, du staffing et de l'expertise technique. Ce projet combine la puissance de l'IA générative (**Google Gemini**) avec une infrastructure cloud robuste et hautement observable.

---

## 🎯 Vue d'Ensemble Fonctionnelle

La Zenika Console n'est pas qu'un simple annuaire de collaborateurs ; c'est un écosystème intelligent qui transforme les données brutes (CVs, missions, compétences) en connaissances actionnables pour les commerciaux, managers et RH.

### 1. Consultant 360 & CV-RAG
Le système automatise l'ingestion des profils via un pipeline de **CV-RAG (Retrieval-Augmented Generation)**. 
- **Parsing Intelligent** : Importation de CVs depuis Google Drive. L'IA Gemini extrait automatiquement le résumé, le rôle actuel, l'expérience, les compétences clés et le détail des missions.
- **Normalisation Sémantique** : Les compétences extraites sont automatiquement mappées sur le référentiel d'entreprise, gérant les synonymes et les aliases technologiques.
- **Anonymisation Heuristique** : Détection automatique des profils anonymes ou provisoires pour garantir la confidentialité des données sensibles tout en permettant le staffing.

### 2. Staffing Copilot (IA Agentique)
Un agent conversationnel intégré permet de naviguer dans l'écosystème via le langage naturel :
- **Recherche Look-alike** : "Trouve-moi un profil semblable à Thomas pour cette mission."
- **Matching de Projet** : Soumettez une fiche de poste, et l'agent calculera le "centre de gravité" vectoriel pour identifier les consultants les plus pertinents.
- **Analyse de Gap** : Identifier les expertises manquantes au sein d'une agence par rapport aux tendances du marché actuel.

### 3. Gestion de la Taxonomie
Une hiérarchie de compétences dynamique (Catégories > Spécialités > Compétences) qui évolue avec l'entreprise. L'IA peut recalculer l'arbre complet en fonction des profils réels en base pour suggérer de nouvelles spécialités émergentes.

### 4. Centre d'Administration & Hygiène de Données
- **Fusion de Profils (Merge)** : Outil de résolution de doublons propageant les changements d'identité à travers tous les micro-services (CVs, items, compétences) via des événements Pub/Sub.
- **Réanalyse de Masse** : Capacité de relancer le pipeline d'extraction sur l'ensemble de la base après une mise à jour du modèle d'IA pour affiner les rankings.

---

## 🛠 Architecture & Spécifications Techniques

Le projet repose sur une architecture **Micro-services Native** orchestrée par Docker Compose en local et déployée sur Google Cloud Run.

### 1. Écosystème des Micro-services
Le backend est segmenté en services spécialisés (FastAPI) communiquant en REST et via des outils MCP :
- **`agent_api`** : Le cerveau, orchestrant les appels LLM et le Model Context Protocol.
- **`cv_api`** : Gestionnaire de vecteurs (AlloyDB/pgvector) et pipeline de parsing Gemini.
- **`users_api`** : Master Data des collaborateurs et identités sécurisées.
- **`competencies_api`** : Gestionnaire de la taxonomie hiérarchique complexe.
- **`items_api`** : Inventaire des ressources et expériences professionnelles (missions).
- **`drive_api`** : Adaptateur pour la synchronisation avec l'API Google Drive.
- **`prompts_api`** : Centralisation et versionnement des templates de prompts pour Gemini.

### 2. IA Agentique & Model Context Protocol (MCP)
L'interaction entre l'IA et les données métiers ne se fait pas par des requêtes rigides, mais via **MCP**. Chaque micro-service expose un serveur MCP autonome, permettant à l'agent de "découvrir" ses outils (recherche, update, stats) dynamiquement. Cela garantit une extensibilité infinie sans modifier le coeur de l'agent.

### 3. Couche de Données & Événements
- **Stockage** : PostgreSQL (namespaces isolés) avec l'extension `pgvector` pour la recherche sémantique à haute performance.
- **Cache & Queue** : Redis pour le caching des APIs, l'invalidation de patterns et la gestion des sessions utilisateur.
- **Asynchrone** : Propagation des événements critiques (ex: fusion d'utilisateurs) via **Google Pub/Sub** pour garantir l'intégrité éventuelle entre les services distribués.

### 4. Observabilité Stack (LGT)
Le projet implémente le standard de l'industrie pour le monitoring distribué :
- **Tracing (Tempo & OTel)** : Visualisation complète du cycle de vie d'une requête, des outils MCP jusqu'à la base de données.
- **Logging (Loki & Promtail)** : Centralisation des logs applicatifs indexés par service et par trace.
- **Metrics (Prometheus & Grafana)** : Tableaux de bord en temps réel pour la santé des APIs et les performances infra.

---

## 📂 Structure du Projet

Le dépôt est organisé pour supporter une scalabilité horizontale et une séparation claire des responsabilités :

```text
├── agent_api/            # Orchestrateur IA & Client MCP
├── competencies_api/     # Micro-service Référentiel de Compétences
├── cv_api/               # Micro-service Analyse CV & RAG (Vector DB)
├── items_api/            # Micro-service Gestion des Missions & Objets
├── users_api/            # Micro-service Identity Management
├── drive_api/            # Micro-service Sync Google Drive
├── prompts_api/          # Gestionnaire de templates de prompts Gemini
├── frontend/             # Single Page Application (Vue.js 3 / Vite)
├── bootstrap/            # Terraform : Fondations GCP (Réseau, DB)
├── platform-engineering/ # Terraform : Déploiement Cloud Run & IAM
├── db_migrations/        # Centralisation des changelogs Liquibase
├── grafana/              # Dashboards & Config Observabilité
├── scripts/              # Utilitaires de maintenance et de test
└── docker-compose.yml    # Orchestration du développement local
```

---

## 🔍 Focus Technique : Sécurité & Standards

### 1. Sécurité Zero-Trust
L'architecture impose une sécurité stricte sur tout le trafic :
- **JWT Validation** : Chaque service valide la signature du token via une clé secrète partagée.
- **Service Accounts** : Sur GCP, chaque service possède son propre SA avec des droits minimaux.
- **Header Propagation** : Le header `Authorization` est transmis explicitement d'un service à l'autre.

### 2. Cycle de Vie des Données (Liquibase)
Les schémas de base de données sont gérés via Liquibase pour garantir l'idempotence des migrations entre les environnements de dev, de staging et de production.

### 3. Container Contract (Cloud Run)
Tous les conteneurs respectent les normes de production Cloud Run :
- **Non-Root** : Exécution sous un utilisateur non-privilégié `appuser`.
- **Multi-Stage Build** : Images optimisées pour réduire la surface d'attaque.
- **Graceful Shutdown** : Gestion des signaux système pour une fermeture propre.

---

## 🚀 Démarrage Rapide

### Pré-requis
- **Docker** & **Docker Compose** installés.
- **Google API Key** : Indispensable pour les fonctions Gemini.
- **Python 3.12+** pour les scripts de maintenance.

### Installation & Lancement
1. Clonez le dépôt et créez votre fichier `.env` à la racine.
2. Démarrez l'infrastructure complète :
   ```bash
   docker-compose up --build
   ```
3. L'interface Vue.js sera disponible sur `http://localhost:8002`.

### Workflows de Développement
Utilisez le workflow automatisé via l'agent pour garantir la qualité :
```bash
@[/git-push]
```
Ce workflow lance les tests, régénère les specs, met à jour le changelog et formate l'IaC.

---

## 📜 Licence & Crédits
Développé par l'équipe **Zenika Advanced AI Engine**. Ce projet est destiné à démontrer les capacités d'orchestration d'agents intelligents dans un environnement Cloud natif hautement sécurisé et observé.
