# Monitoring MCP — Spécification

> Service MCP natif exposant les outils de monitoring, d'observabilité et de SRE de la plateforme Zenika Console.

## Vue d'ensemble

Le **Monitoring MCP** est un service MCP natif (HTTP direct) qui agrège des données de monitoring issues de **GCP Cloud Logging**, **Cloud Trace**, **Cloud Run**, **Redis**, **AlloyDB/PostgreSQL** et **Pub/Sub**.

- **Port** : `8010`
- **Préfixe proxy Nginx** : `/monitoring-mcp/`
- **Authentification** : JWT HS256 obligatoire sur toutes les routes (Zero-Trust)

---

## Architecture

| Type | Détail |
|------|--------|
| Pattern | MCP Natif HTTP (pas de sidecar stdio) |
| Exposition | `GET /mcp/tools` · `POST /mcp/call` |
| Backend | GCP Cloud Logging, Cloud Trace, Cloud Run, Redis, Pub/Sub, AlloyDB |
| Cache | Redis (topologie infrastructure — soft TTL 5min, hard TTL 1h) |
| Observabilité | OpenTelemetry + Prometheus |

---

## Endpoints MCP

### `GET /mcp/tools`
Liste tous les outils MCP de monitoring disponibles avec leur schéma d'entrée.

**Authentification requise** : `Authorization: Bearer <token>`

### `POST /mcp/call`
Invoque un tool MCP de monitoring par son nom avec les arguments fournis.

```json
{
  "name": "get_recent_500_errors",
  "arguments": { "limit": 10, "hours_lookback": 1 }
}
```

---

## Endpoints REST natifs

### `GET /api/topology`
Topologie de l'infrastructure depuis GCP Cloud Trace.
- Cache Redis (soft TTL : 5min, hard TTL : 1h)
- Mutex Redis (SETNX) anti cache stampede
- `?force=true` pour forcer un recalcul immédiat

---

## Outils MCP exposés (11 tools)

### Observabilité & Logs

| Tool | Module | Description | Paramètres clés |
|------|--------|-------------|-----------------|
| `get_infrastructure_topology` | `infra_tools` | Graphe de dépendances inter-services via Cloud Trace | `hours_lookback` (défaut 1) |
| `get_service_logs` | `logs_tools` | Logs récents d'un service Cloud Run (fuzzy match) | `service_name`, `limit`, `hours_lookback`, `severity` |
| `list_gcp_services` | `infra_tools` | Liste des services Cloud Run Zenika actifs | — |
| `search_cloud_logs_by_trace` | `logs_tools` | Flux de logs complet associé à un Trace ID OTel/Tempo | `trace_id`, `limit` |
| `get_recent_500_errors` | `logs_tools` | Erreurs HTTP 5xx récentes sur tous les services Cloud Run | `limit`, `hours_lookback` |

### Health Checks & Pipeline

| Tool | Module | Description | Paramètres clés |
|------|--------|-------------|-----------------|
| `check_component_health` | `pipeline_tools` | Santé d'un composant (Cloud Run, Redis, AlloyDB, BigQuery) | `component_name` |
| `check_all_components_health` | `pipeline_tools` | Health check global de TOUS les composants de la plateforme | — |
| `get_ingestion_pipeline_status` | `pipeline_tools` | Statut pipeline Drive → Pub/Sub → cv_api avec recommandations | — |

### Data Layer (Redis · Pub/Sub · AlloyDB)

| Tool | Module | Description | Paramètres clés |
|------|--------|-------------|-----------------|
| `inspect_pubsub_dlq` | `data_tools` | Lecture seule des messages DLQ Pub/Sub (ack_deadline prolongé à 600s) | `subscription_id` (défaut: `cv-ingestion-dlq-sub`), `limit` |
| `get_redis_invalidation_state` | `data_tools` | Inspection des clés Redis par pattern SCAN | `pattern` (défaut: `*`) |
| `execute_read_only_query` | `data_tools` | Requête SQL SELECT sur AlloyDB (DML/DDL rejeté) | `query`, `db_name` |

---

## Sécurité

- Tous les endpoints (sauf `/health`, `/metrics`, `/version`, `/spec`) sont protégés par `verify_jwt`
- La `SECRET_KEY` est purgée de l'environnement après lecture
- Aucun fallback JWT permis — absence de `SECRET_KEY` = crash au démarrage
- `execute_read_only_query` : filtrage DML/DDL côté serveur avant toute exécution

---

## Observabilité

- **Métriques Prometheus** : `GET /metrics`
- **Health check** : `GET /health` → `{"status": "healthy", "service": "monitoring-mcp"}`
- **Version** : `GET /version` → `{"version": "<APP_VERSION>"}`
- **Traçage** : OpenTelemetry OTLP (Tempo)
- **Nom de service OTel** : `monitoring-mcp`
