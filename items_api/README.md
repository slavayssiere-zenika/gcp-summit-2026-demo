# items_api

## Rôle
Gestion des items (catalogue de services/produits) et de leurs catégories.

## Type
🔵 API data (producteur MCP)

## Fichiers clés
| Fichier | Lignes | État |
|---|---|---|
| `src/items/router.py` | 605 | 🚨 Zone bloquante (> 400) — refactoring requis |
| `src/items/schemas.py` | 74 | ✅ OK |
| `src/items/models.py` | 45 | ✅ OK |
| `src/auth.py` | 40 | ✅ OK |

## Variables d'environnement
| Var | Type | Valeur dev |
|---|---|---|
| `SECRET_KEY` | Secret | via `.env` |
| `DATABASE_URL` | Infra | injecté Cloud Run |
| `REDIS_URL` | Infra | `redis://redis:6379/1` |
| `MCP_SIDECAR_URL` | Comportement | `http://items_mcp:8000` |
| `ROOT_PATH` | Comportement | `/items-api` |

## Redis
**DB 1** — namespace `items:*`
- Invalidation obligatoire sur POST/PUT/DELETE (`items:list:*`)

## MCP tools exposés
- `get_item_by_id`, `list_items`, `create_item`, `update_item`, `delete_item`
- `list_categories`, `get_category_by_id`

## Gotchas connus
- `router.py` est en zone bloquante : toute nouvelle feature DOIT passer par un `services/` layer
- Routes statiques avant wildcard obligatoire (cf. règle FastAPI §AGENTS.md)
- Cache Redis DB1 — ne pas confondre avec `agent_router_api` qui utilisait historiquement DB1 aussi (corrigé en DB2)

## Dernière modification
2026-04-29 — v0.0.45 — bump version post-audit sécurité
