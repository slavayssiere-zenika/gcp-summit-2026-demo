# agent_hr_api

## Rôle
Sous-agent spécialisé RH : recherche sémantique de consultants, gestion des compétences, analyse de CVs, et matching consultant/mission. Orchestré par `agent_router_api` via A2A.

## Type
🟣 Agent IA (consommateur MCP)

## Fichiers clés
| Fichier | Lignes | État |
|---|---|---|
| `main.py` | 536 | ⚠️ Zone alerte |
| `test_guardrail.py` | 282 | ✅ OK |
| `agent.py` | 270 | ✅ OK |
| `mcp_client.py` | 205 | ✅ OK |
| `session.py` | ~150 | ✅ OK |
| `metadata.py` | ~80 | ✅ OK |
| `metrics.py` | ~50 | ✅ OK |

## Variables d'environnement
| Var | Type | Valeur dev |
|---|---|---|
| `SECRET_KEY` | Secret | via `.env` |
| `REDIS_URL` | Infra | `redis://redis:6379/10` |
| `GEMINI_MODEL` | Comportement | `gemini-2.5-flash` |
| `ROOT_PATH` | Comportement | `/agent-hr-api` |
| `CV_API_URL` | Infra | URL de `cv_api` |
| `COMPETENCIES_API_URL` | Infra | URL de `competencies_api` |
| `USERS_API_URL` | Infra | URL de `users_api` |
| `ANALYTICS_MCP_URL` | Infra | URL de `analytics_mcp` |

## Redis
**DB 10** — namespace `session:hr:*` (historique de session par user)

## Endpoints clés
- `POST /a2a/query` — point d'entrée A2A depuis `agent_router_api`
- `GET /health`, `GET /metrics`, `GET /version`

## MCP APIs consommées
- `cv_api` : `search_cvs_semantic`, `get_cv_profile`, `list_cvs`
- `competencies_api` : `get_competency_tree`, `list_evaluations`
- `users_api` : `list_users`, `get_user_by_id`
- `analytics_mcp` : `log_ai_consumption` (OBLIGATOIRE après chaque inférence)

## Gotchas connus
- Le pool de candidats en session (`session_candidates`) est stocké en Redis par user — il survit entre les tours de conversation pour éviter les re-searches RAG redondantes
- Expertise score threshold : ne proposer que des consultants avec score > 0.6 (règle system prompt)
- `main.py` approche la zone bloquante — surveiller lors des prochaines features
- `log_ai_consumption` DOIT être appelé avec `service="agent_hr_api"` pour le tracking FinOps

## Dernière modification
2026-04-28 — v0.0.85 — fix JWT propagation + session candidate pool
