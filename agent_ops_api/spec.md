# Agent Ops API — Spécification Métier

> Version : voir `/version` | Service : `agent-ops-api` | Rôle : Expert Opérations, Monitoring & FinOps

## 🎯 Rôle

L'Agent Ops est le **spécialiste des opérations et de l'observabilité** de la plateforme Zenika.
Il donne accès aux données de monitoring GCP, aux coûts IA (FinOps) et à la gestion Drive.

---

## 🛠️ Outils MCP disponibles

| MCP | Outils principaux |
|-----|------------------|
| `analytics_mcp` | `get_finops_report`, `check_all_components_health`, `get_service_logs`, `get_infrastructure_topology` |
| `drive_mcp` | `list_synced_folders`, `configure_drive_folder`, `remove_drive_folder` |

---

## 🗺️ Cas d'usage couverts

1. **Santé plateforme** : "Quel est l'état de la plateforme ?" → `check_all_components_health`
2. **Logs** : "Montre-moi les erreurs sur cv-api" → `get_service_logs(service="cv-api", severity="ERROR")`
3. **FinOps** : "Quel est le coût IA de cette semaine ?" → `get_finops_report`
4. **Topologie** : "Montre-moi les traces distribuées" → `get_infrastructure_topology`
5. **Drive** : "Configure le dossier Drive pour l'agence Niort" → `configure_drive_folder`

---

## 📡 Endpoints

| Méthode | Chemin | Description |
|---------|--------|-------------|
| `GET` | `/health` | Santé du service |
| `GET` | `/version` | Version déployée |
| `POST` | `/query` | Requête directe |
| `POST` | `/a2a/query` | Point d'entrée A2A (appelé par le Router) |
| `GET` | `/history` | Historique de session |
| `DELETE` | `/history` | Effacer la session |
| `GET` | `/mcp/registry` | Catalogue des outils MCP chargés |
| `GET` | `/spec` | Cette spécification |

---

## ⚙️ Configuration

- **Redis DB** : 11 (isolation sessions Ops)
- **Session** : éphémère par requête (UUID frais)
- **Modèle** : `GEMINI_MODEL` (env var)
- **OTel** : `OTEL_SERVICE_NAME=agent-ops-api`

## 📡 Schema OpenAPI Auto-Généré

- **GET** `/metrics` : Metrics
- **GET** `/` : Root
- **GET** `/spec` : Get Spec
- **POST** `/login` : Login
- **POST** `/logout` : Logout
- **GET** `/me` : Get Me
- **GET** `/health` : Health
- **GET** `/version` : Get Version
- **POST** `/query` : Query
- **POST** `/a2a/query` : A2A Query
- **GET** `/history` : Get History
- **DELETE** `/history` : Delete History
- **GET** `/mcp/registry` : Mcp Registry
- **PUT** `/mcp/proxy/{server_name}/{path}` : Proxy Mcp
- **POST** `/mcp/proxy/{server_name}/{path}` : Proxy Mcp
- **GET** `/mcp/proxy/{server_name}/{path}` : Proxy Mcp
- **DELETE** `/mcp/proxy/{server_name}/{path}` : Proxy Mcp
- **PATCH** `/mcp/proxy/{server_name}/{path}` : Proxy Mcp
