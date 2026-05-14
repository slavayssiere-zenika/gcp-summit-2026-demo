# agent_hr_api

## Rôle
Sous-agent spécialisé RH : recherche sémantique de consultants, gestion des compétences, analyse de CVs, et matching consultant/mission. Orchestré par `agent_router_api` via A2A.

## Type
🟣 Agent IA (consommateur MCP)

## Fichiers clés
| Fichier | Lignes | État |
|---|---|---|
| `main.py` | 271 | ✅ |
| `conftest.py` | 22 | ✅ |
| `metrics.py` | 19 | ✅ |
| `agent.py` | 285 | ✅ |

## Variables d'environnement
| Var | Type | Valeur dev |
|---|---|---|
| `PYTHONPATH` | Comportement | `/app` |
| `GEMINI_MODEL` | Comportement | `gemini-3.1-flash-lite-preview` |
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
| `USERS_MCP_URL` | Infra | `http://users_mcp:8000` |
| `ITEMS_MCP_URL` | Infra | `http://items_mcp:8000` |
| `COMPETENCIES_MCP_URL` | Infra | `http://competencies_mcp:8000` |
| `CV_MCP_URL` | Infra | `http://cv_mcp:8000` |
| `MISSIONS_MCP_URL` | Infra | `http://missions_mcp:8000` |
| `DRIVE_MCP_URL` | Infra | `http://drive_api:8080` |
| `LOKI_MCP_URL` | Infra | `http://loki:3100/mcp` |
| `MONITORING_MCP_URL` | Infra | `http://monitoring_mcp:8010` |

## Redis
**DB 10** — namespace `session:hr:*` (historique de session par user)

## Endpoints clés
- `GET /`
- `GET /spec`
- `POST /query`
- `POST /a2a/query`
- `GET /mcp/registry`
- `GET /version`

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
