# prompts_api

## Rôle
Gestion et versioning des system prompts des agents IA. Centralise les instructions LLM, reçoit les rapports d'erreurs 500 de toutes les APIs data, et déclenche l'amélioration continue des prompts via LLM.

## Type
🔵 API data (producteur MCP)

## Fichiers clés
| Fichier | Lignes | État |
|---|---|---|
| `main.py` | 219 | ✅ |
| `mcp_server.py` | 279 | ✅ |
| `conftest.py` | 32 | ✅ |
| `src/prompts/router.py` | 322 | ✅ |

## Variables d'environnement
| Var | Type | Valeur dev |
|---|---|---|
| `NPM_CONFIG_PREFIX` | Comportement | `/opt/promptfoo-env` |
| `PATH` | Comportement | `"/opt/promptfoo-env/bin:${PATH}"` |
| `PYTHONPATH` | Comportement | `/app` |
| `PORT` | Infra | `8000` |
| `PYTHONUNBUFFERED` | Comportement | `1` |
| `LOG_LEVEL` | Comportement | `INFO` |
| `TRACE_EXPORTER` | Infra | `grpc` |
| `ROOT_PATH` | Comportement | `/prompts-api` |
| `APP_VERSION` | Comportement | `dev` |
| `SERVICE_NAME` | Comportement | `prompts-api` |
| `USE_IAM_AUTH` | Comportement | `false` |

## Redis
**DB 5** — namespace `prompts:*`

## Endpoints clés
- `GET /user/me`
- `PUT /user/me`
- `GET /`
- `GET /{key}`
- `PUT /{key}`
- `POST /`
- `POST /{key}/analyze`
- `POST /errors/report`
- `GET /{key}/compiled`
- `DELETE /{key}`
- `GET /version`
- `GET /spec`
- `GET /mcp/tools`
- `POST /mcp/call`
- `GET /users/`
- `GET /items/`
- `PUT /items/{item_id}`
- `POST /items/`
- `DELETE /items/{item_id}`
- `PATCH /items/`

## MCP tools exposés
- `analyze_prompt`, `create_prompt`, `get_my_prompt`, `get_prompt`, `health_check_prompts`, `list_prompts`, `report_service_error_for_prompt`, `update_my_prompt`, `update_prompt`

## Gotchas connus
- `GET /prompts/by-name/{name}` retourne `""` (string vide) si le prompt n'existe pas — les services appelants DOIVENT vérifier la réponse avant de l'utiliser comme instruction LLM
- Ce service reçoit les rapports d'erreurs asynchrones (`POST /errors/report`) de toutes les APIs data via `@app.exception_handler(Exception)` — il ne doit JAMAIS être down sans fallback
- Pas de `mcp_server.py` sidecar ? À vérifier lors de la prochaine intervention

## Dernière modification
2026-04-29 — v0.0.49 — fix prompt fetch URL dans cv_api
