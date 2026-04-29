# drive_api

## Rôle
Synchronisation avec Google Drive : ingestion de CVs et documents depuis des dossiers Drive partagés vers la plateforme.

## Type
🔵 API data (producteur MCP)

## Fichiers clés
| Fichier | Lignes | État |
|---|---|---|
| `src/router.py` | 1185 | 🚨 Zone bloquante (> 400) — refactoring requis |
| `src/drive_service.py` | 581 | ⚠️ Zone alerte |
| `src/schemas.py` | 129 | ✅ OK |
| `src/google_auth.py` | 100 | ✅ OK |
| `src/redis_client.py` | ~50 | ✅ OK |
| `src/models.py` | ~40 | ✅ OK |

## Variables d'environnement
| Var | Type | Valeur dev |
|---|---|---|
| `SECRET_KEY` | Secret | via `.env` |
| `DATABASE_URL` | Infra | injecté Cloud Run |
| `REDIS_URL` | Infra | `redis://redis:6379/6` (Dockerfile) |
| `MCP_SIDECAR_URL` | Comportement | `http://drive_mcp:8000` |
| `ROOT_PATH` | Comportement | `/drive-api` |
| `GOOGLE_SERVICE_ACCOUNT_KEY` | Secret | compte de service Drive |

## Redis
**DB 6** — namespace `drive:*`

## Endpoints clés
- `POST /drive/sync` — déclenche la synchronisation d'un dossier Drive
- `GET /drive/status` — état de la dernière synchronisation
- `GET /drive/files` — liste des fichiers Drive indexés

## MCP tools exposés
- `sync_drive_folder`, `list_drive_files`, `get_sync_status`

## Gotchas connus
- **Compte de service Drive** (`sa-drive-*-v2`) : NE DOIT PAS être supprimé par `terraform destroy` — les droits Drive sont assignés manuellement et non reproductibles automatiquement
- L'authentification Google Drive utilise `src/google_auth.py` (service account JSON), pas les ADC standard
- `router.py` est en zone bloquante : toute nouvelle feature DOIT passer par un `services/` layer

## Dernière modification
2026-04-29 — v0.0.85 — audit sécurité RBAC
