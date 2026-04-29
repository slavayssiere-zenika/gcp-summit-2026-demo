# analytics_mcp

## Rôle
Service MCP natif (HTTP direct, pas de sidecar stdio) exposant : tracking FinOps des appels LLM vers BigQuery, données marché, et outils GCP infra (Cloud Logging, Cloud Run metrics).

## Type
🟤 MCP natif (HTTP direct)

## Fichiers clés
| Fichier | Lignes | État |
|---|---|---|
| `mcp_server.py` | 403 | ⚠️ Zone alerte |
| `mcp_app.py` | 336 | ⚠️ Zone alerte |
| `auth.py` | ~75 | ✅ OK |
| `init_pricing.py` | 89 | ✅ OK |

## Variables d'environnement
| Var | Type | Valeur dev |
|---|---|---|
| `SECRET_KEY` | Secret | via `.env` |
| `GCP_PROJECT_ID` | Infra | injecté Cloud Run |
| `BIGQUERY_DATASET` | Infra | injecté Cloud Run |
| `ROOT_PATH` | Comportement | `/analytics-mcp` |

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
- `log_ai_consumption` — **CRITIQUE** : appelé par tous les agents après chaque inférence LLM
- `get_ai_usage_stats`, `list_model_pricing`, `get_cloud_run_metrics`, `query_cloud_logging`

## Gotchas connus
- **ADR12 Axe 3** : À terme, ce service sera scindé en `analytics_mcp` + `monitoring_mcp` (voir `todo.md`)
- `log_ai_consumption` est le seul point d'entrée FinOps — son indisponibilité ne doit PAS bloquer les agents (gérer en mode dégradé silencieux côté agent)
- La table `model_pricing` a un schéma en drift avec Terraform — ne pas lancer `terraform apply` sur cette table sans plan review

## Dernière modification
2026-04-29 — v0.0.82 — stable
