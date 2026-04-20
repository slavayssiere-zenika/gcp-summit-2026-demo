# Spécifications Missions API

Le service `missions_api` est le cœur de la mise en correspondance d'affaires (Staffing IA).
Il ingère des fiches de missions ou des demandes de staffing formelles, les consolide grâce aux capacités sémantiques de Gemini, puis propose une équipe sur-mesure (DP, Tech Lead, Consultants).

## Architecture

Ce micro-service se base sur :
- **PostgreSQL / pgvector** (Stockage vectoriel des embeddings des descriptions de mission).
- **Gemini + RAG** (Extraction des compétences implicites et heuristiques de proposition d'équipe).
- **OpenTelemetry & FinOps** (Tracing de l'orchestration croisée des services et remontée des coûts de token IA).

## Intégrations
- Interroge `cv_api` (`/search`) pour identifier les top-candidats.
- Interroge `users_api` (`/users/{id}`) pour récupérer les disponibilités à date.
- Loggue la consommation sur `market_mcp` par le biais des appels asynchrones internes.

## Modèles

### `MissionCreateRequest`
```json
{
  "title": "Chef de projet Data",
  "description": "Nous cherchons quelqu'un pour piloter notre migration Snowflake..."
}
```

### `MissionAnalyzeResponse`
```json
{
  "id": 1,
  "title": "Chef de projet Data",
  "description": "...",
  "extracted_competencies": ["Snowflake", "Management", "Agile"],
  "proposed_team": [
    {
      "user_id": 14,
      "full_name": "Sébastien Lavayssière",
      "role": "Directeur de Projet",
      "justification": "Expert Snowflake et entièrement disponible le mois courant.",
      "estimated_days": 18
    }
  ]
}
```

## 📡 Schema OpenAPI Auto-Généré

- **GET** `/metrics` : Metrics
- **GET** `/health` : Health
- **GET** `/version` : Get Version
- **POST** `/missions` : Create And Analyze Mission
- **GET** `/missions` : List Missions
- **POST** `/missions/{mission_id}/reanalyze` : Reanalyze Mission
- **GET** `/missions/task/{task_id}` : Get Mission Task Status
- **POST** `/cache/invalidate` : Force Invalidate
- **PATCH** `/missions/{mission_id}/status` : Update Mission Status
- **GET** `/missions/{mission_id}/status/history` : Get Mission Status History
- **GET** `/missions/user/{user_id}/active` : Get Active Missions For User
- **GET** `/missions/{mission_id}` : Get Mission
- **DELETE** `/mcp/{path}` : Proxy Mcp
- **GET** `/mcp/{path}` : Proxy Mcp
- **POST** `/mcp/{path}` : Proxy Mcp
- **PUT** `/mcp/{path}` : Proxy Mcp
- **GET** `/spec` : Get Spec
