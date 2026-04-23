# Analytics MCP — Spécification

> Service MCP natif exposant les données marché, le tracking FinOps et les outils GCP Infrastructure.

## Vue d'ensemble

Le **Analytics MCP** est un service MCP natif (HTTP direct) qui agrège des données issues de **Google BigQuery** et expose des outils utilisables par les agents IA de la plateforme Zenika Console.

- **Port** : `8008`
- **Préfixe proxy Nginx** : `/analytics-mcp/`
- **Authentification** : JWT HS256 obligatoire sur toutes les routes (Zero-Trust)

---

## Architecture

| Type | Détail |
|------|--------|
| Pattern | MCP Natif HTTP (pas de sidecar stdio) |
| Exposition | `GET /mcp/tools` · `POST /mcp/call` |
| Backend | Google BigQuery (ADC / Workload Identity) |
| Cache | Redis DB 1 (SWR : Stale-While-Revalidate) |
| Observabilité | OpenTelemetry + Prometheus |

---

## Endpoints MCP

### `GET /mcp/tools`
Liste tous les outils MCP disponibles avec leur schéma d'entrée.

**Authentification requise** : `Authorization: Bearer <token>`

```json
[
  {
    "name": "log_ai_consumption",
    "description": "Journalise la consommation IA dans BigQuery (table ai_usage)",
    "inputSchema": { ... }
  }
]
```

### `POST /mcp/call`
Invoque un tool MCP par son nom avec les arguments fournis.

**Body** :
```json
{
  "name": "get_finops_summary",
  "arguments": { "days": 7 }
}
```

---

## Endpoints REST natifs

### `GET /api/metrics/aiops`
Récupère les indicateurs AIOps et FinOps agrégés.
- Cache Redis SWR (soft TTL : 1h, hard TTL : 24h)
- Mutex Redis (SETNX) anti cache stampede

### `GET /api/topology`
Topologie infra depuis GCP Cloud Trace.
- Cache Redis (soft TTL : 5min, hard TTL : 1h)

### `POST /api/admin/finops/detect`
Détecte les anomalies de consommation IA et déclenche le Kill-Switch utilisateur si le seuil est dépassé.

---

## Outils MCP exposés

| Tool | Description |
|------|-------------|
| `log_ai_consumption` | Ingestion consommation IA dans BigQuery |
| `get_finops_summary` | Résumé FinOps par utilisateur / modèle |
| `get_infrastructure_topology` | Topologie des services depuis Cloud Trace |
| `get_cloud_run_services` | Liste des Cloud Run en production |
| `get_cloud_logging_errors` | Dernières erreurs Cloud Logging |
| `get_model_usage_stats` | Statistiques d'usage par modèle Gemini |

---

## Sécurité

- Tous les endpoints (sauf `/health`, `/metrics`, `/version`, `/spec`) sont protégés par `verify_jwt`
- La `SECRET_KEY` est purgée de l'environnement après lecture
- Aucun fallback JWT permis — absence de `SECRET_KEY` = crash au démarrage

---

## Observabilité

- **Métriques Prometheus** : `GET /metrics`
- **Health check** : `GET /health` → `{"status": "healthy", "service": "analytics-mcp"}`
- **Version** : `GET /version` → `{"version": "<APP_VERSION>"}`
- **Traçage** : OpenTelemetry OTLP (Tempo)
