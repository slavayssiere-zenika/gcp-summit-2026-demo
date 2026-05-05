# missions_api

## Rôle
Gestion des missions client (appels d'offre, documents), analyse multimodale des documents de mission via Gemini, et stockage vectoriel pour le matching consultant/mission.

## Type
🔵 API data (producteur MCP)

## Fichiers clés
| Fichier | Lignes | État |
|---|---|---|
| `main.py` | 212 | ✅ |
| `mcp_server.py` | 328 | ✅ |
| `conftest.py` | 39 | ✅ |
| `metrics.py` | 3 | ✅ |
| `src/missions/analysis_router.py` | 196 | ✅ |
| `src/missions/crud_router.py` | 176 | ✅ |
| `src/missions/router.py` | 16 | ✅ |
| `src/missions/user_router.py` | 44 | ✅ |

## Variables d'environnement
| Var | Type | Valeur dev |
|---|---|---|
| `PYTHONPATH` | Comportement | `/app` |
| `GEMINI_MODEL` | Comportement | `gemini-2.5-flash` |
| `GEMINI_EMBEDDING_MODEL` | Comportement | `gemini-embedding-001` |
| `PORT` | Infra | `8009` |
| `MCP_SIDECAR_URL` | Infra | `http://missions_mcp:8000` |
| `PYTHONUNBUFFERED` | Comportement | `1` |
| `LOG_LEVEL` | Comportement | `INFO` |
| `TRACE_EXPORTER` | Infra | `grpc` |
| `ROOT_PATH` | Comportement | `/missions-api` |
| `APP_VERSION` | Comportement | `dev` |
| `SERVICE_NAME` | Comportement | `missions-api` |
| `USE_IAM_AUTH` | Comportement | `false` |
| `USERS_API_URL` | Infra | `http://users_api:8000` |
| `CV_API_URL` | Infra | `http://cv_api:8004` |
| `COMPETENCIES_API_URL` | Infra | `http://competencies_api:8003` |
| `ITEMS_API_URL` | Infra | `http://items_api:8001` |
| `PROMPTS_API_URL` | Infra | `http://prompts_api:8000` |

## Redis
**DB 8** — namespace `missions:*`

## Endpoints clés
- `POST /missions`
- `POST /missions/{mission_id}/reanalyze`
- `GET /missions/task/{task_id}`
- `POST /cache/invalidate`
- `GET /missions/{mission_id}/embedding`
- `GET /missions`
- `PATCH /missions/{mission_id}/status`
- `GET /missions/{mission_id}/status/history`
- `GET /missions/{mission_id}`
- `DELETE /missions`
- `DELETE /missions/{mission_id}`
- `GET /missions/user/{user_id}/active`
- `GET /version`
- `GET /spec`
- `GET /mcp/tools`
- `POST /mcp/call`

## MCP tools exposés
- `create_mission`, `delete_all_missions`, `get_mission`, `get_mission_candidates`, `get_mission_status_history`, `get_mission_task_status`, `get_user_active_missions`, `list_missions`, `reanalyze_mission`, `update_mission_status`

## Gotchas connus
- **MIME type DOCX** : `application/vnd.openxmlformats-officedocument.wordprocessingml.document` n'est pas supporté par Vertex AI — conversion PDF obligatoire avant envoi au LLM
- `router.py` est en zone bloquante : toute nouvelle feature DOIT passer par un `services/` layer
- La sanity check a un timeout de 90s (latence AlloyDB IAM + cold start Cloud Run)

## Dernière modification
2026-04-29 — v0.0.69 — fix DOCX upload + timeout sanity check
