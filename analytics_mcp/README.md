# analytics_mcp

## Rôle
Service MCP natif (HTTP direct, pas de sidecar stdio) exposant : tracking FinOps des appels LLM vers BigQuery, données marché, et outils GCP infra (Cloud Logging, Cloud Run metrics).

## Type
🟤 MCP natif (HTTP direct)

## Fichiers clés
| Fichier | Lignes | État |
|---|---|---|
| `mcp_server.py` | 428 | ⚠️ |
| `conftest.py` | 37 | ✅ |

## Variables d'environnement
| Var | Type | Valeur dev |
|---|---|---|
| `PYTHON_AR_REPO` | Comportement | `${PYTHON_AR_REPO}` |
| `SHARED_VERSION` | Comportement | `${SHARED_VERSION}` |
| `PATH` | Comportement | `"/app/.venv/bin:$PATH"` |
| `PYTHONPATH` | Comportement | `/app` |
| `PORT` | Infra | `8080` |
| `PYTHONUNBUFFERED` | Comportement | `1` |
| `LOG_LEVEL` | Comportement | `INFO` |
| `TRACE_EXPORTER` | Infra | `grpc` |
| `ROOT_PATH` | Comportement | `/analytics-mcp` |
| `APP_VERSION` | Comportement | `dev` |
| `ENVIRONMENT` | Comportement | `dev` |

## BigQuery
- Dataset : `ai_analytics` — **localisation OBLIGATOIRE : `europe-west1`**
- Table principale : `ai_usage` (partitionnée par jour)
- Table : `model_pricing` — NE PAS recréer via Terraform (schéma figé, drift connu)
- Tout client `bigquery.Client` DOIT inclure `location="europe-west1"`

## Exposition MCP
- `GET /mcp/tools` — liste des tools disponibles
- `POST /mcp/call` — invocation d'un tool
- **Pas de sidecar stdio** — exposition HTTP directe

## MCP tools exposés
- `detect_usage_anomalies`, `get_aiops_dashboard_data`, `get_finops_report`, `get_market_demand_volume`, `get_rag_quality_history`, `get_sre_trends`, `get_top_market_skills`, `get_usage_statistics`, `log_ai_consumption`, `log_rag_quality_snapshot`, `log_sre_triage`

## Gotchas connus
- **ADR12 Axe 3** : À terme, ce service sera scindé en `analytics_mcp` + `monitoring_mcp` (voir `todo.md`)
- `log_ai_consumption` est le seul point d'entrée FinOps — son indisponibilité ne doit PAS bloquer les agents (gérer en mode dégradé silencieux côté agent)
- La table `model_pricing` a un schéma en drift avec Terraform — ne pas lancer `terraform apply` sur cette table sans plan review

## Dernière modification
- 2026-07-17 — v0.1.45 — Support des mécanismes de sécurité, du triage SRE et de l'intégration globale de l'observabilité.
