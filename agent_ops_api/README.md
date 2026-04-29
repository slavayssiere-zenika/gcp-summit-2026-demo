# agent_ops_api

## Rôle
Sous-agent spécialisé Ops : gestion des missions, items, catalogue de services, et requêtes opérationnelles. Orchestré par `agent_router_api` via A2A.

## Type
🟣 Agent IA (consommateur MCP)

## Fichiers clés
| Fichier | Lignes | État |
|---|---|---|
| `main.py` | 542 | ⚠️ Zone alerte |
| `test_guardrail.py` | 312 | ⚠️ Zone alerte |
| `mcp_client.py` | 205 | ✅ OK |
| `agent.py` | 202 | ✅ OK |
| `session.py` | ~150 | ✅ OK |
| `metadata.py` | ~80 | ✅ OK |
| `metrics.py` | ~50 | ✅ OK |

## Variables d'environnement
| Var | Type | Valeur dev |
|---|---|---|
| `SECRET_KEY` | Secret | via `.env` |
| `REDIS_URL` | Infra | `redis://redis:6379/11` |
| `GEMINI_MODEL` | Comportement | `gemini-2.5-flash` |
| `ROOT_PATH` | Comportement | `/agent-ops-api` |
| `MISSIONS_API_URL` | Infra | URL de `missions_api` |
| `ITEMS_API_URL` | Infra | URL de `items_api` |
| `ANALYTICS_MCP_URL` | Infra | URL de `analytics_mcp` |

## Redis
**DB 11** — namespace `session:ops:*`

## Endpoints clés
- `POST /a2a/query` — point d'entrée A2A depuis `agent_router_api`
- `GET /health`, `GET /metrics`, `GET /version`

## MCP APIs consommées
- `missions_api` : `list_missions`, `get_mission_by_id`, `search_missions_semantic`
- `items_api` : `list_items`, `get_item_by_id`
- `analytics_mcp` : `log_ai_consumption` (OBLIGATOIRE)

## Gotchas connus
- `main.py` approche la zone bloquante — surveiller lors des prochaines features
- Toutes les réponses A2A doivent inclure le flag `degraded: True` si une API aval est indisponible

## Dernière modification
2026-04-27 — v0.0.52 — stable
