# items_api

## Rôle
Gestion des items (catalogue de services/produits) et de leurs catégories.

## Type
🔵 API data (producteur MCP)

## Fichiers clés
| Fichier | Lignes | État |
|---|---|---|
| `main.py` | 210 | ✅ |
| `mcp_server.py` | 402 | ⚠️ |
| `conftest.py` | 68 | ✅ |
| `src/items/admin_router.py` | 91 | ✅ |
| `src/items/crud_router.py` | 357 | ✅ |
| `src/items/router.py` | 26 | ✅ |
| `src/items/routers/categories_router.py` | 100 | ✅ |
| `src/items/routers/search_router.py` | 126 | ✅ |

## Variables d'environnement
| Var | Type | Valeur dev |
|---|---|---|
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
- `bulk_create_items`, `create_category`, `create_item`, `delete_item`, `delete_user_items`, `get_item`, `get_item_stats`, `get_item_with_user`, `get_items_by_user`, `health_check`, `list_categories`, `list_items`, `search_items`, `update_item`

## Gotchas connus
- `router.py` est en zone bloquante : toute nouvelle feature DOIT passer par un `services/` layer
- Routes statiques avant wildcard obligatoire (cf. règle FastAPI §AGENTS.md)
- Cache Redis DB1 — ne pas confondre avec `agent_router_api` qui utilisait historiquement DB1 aussi (corrigé en DB2)

## Dernière modification
2026-04-29 — v0.0.45 — bump version post-audit sécurité
