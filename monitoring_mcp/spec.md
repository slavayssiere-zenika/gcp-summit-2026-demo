# Monitoring MCP — Spécification

> Service MCP natif exposant les outils de monitoring et d'observabilité de la plateforme Zenika Console.

## Vue d'ensemble

Le **Monitoring MCP** est un service MCP natif (HTTP direct) qui agrège des données de monitoring issues de **GCP Cloud Logging**, **Cloud Trace** et de l'infrastructure Docker locale.

- **Port** : `8010`
- **Préfixe proxy Nginx** : `/monitoring-mcp/`
- **Authentification** : JWT HS256 obligatoire sur toutes les routes (Zero-Trust)

---

## Architecture

| Type | Détail |
|------|--------|
| Pattern | MCP Natif HTTP (pas de sidecar stdio) |
| Exposition | `GET /mcp/tools` · `POST /mcp/call` |
| Backend | GCP Cloud Logging, Cloud Trace, Cloud Run |
| Cache | Redis (topologie infrastructure) |
| Observabilité | OpenTelemetry + Prometheus |

---

## Endpoints MCP

### `GET /mcp/tools`
Liste tous les outils MCP de monitoring disponibles avec leur schéma d'entrée.

**Authentification requise** : `Authorization: Bearer <token>`

```json
[
  {
    "name": "get_service_health",
    "description": "Vérifie l'état de santé de tous les microservices",
    "inputSchema": { ... }
  }
]
```

### `POST /mcp/call`
Invoque un tool MCP de monitoring par son nom avec les arguments fournis.

**Body** :
```json
{
  "name": "get_cloud_run_metrics",
  "arguments": { "service": "agent-router-api", "hours": 1 }
}
```

---

## Endpoints REST natifs

### `GET /api/topology`
Topologie de l'infrastructure depuis GCP Cloud Trace.
- Cache Redis (soft TTL : 5min, hard TTL : 1h)
- Mutex Redis (SETNX) anti cache stampede

---

## Outils MCP exposés

| Tool | Description |
|------|-------------|
| `get_service_health` | État de santé agrégé de tous les microservices |
| `get_cloud_run_metrics` | Métriques CPU/mémoire/latence Cloud Run |
| `get_cloud_logging_errors` | Erreurs récentes depuis Cloud Logging |
| `get_infrastructure_topology` | Topologie des services depuis Cloud Trace |
| `get_trace_details` | Détails d'une trace distribuée par ID |
| `list_cloud_run_services` | Liste des services Cloud Run actifs |

---

## Sécurité

- Tous les endpoints (sauf `/health`, `/metrics`, `/version`, `/spec`) sont protégés par `verify_jwt`
- La `SECRET_KEY` est purgée de l'environnement après lecture
- Aucun fallback JWT permis — absence de `SECRET_KEY` = crash au démarrage

---

## Observabilité

- **Métriques Prometheus** : `GET /metrics`
- **Health check** : `GET /health` → `{"status": "healthy", "service": "monitoring-mcp"}`
- **Version** : `GET /version` → `{"version": "<APP_VERSION>"}`
- **Traçage** : OpenTelemetry OTLP (Tempo)
- **Nom de service OTel** : `monitoring-mcp`
