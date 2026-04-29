# monitoring_mcp

## Rôle
Service MCP natif exposant des outils d'observation infrastructure : Cloud Run metrics, Cloud Logging queries, alertes, health checks de pipelines. Complément opérationnel d'`analytics_mcp`.

## Type
🟤 MCP natif (HTTP direct)

## Architecture modulaire (refactoring 2026-04-29)

Le monolithe `mcp_server.py` (~887L) a été décomposé en modules spécialisés.  
**Chaque fichier respecte la limite de 400 lignes.**

| Fichier | Lignes | Rôle |
|---|---|---|
| `mcp_server.py` | ~210 | ✅ Dispatcher léger — route vers les tools/ |
| `tools/infra_tools.py` | ~294 | Topologie Cloud Trace, découverte services GCP |
| `tools/logs_tools.py` | ~209 | Cloud Logging (traces, logs, erreurs 500) |
| `tools/data_tools.py` | ~126 | Redis, AlloyDB, Pub/Sub DLQ |
| `tools/pipeline_tools.py` | ~222 | Health checks, statut ingestion CV |
| `context.py` | ~11 | `mcp_auth_header_var` (ContextVar — évite les cycles) |
| `mcp_app.py` | 228 | ✅ FastAPI app + routes HTTP |
| `auth.py` | 75 | ✅ verify_jwt local |

### Pattern Dispatcher

```
POST /mcp/call  →  mcp_server.py (dispatcher)
                     ├── infra_tools.py   (get_infrastructure_topology, list_gcp_services_internal)
                     ├── logs_tools.py    (get_cloud_run_logs, get_error_summary)
                     ├── data_tools.py    (get_redis_status, get_alloydb_status, get_pubsub_dlq)
                     └── pipeline_tools.py (get_pipeline_health, get_cv_ingestion_status)
```

## Variables d'environnement

| Var | Type | Valeur dev |
|---|---|---|
| `SECRET_KEY` | Secret | via `.env` |
| `GCP_PROJECT_ID` | Infra | injecté Cloud Run |
| `ROOT_PATH` | Comportement | `` (vide — voir Gotchas) |
| `DRIVE_API_URL` | Infra | URL de `drive_api` |

## Exposition MCP
- `GET /mcp/tools` — liste des tools disponibles
- `POST /mcp/call` — invocation d'un tool par nom
- **Pas de sidecar stdio** — exposition HTTP directe

## MCP tools exposés

| Tool | Module | Description |
|---|---|---|
| `get_cloud_run_logs` | `logs_tools` | Logs Cloud Run filtrés par service/sévérité |
| `get_error_summary` | `logs_tools` | Résumé des erreurs 500 récentes |
| `get_infrastructure_topology` | `infra_tools` | Topologie traces Cloud Trace |
| `list_gcp_services_internal` | `infra_tools` | Découverte services Cloud Run actifs |
| `get_redis_status` | `data_tools` | Métriques Redis (mémoire, keys) |
| `get_alloydb_status` | `data_tools` | Santé AlloyDB |
| `get_pubsub_dlq` | `data_tools` | Messages DLQ Pub/Sub |
| `get_pipeline_health` | `pipeline_tools` | Health checks des microservices |
| `get_cv_ingestion_status` | `pipeline_tools` | Statut pipeline d'ingestion CV |

## Gotchas connus
- **`ROOT_PATH` vide** : contrairement aux autres services, `ROOT_PATH=""` — fix Dockerfile appliqué 2026-04-28.
- **Anti-circularité** : `mcp_auth_header_var` défini dans `context.py` (pas dans `mcp_server.py`) pour éviter les imports circulaires entre le dispatcher et les modules `tools/`.
- **`is_ephemeral=True` interdite** en dev — les tools NAT doivent lever une `ValueError` si `SECRET_KEY` absente.
- La sanity check timeout est à 90s — cold start AlloyDB IAM peut dépasser 35s.

## Dernière modification
`2026-04-29` — Refactoring complet : décomposition du God Module (~887L) en dispatcher (~210L) + 4 modules `tools/` spécialisés.
