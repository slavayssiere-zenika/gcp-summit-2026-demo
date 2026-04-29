# users_api

## Rôle
Gestion des utilisateurs, authentification JWT, et émission de tokens de service pour les background tasks.

## Type
🔵 API data (producteur MCP)

## Fichiers clés
| Fichier | Lignes | État |
|---|---|---|
| `src/users/router.py` | 819 | ⚠️ Zone alerte (> 300) |
| `src/auth.py` | 117 | ✅ OK |
| `src/users/schemas.py` | 85 | ✅ OK |
| `src/users/pubsub.py` | 68 | ✅ OK |
| `src/users/models.py` | ~40 | ✅ OK |
| `mcp_server.py` | ~150 | ✅ OK |
| `main.py` | ~80 | ✅ OK |

## Variables d'environnement
| Var | Type | Valeur dev |
|---|---|---|
| `SECRET_KEY` | Secret | via `.env` |
| `DATABASE_URL` | Infra | injecté Cloud Run |
| `MCP_SIDECAR_URL` | Comportement | `http://users_mcp:8000` |
| `ROOT_PATH` | Comportement | `/users-api` |

## Redis
**DB 0** — namespace `users:*`

## Endpoints clés
- `POST /auth/login` — émission de JWT utilisateur
- `POST /auth/internal/service-token` — token de service longue durée (background tasks)
- `GET /users/me` — profil courant
- `GET /users/{id}` — profil par ID (protégé)
- `POST /users/` — création utilisateur (auto-génération password si absent)

## MCP tools exposés
Consommables par les agents via `agent_commons.mcp_client` :
- `get_user_by_id`, `list_users`, `create_user`, `update_user`, `delete_user`

## Gotchas connus
- Les routes statiques (`/spec`, `/health`) doivent être enregistrées **avant** les routes wildcard `/{id}` (sinon 422 int_parsing sur `"spec"`)
- `POST /auth/internal/service-token` est le **seul** mécanisme autorisé pour les tokens de background task — ne jamais utiliser le compte admin

## Dernière modification
2026-04-29 — Audit sécurité RBAC + renforcement verify_jwt
