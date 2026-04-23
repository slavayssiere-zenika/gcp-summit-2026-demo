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
- **POST** `/mcp/{path}` : Proxy Mcp
- **GET** `/mcp/{path}` : Proxy Mcp
- **DELETE** `/mcp/{path}` : Proxy Mcp
- **PUT** `/mcp/{path}` : Proxy Mcp
- **GET** `/spec` : Get Spec
- **GET** `/health` : Health
- **GET** `/version` : Get Version
- **GET** `/folders` : List Folders
- **POST** `/folders` : Add Folder
- **POST** `/folders/reset-sync` : Reset Folder Sync
- **DELETE** `/folders/{folder_id}` : Delete Folder
- **GET** `/status` : Get Status
- **GET** `/files` : List Files
- **GET** `/files/{google_file_id}` : Get File State
- **POST** `/retry-errors` : Retry Errors
- **GET** `/tokens/google` : Get Google Token
- **GET** `/dlq/status` : Get Dlq Status
- **DELETE** `/dlq/message` : Delete Dlq Message
- **POST** `/dlq/replay` : Replay Dlq
- **PATCH** `/files/{file_id}` : Update File
- **POST** `/scheduled/retry-errors` : Scheduled Retry Errors
- **POST** `/sync` : Trigger Sync
