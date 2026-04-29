# Spécifications de l'API CV & RAG (Retrieval-Augmented Generation)

L'API CV est un service asynchrone hybride couplant PostgreSQL (avec son extension `pgvector`) et l'Intelligence Artificielle Google Gemini. Son objectif est d'ingérer des blocs sémantiques isolés (Curriculum Vitae Google Doc), d'en déterminer le modèle en graphe et d'opérer simultanément sur les nœuds inter-services distants (`users_api` et `competencies_api`).

## Philosophie d'Architecture
- **Microservice Autonome** : Rattaché aux bases via `postgres_data` au sein du namespace Docker Compose.
- **Délégation Asynchrone (Agent MCP)** : Embarque son propre Sidecar (`cv_mcp:8000`) autorisant les prompts contextuels par l'Agentic Dashboard (Recherche conversationnelle de candidats).
- **RAG Capability (Embeddings 3072-D)** : Traduction du contenu texte via LLM `gemini-embedding-001` persistée en index optimisé.

## Description Fonctionnelle Détaillée
L'API CV agit en tant que moteur de traitement du langage naturel et d'extraction de connaissances. Elle permet aux recruteurs et aux managers de Zenika d'automatiser l'analyse des profils candidats ou collaborateurs.
Lorsqu'un Curriculum Vitae est soumis sous forme de lien Google Doc, le service télécharge son contenu, utilise les modèles LLM de Gemini pour en extraire l'essence (expériences, technologies maîtrisées, soft skills), puis transforme ces données non-structurées en vecteurs de connaissances (RAG).
Ces métadonnées sont alors croisées avec le référentiel d'entreprise (via `competencies_api`) pour mettre à jour ou suggérer automatiquement les compétences d'un profil (via `users_api`). Ce service décharge l'humain des tâches de saisie manuelle et offre une capacité de recherche sémantique profonde (ex: "Trouve-moi quelqu'un ayant travaillé 5 ans sur React dans le secteur bancaire").

## Modèles Techniques - SQL Alchemy
- `id` (PK)
- `user_id` (Integer) -> Clé Etrangère logique interservice pointant sur `Users`
- `source_url` (String) -> URI Doc
- `raw_content` (Text) -> Buffer Extrait
- `semantic_embedding` (Vector(3072)) -> RAG Indexing

## Endpoints Exposés

### 1. Ingestion Documentaire `POST /cvs/import`
Extrait, analyse, parse, connecte et vectorise un Profil de façon synchrone.
**Exigences de Sécurité :** Un jeton JWT doit impérativement transiter en header `Authorization`

`Payload attendu`
```json
{
  "url": "https://docs.google.com/document/d/DOC_ID/edit"
}
```

`Réponse`
```json
{
  "message": "Success! Processed 'Nom' and mapped N RAG competencies.",
  "user_id": 12,
  "competencies_assigned": 4
}
```

## Observabilité Intrinsèque
- Root Tracing propagé inter-services (Opentelemetry interceptors `httpx`).
- Route Prometheus `/metrics` sur `8004`.

## 🔒 Sécurité Zero-Trust & JWT
L'intégralité des routes (hors santé et documentation OpenAPI) exigent dorénavant un JWT d'authentification vérifié. Le token doit être passé dans l'entête HTTP (`Authorization: Bearer <token>`). Tous les composants internes et externes propagent l'identité du requérant.

## 📡 Schema OpenAPI Auto-Généré

- **GET** `/metrics` : Metrics
- **GET** `/health` : Health
- **GET** `/ready` : Ready
- **GET** `/version` : Get Version
- **GET** `/spec` : Get Spec
- **POST** `/pubsub/import-cv` : Handle Pubsub Cv Import
- **POST** `/pubsub/user-events` : Handle User Pubsub Events
- **POST** `/cache/invalidate-taxonomy` : Force Invalidate Taxonomy Cache
- **POST** `/import` : Import And Analyze Cv
- **GET** `/search` : Search Candidates
- **POST** `/search` : Search Candidates Post
- **GET** `/user/{user_id}` : Get User Cv
- **GET** `/users/tags/map` : Get All User Tags
- **GET** `/users/tag/{tag}` : Get Users By Tag
- **GET** `/user/{user_id}/missions` : Get User Missions
- **GET** `/user/{user_id}/details` : Get User Cv Details
- **GET** `/ranking/experience` : Get Consultants Experience Ranking
- **POST** `/recalculate_tree/step` : Recalculate Competencies Tree Step
- **POST** `/recalculate_tree` : Recalculate Competencies Tree
- **GET** `/recalculate_tree/status` : Get Recalculate Tree Status
- **POST** `/reindex-embeddings` : Reindex Embeddings
- **GET** `/user/{user_id}/similar` : Find Similar Consultants
- **POST** `/search/multi-criteria` : Search Candidates Multi Criteria
- **GET** `/user/{user_id}/rag-snippet` : Get Rag Snippet
- **GET** `/reanalyze/status` : Get Reanalyze Status
- **POST** `/search/mission-match` : Match Mission To Candidates
- **GET** `/analytics/skills-coverage` : Get Skills Coverage
- **POST** `/reanalyze` : Reanalyze Cvs
- **POST** `/internal/users/merge` : Merge Users
- **POST** `/recalculate_tree/batch/start` : Lance le processus batch asynchrone (Map)
- **POST** `/recalculate_tree/batch/check` : Vérifie l'état du batch et avance la machine à états
- **GET** `/recalculate_tree/batch/list` : Liste l'historique des jobs batch de taxonomie
- **DELETE** `/recalculate_tree/batch/{job_id}` : Supprime un job batch GCP de l'historique
- **POST** `/recalculate_tree/cancel` : Annule le traitement interactif en cours
- **POST** `/recalculate_tree/batch/cancel` : Annule le batch en cours
- **POST** `/recalculate_tree/batch/recover` : Tente de récupérer un batch bloqué en erreur
- **POST** `/recalculate_tree/batch/reset` : Réinitialise forcé l'état Redis du batch (déblocage d'urgence)
- **POST** `/bulk-reanalyse/start` : Start Bulk Reanalyse
- **GET** `/bulk-reanalyse/status` : Get Bulk Reanalyse Status
- **POST** `/bulk-reanalyse/cancel` : Cancel Bulk Reanalyse
- **POST** `/bulk-reanalyse/reset` : Reset Bulk Reanalyse
- **GET** `/bulk-reanalyse/data-quality` : Get Data Quality Report
- **POST** `/bulk-reanalyse/retry-apply` : Retry Bulk Apply
- **POST** `/mcp/{path}` : Proxy Mcp
- **DELETE** `/mcp/{path}` : Proxy Mcp
- **GET** `/mcp/{path}` : Proxy Mcp
- **PUT** `/mcp/{path}` : Proxy Mcp
