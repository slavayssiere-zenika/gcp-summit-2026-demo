# agent_router_api

## Rôle
Routeur intelligent : point d'entrée unique du frontend, gestion des sessions ADK, cache sémantique Redis, et délégation aux sous-agents HR/Ops/Missions via le protocole A2A (HTTP).

## Type
🟣 Agent IA (consommateur MCP)

## Fichiers clés
| Fichier | Lignes | État |
|---|---|---|
| `main.py` | 225 | ✅ |
| `conftest.py` | 20 | ✅ |
| `metrics.py` | 45 | ✅ |
| `agent.py` | 390 | ✅ |

## Variables d'environnement
| Var | Type | Valeur dev |
|---|---|---|
| `PYTHON_AR_REPO` | Comportement | `${PYTHON_AR_REPO}` |
| `SHARED_VERSION` | Comportement | `${SHARED_VERSION}` |
| `PATH` | Comportement | `"/app/.venv/bin:$PATH"` |
| `PYTHONPATH` | Comportement | `/app` |
| `GEMINI_MODEL` | Comportement | `gemini-3.1-flash-lite-preview` |
| `GEMINI_ROUTER_MODEL` | Comportement | `gemini-3.5-flash` |
| `GEMINI_HR_MODEL` | Comportement | `gemini-3.1-flash-lite-preview` |
| `GEMINI_OPS_MODEL` | Comportement | `gemini-3.1-flash-lite-preview` |
| `PORT` | Infra | `8080` |
| `PYTHONUNBUFFERED` | Comportement | `1` |
| `LOG_LEVEL` | Comportement | `INFO` |
| `TRACE_EXPORTER` | Infra | `grpc` |
| `ROOT_PATH` | Comportement | `/api` |
| `APP_VERSION` | Comportement | `dev` |
| `SERVICE_NAME` | Comportement | `agent-router` |
| `USERS_API_URL` | Infra | `http://users_api:8000` |
| `AGENT_HR_API_URL` | Infra | `http://agent_hr_api:8080` |
| `AGENT_OPS_API_URL` | Infra | `http://agent_ops_api:8080` |
| `AGENT_MISSIONS_API_URL` | Infra | `http://agent_missions_api:8080` |
| `PROMPTS_API_URL` | Infra | `http://prompts_api:8000` |
| `ANALYTICS_MCP_URL` | Infra | `http://analytics_mcp:8080` |
| `MONITORING_MCP_URL` | Infra | `http://monitoring_mcp:8010` |
| `REDIS_URL` | Infra | `redis://redis:6379/2` |
| `SEMANTIC_CACHE_ENABLED` | Comportement | `true` |
| `SEMANTIC_CACHE_THRESHOLD` | Comportement | `0.95` |
| `SEMANTIC_CACHE_TTL` | Comportement | `900` |
| `GEMINI_EMBEDDING_MODEL` | Comportement | `gemini-embedding-001` |
| `A2A_CB_FAILURE_THRESHOLD` | Comportement | `5` |
| `A2A_CB_OPEN_DURATION_S` | Comportement | `30` |
| `AGENT_CARD_CACHE_TTL_S` | Comportement | `300` |
| `PROMPT_CACHE_TTL_S` | Comportement | `3600` |

## Redis
**DB 2** — namespace `session:*` (historique) + `semantic:*` (cache sémantique)

## Endpoints clés
- `POST /a2a/query`
- `GET /users/`
- `GET /items/`
- `PUT /items/{item_id}`
- `POST /items/`
- `DELETE /items/{item_id}`
- `PATCH /items/`
- `POST /send-notification/{email}`
- `POST /files/`
- `POST /uploadfile/`
- `GET /items/{item_id}`
- `GET /users/me/items/`
- `GET /users/me`
- `POST /login`
- `GET /version`
- `GET /list-apps`
- `GET /apps/{app_name}/app-info`
- `GET /debug/trace/{event_id}`
- `GET /dev/build_graph/{app_name}`
- `GET /debug/trace/session/{session_id}`

## Sous-agents consommés (A2A)
- `agent_hr_api` — RH, CVs, compétences
- `agent_ops_api` — missions, items, opérationnel
- `agent_missions_api` — gestion documentaire missions

## Cache sémantique
- `SemanticCache` dans `semantic_cache.py` : index HNSW Redis
- **Attention** : Redis Memorystore GCP ne supporte pas les types TEXT pour les index vectoriels — utiliser TAG
- Reset automatique si le context window déborde (INVALID_ARGUMENT 400)

## Gotchas connus
- **`main.py` en zone bloquante (808L)** — ne pas ajouter de logique métier directement
- Le cache sémantique HNSW nécessite un index Redis de type TAG (pas TEXT) pour la compatibilité GCP Memorystore
- Les appels A2A vers les sous-agents doivent tous utiliser le pattern httpx timeout/retry standard (30s, 3 retries, backoff exponentiel)
- Les erreurs non-critiques (FinOps, monitoring) doivent être en mode dégradé (`asyncio.create_task`) pour ne pas bloquer la réponse

## Dernière modification
2026-04-28 — v0.1.23 — fix SemanticCache HNSW TAG + session reset overflow
