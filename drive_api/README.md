# drive_api

## Rôle
Synchronisation avec Google Drive : ingestion de CVs et documents depuis des dossiers Drive partagés vers la plateforme.

## Type
🔵 API data (producteur MCP)

## Fichiers clés
| Fichier | Lignes | État |
|---|---|---|
| `main.py` | 219 | ✅ |
| `mcp_server.py` | 397 | ✅ |
| `conftest.py` | 71 | ✅ |
| `src/routers/dlq_router.py` | 411 | ✅ |
| `src/routers/files_router.py` | 403 | ✅ |
| `src/routers/folders_router.py` | 471 | ✅ |
| `src/routers/ingestion_router.py` | 420 | ✅ |

## Variables d'environnement
| Var | Type | Valeur dev |
|---|---|---|
| `PYTHONPATH` | Comportement | `/app` |
| `PORT` | Infra | `8006` |
| `MCP_SIDECAR_URL` | Infra | `http://drive_mcp:8000` |
| `PYTHONUNBUFFERED` | Comportement | `1` |
| `LOG_LEVEL` | Comportement | `INFO` |
| `TRACE_EXPORTER` | Infra | `grpc` |
| `ROOT_PATH` | Comportement | `/drive-api` |
| `APP_VERSION` | Comportement | `dev` |
| `SERVICE_NAME` | Comportement | `drive-api` |
| `USE_IAM_AUTH` | Comportement | `false` |
| `USERS_API_URL` | Infra | `http://users_api:8000` |
| `PUBSUB_CV_IMPORT_TOPIC` | Infra | `zenika-cv-import-events-dev` |
| `GCP_PROJECT_ID` | Infra | `your-gcp-project-id` |
| `MAX_DRIVE_CV_IMPORT` | Infra | `10` |
| `REDIS_URL` | Infra | `redis://redis:6379/6` |

## Redis
**DB 6** — namespace `drive:*`

## Endpoints clés
- `GET /dlq/status`
- `DELETE /dlq/message`
- `POST /dlq/replay`
- `GET /status`
- `GET /files`
- `GET /files/{google_file_id}`
- `GET /consultant/search`
- `POST /retry-errors`
- `DELETE /errors`
- `GET /tokens/google`
- `PATCH /files/{file_id}`
- `POST /folders`
- `PATCH /folders/{folder_id}`
- `GET /folders`
- `POST /folders/reset-sync`
- `POST /folders/rebuild-tree`
- `POST /folders/invalidate-cache`
- `DELETE /folders/{folder_id}`
- `GET /ingestion/stats`
- `GET /ingestion/folder-kpis`

## MCP tools exposés
- `add_drive_folder`, `delete_dlq_message`, `delete_drive_folder`, `get_dlq_status`, `get_drive_file_state`, `get_drive_status`, `get_folder_ingestion_kpis`, `get_ingestion_kpis`, `list_drive_files`, `list_drive_folders`, `replay_dlq`, `reset_drive_folder_sync`, `retry_drive_errors`, `run_quality_gate_batch`, `trigger_drive_sync`, `update_drive_file`

## Gotchas connus
- **Compte de service Drive** (`sa-drive-*-v2`) : NE DOIT PAS être supprimé par `terraform destroy` — les droits Drive sont assignés manuellement et non reproductibles automatiquement
- L'authentification Google Drive utilise `src/google_auth.py` (service account JSON), pas les ADC standard
- `router.py` est en zone bloquante : toute nouvelle feature DOIT passer par un `services/` layer

## Dernière modification
2026-04-29 — v0.0.85 — audit sécurité RBAC
