# agent_hr_api

## Rôle
Sous-agent spécialisé RH : recherche sémantique de consultants, gestion des compétences, analyse de CVs, et matching consultant/mission. Orchestré par `agent_router_api` via A2A.

## Type
🟣 Agent IA (consommateur MCP)

## Fichiers clés
| Fichier | Lignes | État |
|---|---|---|
| `main.py` | 335 | ✅ |
| `conftest.py` | 21 | ✅ |
| `metrics.py` | 19 | ✅ |
| `agent.py` | 330 | ✅ |

## Variables d'environnement
| Var | Type | Valeur dev |
|---|---|---|
| `PYTHON_AR_REPO` | Comportement | `${PYTHON_AR_REPO}` |
| `SHARED_VERSION` | Comportement | `${SHARED_VERSION}` |
| `PATH` | Comportement | `"/app/.venv/bin:$PATH"` |
| `PYTHONPATH` | Comportement | `/app` |
| `GEMINI_MODEL` | Comportement | `gemini-3.1-flash-lite-preview` |
| `GEMINI_HR_MODEL` | Comportement | `gemini-3.1-flash-lite-preview` |
| `ENABLE_OUTPUT_SCHEMA` | Comportement | `false` |
| `PORT` | Infra | `8080` |
| `PYTHONUNBUFFERED` | Comportement | `1` |
| `LOG_LEVEL` | Comportement | `INFO` |
| `TRACE_EXPORTER` | Infra | `grpc` |
| `ROOT_PATH` | Comportement | `/agent-hr-api` |
| `APP_VERSION` | Comportement | `dev` |
| `SERVICE_NAME` | Comportement | `agent-hr` |
| `USERS_API_URL` | Infra | `http://users_api:8000` |
| `ITEMS_API_URL` | Infra | `http://items_api:8001` |
| `COMPETENCIES_API_URL` | Infra | `http://competencies_api:8003` |
| `CV_API_URL` | Infra | `http://cv_api:8004` |
| `MISSIONS_API_URL` | Infra | `http://missions_api:8009` |
| `PROMPTS_API_URL` | Infra | `http://prompts_api:8000` |
| `ANALYTICS_MCP_URL` | Infra | `http://analytics_mcp:8080` |
| `MONITORING_MCP_URL` | Infra | `http://monitoring_mcp:8010` |
| `USERS_MCP_URL` | Infra | `http://users_mcp:8000` |
| `ITEMS_MCP_URL` | Infra | `http://items_mcp:8000` |
| `COMPETENCIES_MCP_URL` | Infra | `http://competencies_mcp:8000` |
| `CV_MCP_URL` | Infra | `http://cv_mcp:8000` |
| `MISSIONS_MCP_URL` | Infra | `http://missions_mcp:8000` |
| `DRIVE_MCP_URL` | Infra | `http://drive_api:8080` |

## Redis
**DB 10** — namespace `session:hr:*` (historique de session par user)

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

## MCP APIs consommées
- `ANALYTICS_MCP_URL`
- `COMPETENCIES_API_URL`
- `COMPETENCIES_MCP_URL`
- `CV_API_URL`
- `CV_MCP_URL`
- `DRIVE_MCP_URL`
- `ITEMS_API_URL`
- `ITEMS_MCP_URL`
- `MISSIONS_API_URL`
- `MISSIONS_MCP_URL`
- `USERS_API_URL`
- `USERS_MCP_URL`

## Gotchas connus
- Le pool de candidats en session (`session_candidates`) est stocké en Redis par user — il survit entre les tours de conversation pour éviter les re-searches RAG redondantes
- Expertise score threshold : ne proposer que des consultants avec score > 0.6 (règle system prompt)
- `main.py` approche la zone bloquante — surveiller lors des prochaines features
- `log_ai_consumption` DOIT être appelé avec `service="agent_hr_api"` pour le tracking FinOps

## Dernière modification
2026-04-28 — v0.0.85 — fix JWT propagation + session candidate pool
