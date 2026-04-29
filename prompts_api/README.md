# prompts_api

## Rôle
Gestion et versioning des system prompts des agents IA. Centralise les instructions LLM, reçoit les rapports d'erreurs 500 de toutes les APIs data, et déclenche l'amélioration continue des prompts via LLM.

## Type
🔵 API data (producteur MCP)

## Fichiers clés
| Fichier | Lignes | État |
|---|---|---|
| `src/prompts/router.py` | 281 | ✅ OK (< 300) |
| `src/prompts/analyzer.py` | 180 | ✅ OK |
| `src/gemini_retry.py` | 75 | ✅ OK |
| `src/prompts/schemas.py` | 29 | ✅ OK |
| `src/prompts/models.py` | ~30 | ✅ OK |

## Variables d'environnement
| Var | Type | Valeur dev |
|---|---|---|
| `SECRET_KEY` | Secret | via `.env` |
| `DATABASE_URL` | Infra | injecté Cloud Run |
| `REDIS_URL` | Infra | `redis://redis:6379/5` |
| `GEMINI_MODEL` | Comportement | via env (non hardcodé) |
| `ROOT_PATH` | Comportement | `/prompts-api` |

## Redis
**DB 5** — namespace `prompts:*`

## Endpoints clés
- `GET /prompts/by-name/{name}` — récupère un prompt par nom (ex: `extract_cv_info`) — **CRITIQUE** : retourne string vide si 404
- `POST /prompts/` — création/mise à jour d'un prompt
- `POST /errors/report` — réception des erreurs 500 des APIs data (boucle feedback LLM)

## MCP tools exposés
- `get_prompt_by_name`, `list_prompts`, `create_prompt`, `update_prompt`

## Gotchas connus
- `GET /prompts/by-name/{name}` retourne `""` (string vide) si le prompt n'existe pas — les services appelants DOIVENT vérifier la réponse avant de l'utiliser comme instruction LLM
- Ce service reçoit les rapports d'erreurs asynchrones (`POST /errors/report`) de toutes les APIs data via `@app.exception_handler(Exception)` — il ne doit JAMAIS être down sans fallback
- Pas de `mcp_server.py` sidecar ? À vérifier lors de la prochaine intervention

## Dernière modification
2026-04-29 — v0.0.49 — fix prompt fetch URL dans cv_api
