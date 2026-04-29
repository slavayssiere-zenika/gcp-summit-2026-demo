# agent_missions_api

## Rôle
Sous-agent spécialisé gestion documentaire des missions : analyse, résumé et extraction d'informations depuis les documents de mission (PDF, DOCX). Orchestré par `agent_router_api` via A2A.

## Type
🟣 Agent IA (consommateur MCP)

## Fichiers clés
| Fichier | Lignes | État |
|---|---|---|
| `main.py` | 424 | ⚠️ Zone alerte |
| `test_guardrail.py` | 357 | ⚠️ Zone alerte |
| `agent.py` | 195 | ✅ OK |
| `mcp_client.py` | 175 | ✅ OK |
| `session.py` | ~150 | ✅ OK |
| `metadata.py` | ~80 | ✅ OK |

## Variables d'environnement
| Var | Type | Valeur dev |
|---|---|---|
| `SECRET_KEY` | Secret | via secret_key_ref (cr_agent_missions.tf) |
| `REDIS_URL` | Infra | `redis://redis:6379/12` |
| `GEMINI_MODEL` | Comportement | `gemini-2.5-flash` |
| `ROOT_PATH` | Comportement | `/agent-missions-api` |
| `MISSIONS_API_URL` | Infra | URL de `missions_api` |
| `ANALYTICS_MCP_URL` | Infra | URL de `analytics_mcp` |

## Redis
**DB 12** — namespace `session:missions:*`

## Endpoints clés
- `POST /a2a/query` — point d'entrée A2A depuis `agent_router_api`
- `GET /health`, `GET /metrics`, `GET /version`

## MCP APIs consommées
- `missions_api` : `list_missions`, `get_mission_by_id`, `search_missions_semantic`
- `analytics_mcp` : `log_ai_consumption` (OBLIGATOIRE)

## Gotchas connus
- `main.py` approche la zone bloquante — surveiller lors des prochaines features
- `SECRET_KEY` est injecté via `secret_key_ref` dans Terraform (pas de valeur dans le Dockerfile)

## Dernière modification
2026-04-28 — v0.1.28 — stable
