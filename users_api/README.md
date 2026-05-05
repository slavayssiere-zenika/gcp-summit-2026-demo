# users_api

## Rôle
Gestion des utilisateurs, authentification JWT, et émission de tokens de service pour les background tasks.

## Type
🔵 API data (producteur MCP)

## Fichiers clés
| Fichier | Lignes | État |
|---|---|---|
| `main.py` | 274 | ✅ |
| `mcp_server.py` | 94 | ✅ |
| `conftest.py` | 72 | ✅ |
| `metrics.py` | 4 | ✅ |
| `src/users/auth_router.py` | 275 | ✅ |
| `src/users/crud_router.py` | 269 | ✅ |
| `src/users/router.py` | 10 | ✅ |
| `src/users/system_router.py` | 131 | ✅ |

## Variables d'environnement
| Var | Type | Valeur dev |
|---|---|---|
| `PYTHONPATH` | Comportement | `/app` |
| `PORT` | Infra | `8000` |
| `MCP_SIDECAR_URL` | Infra | `http://users_mcp:8000` |
| `PYTHONUNBUFFERED` | Comportement | `1` |
| `LOG_LEVEL` | Comportement | `INFO` |
| `TRACE_EXPORTER` | Infra | `grpc` |
| `ROOT_PATH` | Comportement | `/users-api` |
| `APP_VERSION` | Comportement | `dev` |
| `SERVICE_NAME` | Comportement | `users-api` |
| `USE_IAM_AUTH` | Comportement | `false` |
| `CORS_ORIGINS` | Comportement | `http://localhost:5173,http://localhost:80,http://localhost:8080` |
| `FRONTEND_URL` | Infra | `http://localhost:5173` |
| `SERVICE_TOKEN_TTL_MINUTES` | Secret | `90` |

## Redis
**DB 0** — namespace `users:*`

## Endpoints clés
- `GET /`
- `GET /search`
- `POST /bulk`
- `GET /me`
- `GET /{user_id}`
- `POST /`
- `PUT /{user_id}`
- `DELETE /{user_id}`
- `GET /stats`
- `GET /duplicates`
- `POST /merge`
- `GET /version`
- `GET /spec`
- `GET /mcp/tools`
- `POST /mcp/call`

## MCP tools exposés
_Aucun tool MCP détecté dans `mcp_server.py`._

## Gotchas connus
- Les routes statiques (`/spec`, `/health`) doivent être enregistrées **avant** les routes wildcard `/{id}` (sinon 422 int_parsing sur `"spec"`)
- `POST /auth/internal/service-token` est le **seul** mécanisme autorisé pour les tokens de background task — ne jamais utiliser le compte admin

## Dernière modification
2026-04-29 — Audit sécurité RBAC + renforcement verify_jwt
