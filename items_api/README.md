# items_api

## Rôle
Gestion des items (catalogue de services/produits) et de leurs catégories.

## Type
🔵 API data (producteur MCP)

## Fichiers clés
| Fichier | Lignes | État |
|---|---|---|
| `main.py` | 121 | ✅ |
| `mcp_server.py` | 71 | ✅ |
| `conftest.py` | 79 | ✅ |
| `src/items/admin_router.py` | 125 | ✅ |
| `src/items/crud_router.py` | 464 | ✅ |
| `src/items/router.py` | 26 | ✅ |
| `src/items/routers/categories_router.py` | 61 | ✅ |
| `src/items/routers/search_router.py` | 186 | ✅ |

## Variables d'environnement
| Var | Type | Valeur dev |
|---|---|---|
| `PYTHON_AR_REPO` | Comportement | `${PYTHON_AR_REPO}` |
| `SHARED_VERSION` | Comportement | `${SHARED_VERSION}` |
| `PATH` | Comportement | `"/app/.venv/bin:$PATH"` |
| `PYTHONPATH` | Comportement | `/app` |
| `PORT` | Infra | `8001` |
| `MCP_SIDECAR_URL` | Infra | `http://items_mcp:8000` |
| `PYTHONUNBUFFERED` | Comportement | `1` |
| `LOG_LEVEL` | Comportement | `INFO` |
| `TRACE_EXPORTER` | Infra | `grpc` |
| `ROOT_PATH` | Comportement | `/items-api` |
| `APP_VERSION` | Comportement | `dev` |
| `SERVICE_NAME` | Comportement | `items-api` |
| `USE_IAM_AUTH` | Comportement | `false` |
| `USERS_API_URL` | Infra | `http://users_api:8000` |

## Redis
**DB 1** — namespace `items:*`
- Invalidation obligatoire sur POST/PUT/DELETE (`items:list:*`)

## MCP tools exposés
_Aucun tool MCP détecté dans `mcp_server.py`._

## Gotchas connus
- `router.py` est en zone bloquante : toute nouvelle feature DOIT passer par un `services/` layer
- Routes statiques avant wildcard obligatoire (cf. règle FastAPI §AGENTS.md)
- Cache Redis DB1 — ne pas confondre avec `agent_router_api` qui utilisait historiquement DB1 aussi (corrigé en DB2)

## Dernière modification
2026-04-29 — v0.0.45 — bump version post-audit sécurité
