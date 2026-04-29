# missions_api

## Rôle
Gestion des missions client (appels d'offre, documents), analyse multimodale des documents de mission via Gemini, et stockage vectoriel pour le matching consultant/mission.

## Type
🔵 API data (producteur MCP)

## Fichiers clés
| Fichier | Lignes | État |
|---|---|---|
| `src/missions/router.py` | 860 | 🚨 Zone bloquante (> 400) — refactoring requis |
| `src/gemini_retry.py` | 75 | ✅ OK |
| `src/missions/models.py` | 69 | ✅ OK |
| `src/missions/cache.py` | 61 | ✅ OK |
| `src/missions/schemas.py` | ~60 | ✅ OK |
| `src/missions/task_state.py` | ~50 | ✅ OK |

## Variables d'environnement
| Var | Type | Valeur dev |
|---|---|---|
| `SECRET_KEY` | Secret | via `.env` |
| `DATABASE_URL` | Infra | injecté Cloud Run |
| `REDIS_URL` | Infra | `redis://redis:6379/8` |
| `GEMINI_MODEL` | Comportement | `gemini-2.5-flash` |
| `MCP_SIDECAR_URL` | Comportement | `http://missions_mcp:8000` |
| `ROOT_PATH` | Comportement | `/missions-api` |

## Redis
**DB 8** — namespace `missions:*`

## Endpoints clés
- `POST /missions/` — création d'une mission avec document (PDF, DOCX auto-converti)
- `GET /missions/` — liste des missions
- `GET /missions/{id}` — détail d'une mission
- `POST /missions/{id}/analyze` — (re)analyse du document via Gemini
- `GET /missions/search` — recherche vectorielle sémantique

## MCP tools exposés
- `list_missions`, `get_mission_by_id`, `create_mission`, `search_missions_semantic`

## Gotchas connus
- **MIME type DOCX** : `application/vnd.openxmlformats-officedocument.wordprocessingml.document` n'est pas supporté par Vertex AI — conversion PDF obligatoire avant envoi au LLM
- `router.py` est en zone bloquante : toute nouvelle feature DOIT passer par un `services/` layer
- La sanity check a un timeout de 90s (latence AlloyDB IAM + cold start Cloud Run)

## Dernière modification
2026-04-29 — v0.0.69 — fix DOCX upload + timeout sanity check
