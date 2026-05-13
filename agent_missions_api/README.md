# agent_missions_api

## Rôle
Sous-agent spécialisé gestion documentaire des missions : analyse, résumé et extraction d'informations depuis les documents de mission (PDF, DOCX). Orchestré par `agent_router_api` via A2A.

## Type
🟣 Agent IA (consommateur MCP)

## Fichiers clés
| Fichier | Lignes | État |
|---|---|---|
| `main.py` | 389 | ✅ |
| `conftest.py` | 18 | ✅ |
| `metrics.py` | 20 | ✅ |
| `agent.py` | 243 | ✅ |

## Variables d'environnement
| Var | Type | Valeur dev |
|---|---|---|
| `PYTHONPATH` | Comportement | `/app` |
| `PYTHONUNBUFFERED` | Comportement | `1` |
| `PORT` | Infra | `8080` |
| `LOG_LEVEL` | Comportement | `INFO` |
| `TRACE_EXPORTER` | Infra | `none` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Infra | `http://tempo:4318` |
| `OTEL_SERVICE_NAME` | Comportement | `agent-missions-api` |
| `ROOT_PATH` | Comportement | `/agent-missions-api` |
| `APP_VERSION` | Comportement | `dev` |
| `SERVICE_NAME` | Comportement | `agent-missions` |
| `GEMINI_MODEL` | Comportement | `gemini-3.1-flash-lite-preview` |
| `MISSIONS_MCP_URL` | Infra | `http://missions_mcp:8000` |
| `CV_MCP_URL` | Infra | `http://cv_mcp:8000` |
| `USERS_MCP_URL` | Infra | `http://users_mcp:8000` |
| `COMPETENCIES_MCP_URL` | Infra | `http://competencies_mcp:8000` |
| `PROMPTS_API_URL` | Infra | `http://prompts_api:8000` |
| `ANALYTICS_MCP_URL` | Infra | `http://analytics_mcp:8080` |
| `MONITORING_MCP_URL` | Infra | `http://monitoring_mcp:8010` |
| `REDIS_URL` | Infra | `redis://redis:6379/12` |
| `USE_GCP_LOGGING` | Infra | `false` |
| `GCP_PROJECT_ID` | Infra | `local` |

## Redis
**DB 12** — namespace `session:missions:*`

## Endpoints clés
- `GET /version`
- `POST /query`
- `POST /a2a/query`
- `GET /history`
- `DELETE /history`
- `GET /spec`
- `GET /mcp/registry`

## MCP APIs consommées
- `COMPETENCIES_MCP_URL`
- `CV_MCP_URL`
- `MISSIONS_MCP_URL`
- `USERS_MCP_URL`

## Gotchas connus
- `main.py` approche la zone bloquante — surveiller lors des prochaines features
- `SECRET_KEY` est injecté via `secret_key_ref` dans Terraform (pas de valeur dans le Dockerfile)

## Dernière modification
2026-04-28 — v0.1.28 — stable
