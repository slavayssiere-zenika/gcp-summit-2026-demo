# Spécifications de l'API CV & RAG (Retrieval-Augmented Generation)

L'API CV est un service asynchrone hybride couplant PostgreSQL (avec son extension `pgvector`) et l'Intelligence Artificielle Google Gemini. Son objectif est d'ingérer des blocs sémantiques isolés (Curriculum Vitae Google Doc), d'en déterminer le modèle en graphe et d'opérer simultanément sur les nœuds inter-services distants (`users_api` et `competencies_api`).

## Philosophie d'Architecture
- **Microservice Autonome** : Rattaché aux bases via `postgres_data` au sein du namespace Docker Compose.
- **Délégation Asynchrone (Agent MCP)** : Embarque son propre Sidecar (`cv_mcp:8000`) autorisant les prompts contextuels par l'Agentic Dashboard (Recherche conversationnelle de candidats).
- **RAG Capability (Embeddings 3072-D)** : Traduction du contenu texte via LLM `gemini-embedding-001` persistée en index optimisé.

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
